"""Bounded interpretation and durable execution (owned by REVAMP-P07).

The model proposes; the server disposes. Every step validates against
capabilities and current world state before anything is queued, and
again at the claim boundary before anything is applied.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from worldsim.application.commands.activities import start_activity
from worldsim.application.commands.deity import apply_override
from worldsim.application.commands.director import accept_decision
from worldsim.application.orchestration.service import derive_run_id
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelGateway,
    ModelGatewayError,
)
from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.commands import ActionIntent
from worldsim.domain.director import DirectorProposal, validate_proposal
from worldsim.domain.enums import ActivityKind, LifeStatus, UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_arc_id, new_hook_id, new_intervention_id
from worldsim.domain.interventions import (
    SUPPORTED_ACTIVITY_KINDS,
    SUPPORTED_ATTEMPT_FAMILIES,
    CreateConditionStep,
    DirectActivityStep,
    DirectAttemptStep,
    Interpretation,
    InterpretationStep,
    Intervention,
    InterventionMode,
    InterventionStatus,
    InterventionStep,
    OverrideCharacterStep,
    StepKind,
    StepStatus,
    new_intervention_steps,
)

INTERPRET_PROMPT_VERSION = "intervene-v1"
MAX_STEPS = 5

_ACTION_ADAPTER: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)
_INTERPRETATION_ADAPTER: TypeAdapter[Interpretation] = TypeAdapter(Interpretation)
_SYSTEM = (
    "You interpret one game-master instruction into a bounded typed plan. "
    "Reply with JSON only, matching this shape: "
    '{"schema_version": 1, "steps": [{"kind": ..., "explanation": ..., ...fields}], '
    '"clarification": ""} Step kinds and fields: '
    "propose_hook: {title, purpose, participant_ids[]} - suggest a story opening. "
    "propose_arc: {title, purpose, participant_ids[]} - suggest a longer arc. "
    "direct_activity: {character_id, activity, to_location_id?, duration?} - start one activity. "
    "direct_attempt: {character_id, family, action} - one resolved attempt. "
    "override_character: {character_id, stamina?, mana?, life_status?, conditions[], retcon?}. "
    "world_condition: {label, detail?, location_ids[], severity 1-5, duration_phases} - "
    "a persistent illness with bounded effects; God mode only. "
    "Lethal combat is unsupported: say so in clarification and offer sparring. "
    "Ambiguous references go in clarification with candidates; steps stay empty."
)


@dataclass(frozen=True)
class Scope:
    kind: str = "world"
    character_ids: list[UUID] = field(default_factory=list)
    location_ids: list[UUID] = field(default_factory=list)


@dataclass(frozen=True)
class InterpretOutcome:
    status: InterventionStatus
    interpretation: Interpretation | None = None
    note: str = ""
    candidates: list[dict[str, str]] = field(default_factory=list)


async def interpret(
    uow: UnitOfWork,
    gateway: ModelGateway,
    world_id: UUID,
    role: UserRole,
    mode: InterventionMode,
    text: str,
    scope: Scope,
    viewer: UUID | None = None,
) -> InterpretOutcome:
    """Resolve scope, ask the model for a typed plan, validate it."""
    characters = await uow.characters.list_for_world(world_id)
    locations = await uow.locations.list_for_world(world_id)
    by_id = {c.id: c for c in characters}
    loc_by_id = {loc.id: loc for loc in locations}
    for character_id in scope.character_ids:
        if character_id not in by_id:
            raise DomainError(ErrorCode.NOT_FOUND, "scoped character is not in this world")
    for location_id in scope.location_ids:
        if location_id not in loc_by_id:
            raise DomainError(ErrorCode.NOT_FOUND, "scoped location is not in this world")

    duplicates = _duplicate_names(text, characters)
    if duplicates:
        candidates = [
            {"character_id": str(c.id), "name": c.name, "location_id": str(c.location_id)}
            for c in duplicates
        ]
        return InterpretOutcome(
            InterventionStatus.NEEDS_CLARIFICATION,
            note="which one did you mean?",
            candidates=candidates,
        )

    context = {
        "characters": [
            {"id": str(c.id), "name": c.name, "location_id": str(c.location_id)}
            for c in characters
        ],
        "locations": [{"id": str(loc.id), "name": loc.name} for loc in locations],
    }
    prompt = json.dumps(
        {
            "mode": mode.value,
            "text": text,
            "scope": {
                "kind": scope.kind,
                "character_ids": [str(i) for i in scope.character_ids],
                "location_ids": [str(i) for i in scope.location_ids],
            },
            "context": context,
        }
    )
    try:
        result = await gateway.complete(
            CompletionRequest(prompt=prompt, system=_SYSTEM, json_mode=True, max_tokens=1024)
        )
        interpretation = _INTERPRETATION_ADAPTER.validate_json(result.text)
    except ModelGatewayError:
        # A provider failure is an interpretation failure, never ambiguity:
        # it propagates (audited as a failed call) instead of asking the
        # operator to rephrase a request the model never saw.
        raise
    except Exception:
        return InterpretOutcome(
            InterventionStatus.NEEDS_CLARIFICATION,
            note="I could not map that to a concrete plan; name characters explicitly or pick IDs.",
        )
    problem = _validate_plan(interpretation, role, by_id, loc_by_id, viewer)
    if problem is not None:
        status, note = problem
        return InterpretOutcome(status, note=note)
    return InterpretOutcome(InterventionStatus.QUEUED, interpretation=interpretation)


def _duplicate_names(text: str, characters: list[Any]) -> list[Any]:
    lowered = text.lower()
    by_name: dict[str, list[Any]] = {}
    for character in characters:
        if character.name.lower() in lowered:
            by_name.setdefault(character.name.lower(), []).append(character)
    return [c for group in by_name.values() if len(group) > 1 for c in group]


def _validate_plan(
    interpretation: Interpretation,
    role: UserRole,
    by_id: dict[UUID, Any],
    loc_by_id: dict[UUID, Any],
    viewer: UUID | None = None,
) -> tuple[InterventionStatus, str] | None:
    """Reject unexecutable plans; None means the plan may queue."""
    if len(interpretation.steps) > MAX_STEPS:
        return InterventionStatus.FAILED, "at most five steps per intervention"
    for step in interpretation.steps:
        if role == UserRole.DIRECTOR and step.kind not in (
            StepKind.PROPOSE_HOOK,
            StepKind.PROPOSE_ARC,
        ):
            return (
                InterventionStatus.FAILED,
                "Direct mode proposes hooks and arcs; forcing needs God mode",
            )
        if role == UserRole.PLAYER and (
            step.kind != StepKind.DIRECT_ATTEMPT or step.character_id != viewer
        ):
            return InterventionStatus.FAILED, "players attempt only their own actions"
        problem = _validate_step(step, by_id, loc_by_id)
        if problem is not None:
            return problem
    return None


def _validate_step(
    step: InterpretationStep, by_id: dict[UUID, Any], loc_by_id: dict[UUID, Any]
) -> tuple[InterventionStatus, str] | None:
    if isinstance(step, CreateConditionStep):
        unknown = [loc for loc in step.location_ids if loc not in loc_by_id]
        if unknown:
            return InterventionStatus.NEEDS_CLARIFICATION, "the condition scope is unknown"
        return None
    if isinstance(step, DirectActivityStep):
        if step.activity not in SUPPORTED_ACTIVITY_KINDS:
            return InterventionStatus.FAILED, f"unsupported activity: {step.activity}"
        if step.character_id not in by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the character is unknown"
        if step.to_location_id is not None and step.to_location_id not in loc_by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the destination is unknown"
        return None
    if isinstance(step, DirectAttemptStep):
        if step.family not in SUPPORTED_ATTEMPT_FAMILIES:
            return (
                InterventionStatus.FAILED,
                f"unsupported attempt family: {step.family}; sparring is the supported bout",
            )
        if step.character_id not in by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the actor is unknown"
        # Authoritative identities are resolved server-side, never typed by
        # the user: the step actor, the validated family, and the sealed
        # snapshot override anything the model supplied. Validation checks the
        # shape only (a nil snapshot never persists).
        action = dict(step.action)
        action["character_id"] = str(step.character_id)
        action["snapshot_id"] = "00000000-0000-0000-0000-000000000000"
        try:
            _ACTION_ADAPTER.validate_python({**action, "family": step.family})
        except Exception:
            return InterventionStatus.NEEDS_CLARIFICATION, "the attempt details do not parse"
        return None
    elif isinstance(step, OverrideCharacterStep):
        if step.character_id not in by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the character is unknown"
        if all(
            value is None or value == [] or value is False
            for value in (step.stamina, step.mana, step.life_status, step.conditions)
        ):
            return InterventionStatus.FAILED, "overrides change something"
        if step.life_status is not None:
            try:
                LifeStatus(step.life_status)
            except ValueError:
                return InterventionStatus.FAILED, f"unknown life status: {step.life_status}"
        return None
    return None


async def submit(
    factory: Callable[[], UnitOfWork],
    gateway: ModelGateway,
    world_id: UUID,
    role: UserRole,
    mode: InterventionMode,
    text: str,
    scope: Scope,
    client_request_id: str,
    watermark: int = 0,
    viewer: UUID | None = None,
) -> Intervention:
    """Interpret and persist a queue item; same key replays the same item."""
    if (role == UserRole.DIRECTOR and mode != InterventionMode.INFLUENCE) or (
        role == UserRole.DEITY and mode != InterventionMode.FORCE
    ):
        raise DomainError(ErrorCode.FORBIDDEN, "mode does not match the operating role")
    if role == UserRole.PLAYER and (
        mode != InterventionMode.ATTEMPT
        or viewer is None
        or scope.character_ids != [viewer]
        or scope.location_ids
    ):
        raise DomainError(ErrorCode.FORBIDDEN, "players attempt only their own actions")
    if role not in (UserRole.DIRECTOR, UserRole.DEITY, UserRole.PLAYER):
        raise DomainError(ErrorCode.FORBIDDEN, "interventions need Direct or God mode")
    async with factory() as uow:
        existing = await uow.interventions.find_by_client_key(world_id, client_request_id)
        if existing is not None:
            return existing
        outcome = await interpret(uow, gateway, world_id, role, mode, text, scope, viewer)
        if (
            outcome.status == InterventionStatus.QUEUED
            and (not outcome.interpretation or not outcome.interpretation.steps)
        ):
            note = (
                outcome.note
                or (outcome.interpretation.clarification if outcome.interpretation else "")
                or "the plan came back empty"
            )
            outcome = InterpretOutcome(InterventionStatus.NEEDS_CLARIFICATION, note=note)
        if outcome.status == InterventionStatus.QUEUED:
            assert outcome.interpretation is not None
            interpretation = outcome.interpretation
        else:
            interpretation = Interpretation(steps=[], clarification=outcome.note)
        intervention = Intervention(
            id=new_intervention_id(),
            world_id=world_id,
            client_request_id=client_request_id,
            text=text,
            mode=mode,
            role=role.value,
            status=outcome.status,
            interpretation=interpretation,
            context_watermark=watermark,
            prompt_version=INTERPRET_PROMPT_VERSION,
            failure_reason="" if outcome.status == InterventionStatus.QUEUED else outcome.note,
        )
        try:
            await uow.interventions.add_intervention(intervention)
            parsed = list(interpretation.steps)
            steps = _chain_travel(new_intervention_steps(intervention.id, parsed))
            for step in steps:
                await uow.interventions.add_step(step)
            await uow.commit()
        except Exception:
            await uow.rollback()
            raced = await uow.interventions.find_by_client_key(world_id, client_request_id)
            if raced is None:
                raise
            return raced
        return intervention


def _chain_travel(steps: list[InterventionStep]) -> list[InterventionStep]:
    """Link consecutive travel legs for one character across boundaries."""
    last_travel: dict[str, int] = {}
    chained: list[InterventionStep] = []
    for step in steps:
        if step.kind == StepKind.DIRECT_ACTIVITY and step.targets.get("activity") == "travel":
            actor = str(step.targets.get("character_id", ""))
            if actor in last_travel:
                targets = dict(step.targets)
                targets["after_seq"] = last_travel[actor]
                chained.append(step.model_copy(update={"targets": targets}))
                last_travel[actor] = step.seq
                continue
            last_travel[actor] = step.seq
        chained.append(step)
    return chained


@dataclass(frozen=True)
class PlannedAttempt:
    """A validated directed attempt awaiting beat resolution."""

    actor: UUID
    intent: ActionIntent
    #: "intervention_hex:seq" — the idempotency key suffix the beat records.
    ref: str


def _step_gate_key(intervention_id: UUID, seq: int) -> str:
    return f"direct:{intervention_id.hex}:{seq}"


async def _claim_step_gate(
    uow: UnitOfWork, world_id: UUID, intervention_id: UUID, seq: int
) -> bool:
    """First-writer-wins execution gate for one effect step.

    True means this caller owns the application. False means another beat
    claimed it first: the caller re-reads for a recorded outcome and,
    when none is recorded yet, re-derives through per-step effect identities.
    """
    try:
        await uow.commands.add(
            command_id=uuid4(),
            world_id=world_id,
            key=_step_gate_key(intervention_id, seq),
            actor_role="system",
            command_type="direct_step",
            expected_versions={},
            payload={"intervention_id": str(intervention_id), "seq": seq},
            input_hash=canonical_input_hash(
                {"intervention_id": str(intervention_id), "seq": seq}
            ),
        )
        return True
    except DomainError as exc:
        if exc.code is ErrorCode.IDEMPOTENCY_CONFLICT:
            # The failed flush poisoned this session: roll back so the
            # caller's follow-up commit/read runs on a clean transaction.
            await uow.rollback()
            return False
        raise


async def claim_for_boundary(
    factory: Callable[[], UnitOfWork], world_id: UUID, owner: str
) -> list[tuple[Intervention, list[InterventionStep]]]:
    """Claim open items for one boundary, including stranded executing ones."""
    async with factory() as uow:
        queued = await uow.interventions.list_open_for_world(world_id)
        batch: list[tuple[Intervention, list[InterventionStep]]] = []
        for intervention in queued:
            if intervention.status == InterventionStatus.QUEUED:
                claimed = intervention.model_copy(update={"status": InterventionStatus.EXECUTING})
                saved = await uow.interventions.save_intervention(claimed, intervention.version)
            else:
                saved = intervention
            steps = await uow.interventions.list_steps(intervention.id)
            batch.append((saved, steps))
        await uow.commit()
        return batch


async def apply_batch(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    batch: list[tuple[Intervention, list[InterventionStep]]],
    player_actors: set[UUID],
) -> None:
    """Apply pre-phase effects for claimed items.

    Travel, conditions, overrides, hooks and arcs execute here, each
    step behind its execution gate. Directed attempts are NOT applied
    here: plan_attempts validates them post-seal and record_attempts
    completes them only after their beat commits. Steps already
    completed are skipped, so replaying a beat or restarting after a
    crash cannot double-apply.
    """
    async with factory() as uow:
        characters = {c.id: c for c in await uow.characters.list_for_world(world_id)}
        actives = await uow.activities.list_active_for_world(world_id)
    active_actors = {a.character_id for a in actives}
    for intervention, steps in batch:
        done = {step.seq for step in steps if step.status == StepStatus.COMPLETED}
        for step in steps:
            if step.status != StepStatus.QUEUED:
                continue
            if step.kind == StepKind.DIRECT_ATTEMPT:
                continue
            dep = step.targets.get("after_seq")
            if isinstance(dep, int) and dep not in done:
                continue
            if isinstance(dep, int):
                actor_raw = step.targets.get("character_id")
                try:
                    actor = UUID(str(actor_raw))
                except ValueError:
                    actor = None
                if actor is not None and actor in active_actors:
                    continue
            await _apply_effect_step(
                factory, world_id, index, step, intervention.id, characters
            )
        await _finish_intervention(factory, intervention)


async def _read_step(
    factory: Callable[[], UnitOfWork], intervention_id: UUID, seq: int
) -> InterventionStep | None:
    async with factory() as uow:
        steps = await uow.interventions.list_steps(intervention_id)
    return next((step for step in steps if step.seq == seq), None)


async def _mark_completed(
    factory: Callable[[], UnitOfWork],
    step: InterventionStep,
    activity_id: UUID | None = None,
    event_id: UUID | None = None,
) -> None:
    """Durably record a completed step; an already-completed step is accepted.

    Conflict tolerance is what lets crash-recovery replays converge:
    the winner's recorded outcome stands, the loser adopts it.
    """
    update: dict[str, Any] = {"status": StepStatus.COMPLETED}
    if activity_id is not None:
        update["result_activity_id"] = activity_id
    if event_id is not None:
        update["result_event_id"] = event_id
    try:
        async with factory() as uow:
            await uow.interventions.save_step(step.model_copy(update=update), step.version)
            await uow.commit()
    except DomainError as exc:
        if exc.code is not ErrorCode.VERSION_CONFLICT:
            raise
        current = await _read_step(factory, step.intervention_id, step.seq)
        if current is None or current.status != StepStatus.COMPLETED:
            raise


async def _apply_effect_step(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    intervention_id: UUID,
    characters: dict[UUID, Any],
) -> None:
    """Gate, apply, and durably mark one effect step. Beat-level mutual
    exclusion comes from guarded() at the HTTP route (one executor per
    world and phase scope; a rival advance gets SlotBusy, never a second
    executor), so a taken gate with no recorded outcome means the claiming
    beat crashed after claiming, or a service-level applier is racing this
    one. Either way convergence comes from per-step effect identities,
    never from value matching: the activity carries the step key, hooks
    and arcs persist a command receipt under the step key, overrides
    commit under a step-derived idempotency key, and conditions match on
    the owning intervention plus label. A crash between the effect commit
    and the completion mark therefore re-derives and adopts the recorded
    outcome instead of duplicating it or losing it.

    Completed steps are skipped before this point, so replaying a
    completed beat replays stored results instead of doubling canon;
    recovery after partial execution re-derives through the per-step
    receipts above, which is lossless only where the effect left one
    (activities, hooks/arcs, overrides, conditions).
    """
    async with factory() as uow:
        owned = await _claim_step_gate(uow, world_id, intervention_id, step.seq)
        await uow.commit()
    if not owned:
        current = await _read_step(factory, intervention_id, step.seq)
        if current is not None and current.status == StepStatus.COMPLETED:
            return
        # Gate taken with no recorded outcome: the claiming beat crashed,
        # or a service-level applier is racing; fall through to per-step verify-or-apply.
    try:
        activity_id, event_id = await _run_effect(
            factory, world_id, index, step, intervention_id, characters
        )
    except DomainError as error:
        await _mark_step(factory, step, StepStatus.FAILED, str(error))
        return
    await _mark_completed(factory, step, activity_id, event_id)


async def _run_effect(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    intervention_id: UUID,
    characters: dict[UUID, Any],
) -> tuple[UUID | None, UUID | None]:
    """Run one effect; returns (result_activity_id, result_event_id)."""
    targets = step.targets
    if step.kind == StepKind.DIRECT_ACTIVITY:
        activity_id = await _start_directed_activity(
            factory, world_id, index, step, targets, characters
        )
        return activity_id, None
    if step.kind in (StepKind.PROPOSE_HOOK, StepKind.PROPOSE_ARC):
        await _accept_hook(factory, world_id, index, step, targets, characters)
        return None, None
    if step.kind == StepKind.OVERRIDE_CHARACTER:
        event_id = await _apply_override_step(factory, world_id, index, step, intervention_id)
        return None, event_id
    if step.kind == StepKind.WORLD_CONDITION:
        await _create_condition(factory, world_id, index, step, targets, intervention_id)
        return None, None
    raise DomainError(ErrorCode.VALIDATION_FAILED, f"unsupported step: {step.kind.value}")


async def plan_attempts(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    snapshot_id: UUID,
    filed_actors: set[UUID] | frozenset[UUID] = frozenset(),
) -> list[PlannedAttempt]:
    """Validate queued attempt steps against sealed state and stamp identities.

    Called post-seal inside the advancing beat. The actor, family, and snapshot are stamped from
    the step and the snapshot from the seal: neither is ever typed by
    the user. Conflicting or stale steps fail with reasons; valid ones
    return intents for the beat. Nothing is marked completed here —
    record_attempts completes steps only after their beat commits.
    """
    planned: list[PlannedAttempt] = []
    directed: dict[UUID, ActionIntent] = {}
    async with factory() as uow:
        characters = {
            character.id: character
            for character in await uow.characters.list_for_world(world_id)
            if character.life_status == LifeStatus.ALIVE
        }
        queued = await uow.interventions.list_open_for_world(world_id)
    for intervention in queued:
        async with factory() as uow:
            steps = await uow.interventions.list_steps(intervention.id)
        for step in steps:
            if step.kind != StepKind.DIRECT_ATTEMPT or step.status != StepStatus.QUEUED:
                continue
            try:
                actor, intent = _direct_attempt(
                    step, step.targets, characters, set(filed_actors), directed,
                    snapshot_id,
                )
            except DomainError as error:
                await _mark_step(factory, step, StepStatus.FAILED, str(error))
                continue
            planned.append(
                PlannedAttempt(
                    actor=actor, intent=intent, ref=f"{intervention.id.hex}:{step.seq}"
                )
            )
    return planned


async def record_attempts(
    factory: Callable[[], UnitOfWork], outcomes: list[tuple[str, UUID]]
) -> None:
    """Mark planned attempts completed once their beat commits.

    Each outcome pairs the plan ref with the committed scene event: the
    durable record of execution. Conflict-tolerant like _mark_completed,
    then each touched intervention is finished from its step states.
    """
    touched: set[UUID] = set()
    for ref, event_id in outcomes:
        raw_id, _, raw_seq = ref.partition(":")
        try:
            intervention_id = UUID(hex=raw_id)
            seq = int(raw_seq)
        except ValueError:
            continue
        step = await _read_step(factory, intervention_id, seq)
        if step is None or step.status == StepStatus.COMPLETED:
            continue
        await _mark_completed(factory, step, event_id=event_id)
        touched.add(intervention_id)
    for intervention_id in touched:
        async with factory() as uow:
            current = await uow.interventions.get_intervention(intervention_id)
        await _finish_intervention(factory, current)


async def _mark_step(
    factory: Callable[[], UnitOfWork], step: InterventionStep, status: StepStatus, reason: str = ""
) -> None:
    async with factory() as uow:
        await uow.interventions.save_step(
            step.model_copy(update={"status": status, "failure_reason": reason}), step.version
        )
        await uow.commit()


async def _finish_intervention(
    factory: Callable[[], UnitOfWork], intervention: Intervention
) -> None:
    async with factory() as uow:
        steps = await uow.interventions.list_steps(intervention.id)
        states = {step.status for step in steps}
        if StepStatus.QUEUED in states:
            status = InterventionStatus.EXECUTING
        elif states <= {StepStatus.COMPLETED}:
            status = InterventionStatus.COMPLETED
        elif StepStatus.COMPLETED in states:
            status = InterventionStatus.PARTIALLY_COMPLETED
        else:
            status = InterventionStatus.FAILED
        current = await uow.interventions.get_intervention(intervention.id)
        await uow.interventions.save_intervention(
            current.model_copy(update={"status": status}), current.version
        )
        await uow.commit()


async def _start_directed_activity(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    targets: dict[str, Any],
    characters: dict[UUID, Any],
) -> UUID | None:
    """Start the directed activity; returns its id. Saves nothing: the
    caller marks the step once this outcome is durably recorded. The start
    is idempotent per step key: a persisted-but-unmarked activity from a
    crashed attempt is adopted, never duplicated."""
    character_id = UUID(str(targets["character_id"]))
    character = characters.get(character_id)
    if character is None:
        raise DomainError(ErrorCode.NOT_FOUND, "directed character is gone")
    async with factory() as uow:
        # Durable step receipt across every status (active, completed,
        # interrupted, cancelled): only this step's own effect is
        # adopted. A same-valued activity from a distinct direction
        # carries a different key and never conflates; starting then
        # fails deterministically on the busy character.
        owned = await uow.activities.get_by_direct_step_key(world_id, step.step_key)
        if owned is not None:
            return owned.id
        to_location = targets.get("to_location_id")
        activity = await start_activity(
            uow,
            world_id,
            character_id,
            ActivityKind(str(targets["activity"])),
            index,
            duration_phases=targets.get("duration_phases"),
            direct_step_key=step.step_key,
            to_location_id=UUID(str(to_location)) if to_location else None,
        )
        await uow.commit()
        return activity.id


def _direct_attempt(
    step: InterventionStep,
    targets: dict[str, Any],
    characters: dict[UUID, Any],
    player_actors: set[UUID],
    directed: dict[UUID, ActionIntent],
    snapshot_id: UUID,
) -> tuple[UUID, ActionIntent]:
    character_id = UUID(str(targets["character_id"]))
    if character_id not in characters:
        raise DomainError(ErrorCode.NOT_FOUND, "directed actor is gone")
    if character_id in player_actors:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED, "actor already has a filed attempt this phase"
        )
    if character_id in directed:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED, "actor already directed this phase"
        )
    action = dict(targets.get("action") or {})
    action["character_id"] = str(character_id)
    action["snapshot_id"] = str(snapshot_id)
    intent = _ACTION_ADAPTER.validate_python({**action, "family": targets["family"]})
    if targets["family"] in ("spar", "communicate", "transfer"):
        other_raw = action.get("target_character_id")
        other = characters.get(UUID(str(other_raw))) if other_raw else None
        if other is None or other.location_id != characters[character_id].location_id:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "actors are not co-located; arrange travel first",
            )
    # Reserve the actor: a second queued attempt for the same actor fails
    # deterministically instead of silently overwriting this one.
    directed[character_id] = intent
    return character_id, intent


async def _accept_hook(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    targets: dict[str, Any],
    characters: dict[UUID, Any],
) -> None:
    from worldsim.domain.enums import LifeStatus

    async with factory() as uow:
        known = frozenset(c for c, row in characters.items() if row.life_status == LifeStatus.ALIVE)
        receipt = await uow.commands.get_by_key(world_id, step.step_key)
        # Per-step receipt, not title matching: a persisted receipt means
        # this step already applied (crash recovery adopts it), while a
        # distinct direction sharing the title applies its own step.
        if receipt is not None:
            return
        active_hooks = await uow.narrative.count_active_hooks(world_id)
        active_arcs = await uow.narrative.count_active_arcs(world_id)
        proposal = DirectorProposal(
            action="propose_hook" if step.kind == StepKind.PROPOSE_HOOK else "propose_arc",
            title=str(targets["title"]),
            purpose=str(targets.get("purpose", "")),
            requested_powers=[],
            participant_ids=[UUID(str(p)) for p in targets.get("participant_ids", [])],
        )
        decision = validate_proposal(
            proposal, world_id, known, active_hooks, active_arcs, new_hook_id(), new_arc_id()
        )
        if not decision.accepted:
            raise DomainError(ErrorCode.VALIDATION_FAILED, decision.reason)
        try:
            await accept_decision(uow, world_id, decision, "director", step.step_key, index)
        except DomainError as exc:
            if exc.code is not ErrorCode.IDEMPOTENCY_CONFLICT:
                raise
            # Lost a race with a concurrent applier of this same step: the
            # winner's receipt owns this step key, so adopt it. Anything
            # else means the conflict is not ours; re-raise it.
            await uow.rollback()
            async with factory() as fresh:
                if await fresh.commands.get_by_key(world_id, step.step_key) is None:
                    raise
            return
        await uow.commit()


async def _apply_override_step(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    intervention_id: UUID,
) -> UUID:
    """Deity override with a step-deterministic idempotency key.

    A replayed commit key collides instead of duplicating: the recorded
    event is the proof, so crash recovery converges on it.
    """
    targets = step.targets
    character_id = UUID(str(targets["character_id"]))
    life_status = targets.get("life_status")
    return await apply_override(
        factory,
        world_id,
        character_id,
        derive_run_id(world_id, index),
        index,
        stamina=targets.get("stamina"),
        mana=targets.get("mana"),
        life_status=LifeStatus(life_status) if life_status else None,
        conditions=list(targets.get("conditions") or []),
        retcon=bool(targets.get("retcon", False)),
        key=f"{_step_gate_key(intervention_id, step.seq)}:override",
    )


async def _create_condition(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    targets: dict[str, Any],
    intervention_id: UUID,
) -> None:
    from worldsim.application.conditions import create_condition
    from worldsim.domain.conditions import ConditionType

    async with factory() as uow:
        # Durable step receipt across every status: a persisted condition
        # from this step is adopted on recovery, even after it recovers
        # or expires. Labels are display text: two steps sharing one
        # apply their own conditions.
        if await uow.conditions.get_by_step_key(world_id, step.step_key) is not None:
            return
    duration = int(targets.get("duration_phases") or 1)
    try:
        async with factory() as uow:
            await create_condition(
                uow,
                world_id,
                ConditionType.ILLNESS,
                str(targets["label"]),
                str(targets.get("detail", "")),
                [UUID(str(loc)) for loc in targets.get("location_ids", [])],
                int(targets["severity"]),
                index,
                index + duration,
                source_intervention_id=intervention_id,
                source_step_key=step.step_key,
            )
    except DomainError as exc:
        if exc.code is not ErrorCode.IDEMPOTENCY_CONFLICT:
            raise
        # Lost a race with a concurrent applier of this same step; the
        # failed session already rolled back on context exit. Adopt the
        # winner's condition, else the conflict is not ours.
        async with factory() as fresh:
            if await fresh.conditions.get_by_step_key(world_id, step.step_key) is None:
                raise


async def cancel(
    factory: Callable[[], UnitOfWork], intervention_id: UUID, expected_version: int
) -> Intervention:
    """Cancel queued work; completed history is preserved, not rewritten."""
    async with factory() as uow:
        intervention = await uow.interventions.get_intervention(intervention_id)
        if intervention.status not in (
            InterventionStatus.QUEUED,
            InterventionStatus.NEEDS_CLARIFICATION,
            InterventionStatus.EXECUTING,
            InterventionStatus.PARTIALLY_COMPLETED,
        ):
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED, f"cannot cancel {intervention.status.value}"
            )
        saved = await uow.interventions.save_intervention(
            intervention.model_copy(update={"status": InterventionStatus.CANCELLED}),
            expected_version,
        )
        for step in await uow.interventions.list_steps(intervention.id):
            if step.status == StepStatus.QUEUED:
                await uow.interventions.save_step(
                    step.model_copy(update={"status": StepStatus.CANCELLED}), step.version
                )
        await uow.commit()
        return saved


async def edit_text(
    factory: Callable[[], UnitOfWork],
    gateway: ModelGateway,
    intervention_id: UUID,
    expected_version: int,
    text: str,
    scope: Scope,
    viewer: UUID | None = None,
) -> Intervention:
    """Reinterpret before claim; history restarts from the new text."""
    async with factory() as uow:
        intervention = await uow.interventions.get_intervention(intervention_id)
        if intervention.status not in (
            InterventionStatus.QUEUED,
            InterventionStatus.NEEDS_CLARIFICATION,
        ):
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED, f"cannot edit {intervention.status.value}"
            )
        outcome = await interpret(
            uow,
            gateway,
            intervention.world_id,
            UserRole(intervention.role),
            intervention.mode,
            text,
            scope,
            viewer,
        )
        if (
            outcome.status == InterventionStatus.QUEUED
            and (not outcome.interpretation or not outcome.interpretation.steps)
        ):
            note = (
                outcome.note
                or (outcome.interpretation.clarification if outcome.interpretation else "")
                or "the plan came back empty"
            )
            outcome = InterpretOutcome(InterventionStatus.NEEDS_CLARIFICATION, note=note)
        if outcome.status == InterventionStatus.QUEUED:
            assert outcome.interpretation is not None
            interpretation = outcome.interpretation
        else:
            interpretation = Interpretation(steps=[], clarification=outcome.note)
        saved = await uow.interventions.save_intervention(
            intervention.model_copy(
                update={
                    "status": outcome.status,
                    "interpretation": interpretation,
                    "failure_reason": (
                        "" if outcome.status == InterventionStatus.QUEUED else outcome.note
                    ),
                }
            ),
            expected_version,
        )
        for old in await uow.interventions.list_steps(intervention.id):
            await uow.interventions.save_step(
                old.model_copy(update={"status": StepStatus.CANCELLED}), old.version
            )
        for step in _chain_travel(new_intervention_steps(saved.id, list(interpretation.steps))):
            await uow.interventions.add_step(step)
        await uow.commit()
        return saved
