"""Atomic scene commit builder (owned by S1-COMMIT-001).

One scene result commits as one canonical transaction: the idempotency
record, the world event, ordered effects, projections, the scene layer
(intent, scene, attempts, reactions, resolution), observations from
permitted fact sets, immediate memories, and exactly one narration
outbox record. The outbox row is the only narration work that exists
before the NarrationGraph runs; a rollback removes it with everything
else.
"""

from __future__ import annotations

from uuid import UUID

from worldsim.application.transactions.canonical import (
    CommitRequest,
    MemorySpec,
    ObservationSpec,
    OutboxSpec,
    SceneRecords,
    canonical_input_hash,
)
from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import CommandType, EventType
from worldsim.domain.perception import ObservationFact, PerceivedFact
from worldsim.domain.scenes import Attempt, Intent, Reaction, Resolution, Scene

#: Narration outbox kind consumed by S1-NARRATE-001 (never canon itself).
NARRATION_OUTBOX_KIND = "narrate_scene"


def narration_spec(scene_id: UUID) -> OutboxSpec:
    """The single narration work record for a committed scene."""
    return OutboxSpec(
        kind=NARRATION_OUTBOX_KIND,
        payload={"scene_id": str(scene_id)},
        key=f"narrate:{scene_id}",
    )


def observation_spec(
    observer_id: UUID,
    facts: list[PerceivedFact],
    source_id: UUID | None = None,
) -> ObservationSpec:
    """Permitted fact set as a commit observation (key/value only).

    Visibility, channel, and concealment metadata stays in the context
    manifest and trace; the observation row keeps exactly what the
    observer may retain. `source_id` carries the stable underlying action
    identity (the intent id) when all facts derive from one action.
    """
    return ObservationSpec(
        observer_id=observer_id,
        facts=[ObservationFact(key=fact.key, value=fact.value) for fact in facts],
        source_id=source_id,
    )


#: Families that leave the world as it was: a scene of only these is idle.
IDLE_FAMILIES = frozenset({"wait", "rest"})


def _event_summary(location_id: UUID | None, intents: list[Intent]) -> dict[str, str]:
    """Where the scene happened, and whether everyone in it only waited or rested."""
    summary: dict[str, str] = {}
    if location_id is not None:
        summary["location_id"] = str(location_id)
    if intents and all(i.action.family.value in IDLE_FAMILIES for i in intents):
        summary["idle"] = "1"
    return summary


def build_scene_commit(
    *,
    command_id: UUID,
    scene: Scene,
    intents: list[Intent],
    attempts: list[Attempt],
    reactions: list[Reaction],
    resolution: Resolution,
    effects: list[DomainEffect],
    expected_versions: dict[str, int],
    absolute_index: int,
    observations: list[ObservationSpec] | None = None,
    memories: list[MemorySpec] | None = None,
    location_id: UUID | None = None,
) -> CommitRequest:
    """Build the one atomic commit for a resolved scene.

    The event records the scene's participants and, when known, where it
    happened, so feeds can place it on the map without replaying scenes.
    """
    payload: dict[str, object] = {
        "scene_id": str(scene.id),
        "intent_ids": sorted(str(i.id) for i in intents),
        "resolution_id": str(resolution.id),
        "absolute_index": absolute_index,
    }
    key = f"scene:{scene.id}"
    return CommitRequest(
        command_id=command_id,
        world_id=scene.world_id,
        idempotency_key=key,
        actor_role="system",
        command_type=CommandType.COMMIT_SCENE.value,
        expected_versions=dict(expected_versions),
        payload=payload,
        input_hash=canonical_input_hash(
            {
                "key": key,
                "payload": payload,
                "effects": [e.model_dump(mode="json") for e in effects],
            }
        ),
        absolute_index=absolute_index,
        phase_run_id=scene.phase_run_id,
        event_type=EventType.ACTION_RESOLVED,
        effects=list(effects),
        observations=list(observations or []),
        memories=list(memories or []),
        outbox=[narration_spec(scene.id)],
        participant_ids=sorted({p.character_id for p in scene.participants}, key=str),
        summary=_event_summary(location_id, intents),
        scene_records=SceneRecords(
            scene=scene,
            intents=list(intents),
            attempts=list(attempts),
            reactions=list(reactions),
            resolution=resolution,
        ),
    )


__all__ = ["NARRATION_OUTBOX_KIND", "build_scene_commit", "narration_spec", "observation_spec"]
