# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""ResolutionGraph: minimal hybrid resolution (owned by S1-RESOLVE-001).

START -> deterministic feasibility envelopes
-> if every intent is determined: automatic resolution
-> otherwise bounded ambiguity packet -> call resolver model
-> validate against the feasible envelope -> repair once
-> deterministic fallback -> END.

No remote call occurs in the canonical commit transaction: this graph
produces a proposal the commit stage revalidates. Seed evidence travels
on the resolution; no chance draws exist in Stage 1.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from langgraph.graph import StateGraph
from pydantic import TypeAdapter, ValidationError

from worldsim.application.graphs.lenient import (
    fill_expected_versions,
    repair_detail,
    validate_lenient,
)
from worldsim.application.graphs.state import GraphState
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelGateway,
    ModelMalformedError,
    ModelProfile,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from worldsim.domain.characters import Character
from worldsim.domain.commands import MoveAction
from worldsim.domain.effects import MoveEntityEffect
from worldsim.domain.enums import ResolutionOutcome, ResolverKind
from worldsim.domain.ids import derive_resolution_id
from worldsim.domain.resolution import AmbiguityPacket, ResolverProposal
from worldsim.domain.rules.resolution import (
    STAGE1_FEASIBLE_EFFECTS,
    FeasibilityEnvelope,
    build_envelope,
    build_packet,
    merge_determined,
    resolution_seed,
)
from worldsim.domain.rules.views import WorldView
from worldsim.domain.scenes import Intent, Resolution
from worldsim.domain.world import Location, World

#: Versioned resolver prompt file.
RESOLVER_PROMPT_VERSION = "resolver.v2"

_PROPOSAL_ADAPTER: TypeAdapter[ResolverProposal] = TypeAdapter(ResolverProposal)


class ResolveState(GraphState, total=False):
    """Graph state plus resolver-local envelope and prompt fields."""

    intents_json: list[dict[str, Any]]
    characters_json: list[dict[str, Any]]
    locations_json: list[dict[str, Any]]
    expected_versions: dict[str, int]
    envelopes_json: list[dict[str, Any]]
    packet_json: dict[str, Any] | None
    system_prompt: str
    user_prompt: str
    raw_response: str | None


@dataclass(frozen=True)
class ResolverGraphDeps:
    """Everything the graph may call: a gateway and static text."""

    gateway: ModelGateway
    profile: ModelProfile
    system_template: str
    max_tokens: int = 512
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    repair_budget: int = 1


def prompt_path() -> Path:
    """Versioned prompt file next to the backend root."""
    return Path(__file__).resolve().parents[4] / "prompts" / f"{RESOLVER_PROMPT_VERSION}.md"


def load_resolver_prompt() -> str:
    """Read the versioned resolver prompt (fails loudly when missing)."""
    return prompt_path().read_text(encoding="utf-8")


def render_system_prompt(template: str) -> str:
    """Fill the response-schema placeholder (the only placeholder)."""
    schema_json = json.dumps(_PROPOSAL_ADAPTER.json_schema(), indent=2, sort_keys=True)
    return template.replace("{{RESPONSE_SCHEMA}}", schema_json)


def render_user_prompt(packet: AmbiguityPacket) -> str:
    """Bounded ambiguity packet as the model-visible question."""
    lines = [
        f"Scene {packet.scene_id} at snapshot {packet.snapshot_id}.",
        "Intents:",
        *[f"- {summary}" for summary in packet.summaries],
        f"Allowed outcomes: {', '.join(o.value for o in packet.allowed_outcomes)}.",
        f"Allowed aggregates: {', '.join(packet.allowed_aggregate_ids) or 'none'}.",
    ]
    if packet.determined_effects:
        lines.append(
            "Determined effects to keep: "
            + "; ".join(
                f"{e.effect_type.value} on {','.join(str(i) for i in e.affected_ids)}"
                for e in packet.determined_effects
            )
        )
    lines.append(f"Reason: {packet.reason}.")
    return "\n".join(lines)


def proposal_effects_valid(
    proposal: ResolverProposal, packet: AmbiguityPacket, view: WorldView | None = None
) -> str | None:
    """Effect validation: feasible types on allowed aggregates only.

    With a world view, moves must also start where the character stands
    and end at a place that exists: the model cannot know location ids,
    and an invented one would only fail later, inside the commit.
    """
    allowed = {a.split(":", 1)[-1] for a in packet.allowed_aggregate_ids}
    for effect in proposal.effects:
        if effect.effect_type not in STAGE1_FEASIBLE_EFFECTS:
            return f"infeasible effect type: {effect.effect_type.value}"
        touched = {str(i) for i in effect.affected_ids}
        if not touched <= allowed:
            return f"effect touches aggregates outside the envelope: {sorted(touched - allowed)}"
        if view is not None and isinstance(effect, MoveEntityEffect):
            denial = _move_denial(effect, view)
            if denial is not None:
                return denial
    if proposal.outcome not in packet.allowed_outcomes:
        return f"outcome outside the envelope: {proposal.outcome.value}"
    return None


def _move_denial(effect: MoveEntityEffect, view: WorldView) -> str | None:
    places = {loc.id for loc in view.locations}
    if effect.to_location_id not in places:
        return f"move to an unknown place: {effect.to_location_id}"
    where = {c.id: c.location_id for c in view.characters}
    for mover in effect.affected_ids:
        if mover in where and where[mover] != effect.from_location_id:
            return f"move must start where the character stands ({where[mover]})"
    return None


def fill_move_endpoints(raw: str, moves: Mapping[str, tuple[str, str]]) -> str:
    """Set from/to of each move effect for a character who attempted a move,
    and drop move effects for characters who attempted none.

    The attempt already names the destination and the server knows where
    the character stands; the model only decides whether the move happens.
    """
    try:
        document: object = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(document, dict):
        return raw
    effects = cast("dict[str, Any]", document).get("effects")
    if not isinstance(effects, list):
        return raw
    kept: list[Any] = []
    for effect in cast("list[Any]", effects):
        if not isinstance(effect, dict):
            kept.append(effect)
            continue
        item = cast("dict[str, Any]", effect)
        affected = item.get("affected_ids")
        if item.get("effect_type") != "move_entity" or not isinstance(affected, list):
            kept.append(item)
            continue
        movers = [str(a) for a in cast("list[Any]", affected) if str(a) in moves]
        if not movers:
            # A move for someone who never tried to go anywhere ("from market
            # to market" for a character who only spoke) cost a whole repair
            # call; it changes nothing the scene asked for, so drop it.
            continue
        item["from_location_id"], item["to_location_id"] = moves[movers[0]]
        kept.append(item)
    cast("dict[str, Any]", document)["effects"] = kept
    return json.dumps(document)


def _moves_of(state: ResolveState) -> dict[str, tuple[str, str]]:
    """Attempted moves in this scene: actor -> (current place, destination)."""
    where = {str(c.id): str(c.location_id) for c in _view_of(state).characters}
    moves: dict[str, tuple[str, str]] = {}
    for intent in _intents_of(state):
        action = intent.action
        actor = str(intent.author_character_id)
        if isinstance(action, MoveAction) and actor in where:
            moves[actor] = (where[actor], str(action.destination_location_id))
    return moves


def _view_of(state: ResolveState) -> WorldView:
    world_raw = state.get("world_id")
    assert isinstance(world_raw, str) and world_raw
    characters = [Character.model_validate(c) for c in state.get("characters_json", [])]
    locations = [Location.model_validate(loc) for loc in state.get("locations_json", [])]
    return WorldView(
        world=World(id=UUID(world_raw), name="Vale", seed_version="s1-resolve"),
        characters=characters,
        locations=locations,
    )


def _intents_of(state: ResolveState) -> list[Intent]:
    return [Intent.model_validate(i) for i in state.get("intents_json", [])]


def _wrap_resolution(
    *,
    world_id: UUID,
    scene_id: UUID,
    outcome: ResolutionOutcome,
    resolver: ResolverKind,
    profile_version: str,
    effects: list[Any],
    rationale: str,
    snapshot_id: UUID,
) -> Resolution:
    return Resolution(
        id=derive_resolution_id(scene_id),
        world_id=world_id,
        scene_id=scene_id,
        outcome=outcome,
        resolver=resolver,
        profile_version=profile_version,
        effects=effects,
        rationale=rationale,
        random_seed=resolution_seed(scene_id, snapshot_id),
    )


def _proposal(resolution: Resolution, *, fallback: bool, reason: str) -> dict[str, Any]:
    return {
        "resolution": resolution.model_dump(mode="json"),
        "fallback": fallback,
        "reason": reason,
    }


def _versions_of(state: ResolveState) -> dict[str, int]:
    """Aggregate versions the server read for this scene (key: aggregate id)."""
    raw = state.get("expected_versions")
    if not isinstance(raw, dict):
        return {}
    return {str(k).split(":", 1)[-1]: int(v) for k, v in raw.items()}


def build_resolve_graph(deps: ResolverGraphDeps) -> Any:
    """Compile the hybrid resolution graph around injected dependencies."""

    def build_envelopes(state: ResolveState) -> dict[str, Any]:
        view = _view_of(state)
        intents = _intents_of(state)
        versions_raw = state.get("expected_versions")
        assert isinstance(versions_raw, dict)
        versions = {str(k): int(v) for k, v in versions_raw.items()}
        envelopes = [build_envelope(intent, view, versions) for intent in intents]
        return {
            "envelopes_json": [e.model_dump(mode="json") for e in envelopes],
            "status": "envelopes_built",
        }

    def route(state: ResolveState) -> str:
        envelopes = [FeasibilityEnvelope.model_validate(e) for e in state.get("envelopes_json", [])]
        if envelopes and all(e.determined for e in envelopes):
            return "automatic"
        return "assisted"

    def finalize_automatic(state: ResolveState) -> dict[str, Any]:
        envelopes = [FeasibilityEnvelope.model_validate(e) for e in state.get("envelopes_json", [])]
        outcome, effects = merge_determined(envelopes)
        scene_raw = state.get("scene_id")
        snapshot_raw = state.get("snapshot_id")
        world_raw = state.get("world_id")
        assert (
            isinstance(scene_raw, str)
            and isinstance(snapshot_raw, str)
            and isinstance(world_raw, str)
        )
        resolution = _wrap_resolution(
            world_id=UUID(world_raw),
            scene_id=UUID(scene_raw),
            outcome=outcome,
            resolver=ResolverKind.DETERMINISTIC,
            profile_version="",
            effects=effects,
            rationale="automatic: every intent determined",
            snapshot_id=UUID(snapshot_raw),
        )
        return {
            "proposal": _proposal(resolution, fallback=False, reason="automatic"),
            "validation_errors": [],
            "repair_count": 0,
            "status": "resolved",
        }

    def render_packet(state: ResolveState) -> dict[str, Any]:
        scene_raw = state.get("scene_id")
        snapshot_raw = state.get("snapshot_id")
        world_raw = state.get("world_id")
        assert (
            isinstance(scene_raw, str)
            and isinstance(snapshot_raw, str)
            and isinstance(world_raw, str)
        )
        intents = _intents_of(state)
        envelopes = [FeasibilityEnvelope.model_validate(e) for e in state.get("envelopes_json", [])]
        packet = build_packet(
            view=_view_of(state),
            scene_id=UUID(scene_raw),
            world_id=UUID(world_raw),
            snapshot_id=UUID(snapshot_raw),
            intents=intents,
            envelopes=envelopes,
        )
        return {
            "packet_json": packet.model_dump(mode="json"),
            "system_prompt": render_system_prompt(deps.system_template),
            "user_prompt": render_user_prompt(packet),
        }

    async def decide(state: ResolveState) -> dict[str, Any]:
        packet = AmbiguityPacket.model_validate(state.get("packet_json"))
        system = state.get("system_prompt")
        user = state.get("user_prompt")
        assert isinstance(system, str) and isinstance(user, str)
        errors: list[str] = []
        repairs = 0
        try:
            result = await deps.gateway.complete(
                CompletionRequest(
                    prompt=user,
                    system=system,
                    max_tokens=deps.max_tokens,
                    json_mode=True,
                    temperature=deps.temperature,
                    top_p=deps.top_p,
                    top_k=deps.top_k,
                )
            )
        except (
            ModelTimeoutError,
            ModelRateLimitedError,
            ModelUnavailableError,
            ModelRefusalError,
            ModelMalformedError,
        ) as exc:
            return _fallback_result(state, f"provider failed ({type(exc).__name__})", [], 0)
        raw: str | None = result.text
        while True:
            try:
                proposal = validate_lenient(
                    _PROPOSAL_ADAPTER,
                    fill_move_endpoints(
                        fill_expected_versions(raw, _versions_of(state)), _moves_of(state)
                    ),
                )
            except ValidationError as exc:
                errors.append(
                    f"attempt {repairs}: {exc.error_count()} schema errors ({repair_detail(exc)})"
                )
                if repairs >= deps.repair_budget:
                    return _fallback_result(
                        state,
                        f"unrepairable resolver output ({len(errors)} attempts)",
                        errors,
                        repairs,
                    )
                repairs += 1
                try:
                    repaired = await deps.gateway.complete(
                        CompletionRequest(
                            prompt=(
                                f"{user}\n\nYour previous output was rejected "
                                f"({errors[-1]}). Output exactly one JSON object "
                                "matching the response schema."
                            ),
                            system=system,
                            max_tokens=deps.max_tokens,
                            temperature=deps.temperature,
                            top_p=deps.top_p,
                            top_k=deps.top_k,
                            json_mode=True,
                        )
                    )
                except (
                    ModelTimeoutError,
                    ModelRateLimitedError,
                    ModelUnavailableError,
                    ModelRefusalError,
                    ModelMalformedError,
                ) as exc:
                    return _fallback_result(
                        state, f"repair call failed ({type(exc).__name__})", errors, repairs
                    )
                raw = repaired.text
                continue
            denial = proposal_effects_valid(proposal, packet, _view_of(state))
            if denial is not None:
                errors.append(f"attempt {repairs}: {denial}")
                if repairs >= deps.repair_budget:
                    return _fallback_result(
                        state, f"unenforceable resolver output ({denial})", errors, repairs
                    )
                repairs += 1
                try:
                    repaired = await deps.gateway.complete(
                        CompletionRequest(
                            prompt=(
                                f"{user}\n\nYour previous output was rejected "
                                f"({denial}). Output exactly one JSON object "
                                "matching the response schema."
                            ),
                            system=system,
                            max_tokens=deps.max_tokens,
                            temperature=deps.temperature,
                            top_p=deps.top_p,
                            top_k=deps.top_k,
                            json_mode=True,
                        )
                    )
                except (
                    ModelTimeoutError,
                    ModelRateLimitedError,
                    ModelUnavailableError,
                    ModelRefusalError,
                    ModelMalformedError,
                ) as exc:
                    return _fallback_result(
                        state, f"repair call failed ({type(exc).__name__})", errors, repairs
                    )
                raw = repaired.text
                continue
            return _accepted_result(state, proposal, errors, repairs, raw, deps.profile.version)

    builder = StateGraph(ResolveState)
    builder.add_node("build_envelopes", build_envelopes)
    builder.add_node("finalize_automatic", finalize_automatic)
    builder.add_node("render_packet", render_packet)
    builder.add_node("decide", decide)
    builder.set_entry_point("build_envelopes")
    builder.add_conditional_edges(
        "build_envelopes", route, {"automatic": "finalize_automatic", "assisted": "render_packet"}
    )
    builder.add_edge("render_packet", "decide")
    builder.set_finish_point("decide")
    builder.set_finish_point("finalize_automatic")
    return builder.compile()


def _fallback_result(
    state: ResolveState, reason: str, errors: list[str], repairs: int
) -> dict[str, Any]:
    envelopes = [FeasibilityEnvelope.model_validate(e) for e in state.get("envelopes_json", [])]
    determined = [e for e in envelopes if e.determined]
    if determined:
        outcome, effects = merge_determined(determined)
    else:
        outcome, effects = ResolutionOutcome.FAILURE, []
    scene_raw = state.get("scene_id")
    snapshot_raw = state.get("snapshot_id")
    world_raw = state.get("world_id")
    assert (
        isinstance(scene_raw, str) and isinstance(snapshot_raw, str) and isinstance(world_raw, str)
    )
    resolution = _wrap_resolution(
        world_id=UUID(world_raw),
        scene_id=UUID(scene_raw),
        outcome=outcome,
        resolver=ResolverKind.DETERMINISTIC,
        profile_version="",
        effects=effects,
        rationale=f"fallback: {reason}",
        snapshot_id=UUID(snapshot_raw),
    )
    return {
        "proposal": _proposal(resolution, fallback=True, reason=reason),
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": None,
        "status": "fallback",
    }


def _accepted_result(
    state: ResolveState,
    proposal: ResolverProposal,
    errors: list[str],
    repairs: int,
    raw: str | None,
    profile_version: str,
) -> dict[str, Any]:
    scene_raw = state.get("scene_id")
    snapshot_raw = state.get("snapshot_id")
    world_raw = state.get("world_id")
    assert (
        isinstance(scene_raw, str) and isinstance(snapshot_raw, str) and isinstance(world_raw, str)
    )
    resolution = _wrap_resolution(
        world_id=UUID(world_raw),
        scene_id=UUID(scene_raw),
        outcome=proposal.outcome,
        resolver=ResolverKind.MODEL,
        profile_version=profile_version,
        effects=list(proposal.effects),
        rationale=proposal.rationale,
        snapshot_id=UUID(snapshot_raw),
    )
    return {
        "proposal": _proposal(resolution, fallback=False, reason="model-assisted"),
        "validation_errors": errors,
        "repair_count": repairs,
        "raw_response": raw,
        "status": "resolved",
    }


__all__ = [
    "RESOLVER_PROMPT_VERSION",
    "ResolveState",
    "ResolverGraphDeps",
    "build_resolve_graph",
    "load_resolver_prompt",
    "proposal_effects_valid",
    "render_user_prompt",
]
