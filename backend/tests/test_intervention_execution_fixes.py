"""Execution-identity fixes for the intervention queue (review follow-up).

1. Server-stamped identities override model-supplied actor, snapshot, and
   family values at validation and at plan time.
2. A second queued attempt for the same actor fails deterministically
   instead of silently overwriting the first.
3. Per-step effect identities: crash/overlap recovery adopts the recorded
   outcome, while distinct directions sharing a label or title apply
   separately.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from worldsim.application import interventions as service
from worldsim.application.interventions import Scope
from worldsim.application.orchestration.service import derive_run_id
from worldsim.domain.activities import TravelRoute
from worldsim.domain.characters import Character
from worldsim.domain.commands import WaitAction
from worldsim.domain.enums import UserRole
from worldsim.domain.ids import (
    new_character_id,
    new_location_id,
    new_route_id,
    new_snapshot_id,
    new_world_id,
)
from worldsim.domain.interventions import (
    InterventionMode,
    InterventionStatus,
    StepStatus,
)
from worldsim.domain.phases import PhaseRun
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import DIRECTOR_FAKE_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _factory() -> Any:
    engine = create_engine(Settings())
    return lambda: create_unit_of_work(engine)


async def _seed_world() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            hearth = new_location_id()
            market = new_location_id()
            wren = new_character_id()
            ash = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="e6-fix"))
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth", capacity=4))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market", capacity=4))
            for src, dst in ((hearth, market), (market, hearth)):
                await uow.routes.add(
                    TravelRoute(
                        id=new_route_id(),
                        world_id=wid,
                        from_location_id=src,
                        to_location_id=dst,
                        duration_phases=1,
                        stamina_cost=0,
                    )
                )
            for cid, name in ((wren, "Wren"), (ash, "Ash")):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=hearth,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.commit()
            return {"world": wid, "hearth": hearth, "market": market, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def _plan(steps: list[dict[str, Any]]) -> str:
    return json.dumps({"schema_version": 1, "steps": steps, "clarification": ""})


def _travel_step(wren: UUID, market: UUID) -> dict[str, Any]:
    return {
        "kind": "direct_activity",
        "explanation": "Wren walks to the Market.",
        "character_id": str(wren),
        "activity": "travel",
        "to_location_id": str(market),
    }


async def _submit(
    factory: Any, gateway: FakeGateway, wid: UUID, text: str, key: str, steps: list[dict[str, Any]]
) -> Any:
    gateway.enqueue_text(_plan(steps))
    item = await service.submit(
        factory, gateway, wid, UserRole.DEITY, InterventionMode.FORCE, text, Scope(), key
    )
    # Mirror the beat: event-writing effects FK their phase run, and the
    # orchestrator creates it idempotently before draining the queue.
    try:
        async with factory() as uow:
            await uow.phases.create_run(
                PhaseRun(id=derive_run_id(wid, 1), world_id=wid, absolute_index=1)
            )
            await uow.commit()
    except IntegrityError:
        pass
    return item


async def _steps_of(factory: Any, intervention_id: UUID) -> list[Any]:
    async with factory() as uow:
        return await uow.interventions.list_steps(intervention_id)


async def _characters(factory: Any, wid: UUID) -> dict[UUID, Any]:
    async with factory() as uow:
        return {c.id: c for c in await uow.characters.list_for_world(wid)}


async def _claim_gate(factory: Any, wid: UUID, intervention_id: UUID, seq: int) -> bool:
    async with factory() as uow:
        owned = await service._claim_step_gate(uow, wid, intervention_id, seq)
        await uow.commit()
        return owned


def test_model_supplied_actor_snapshot_and_family_are_overridden(migrated_db: None) -> None:
    """Contradictory model identities never reach the beat (issue 1)."""

    async def _inner() -> None:
        ids = await _seed_world()
        factory = _factory()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        other_snapshot = new_snapshot_id()
        item = await _submit(
            factory,
            gateway,
            ids["world"],
            "Wren waits",
            "e6-fix-ident-1",
            [
                {
                    "kind": "direct_attempt",
                    "explanation": "Wren waits.",
                    "character_id": str(ids["wren"]),
                    "family": "wait",
                    # A hostile or confused model reply: another actor, a
                    # forged snapshot, and a different family. The "move"
                    # family would fail validation on its own (no
                    # destination), so queuing proves the server stamped
                    # its own values before validating.
                    "action": {
                        "character_id": str(ids["ash"]),
                        "snapshot_id": str(other_snapshot),
                        "family": "move",
                    },
                }
            ],
        )
        assert item.status == InterventionStatus.QUEUED

        sealed = new_snapshot_id()
        planned = await service.plan_attempts(factory, ids["world"], sealed)
        assert len(planned) == 1
        attempt = planned[0]
        assert attempt.actor == ids["wren"]
        assert isinstance(attempt.intent, WaitAction)
        assert attempt.intent.character_id == ids["wren"]
        assert attempt.intent.snapshot_id == sealed

    _run(_inner())


def test_second_attempt_for_same_actor_fails_deterministically(migrated_db: None) -> None:
    """Two queued attempts for Wren leave none silently missing (issue 2)."""

    async def _inner() -> None:
        ids = await _seed_world()
        factory = _factory()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        first = await _submit(
            factory,
            gateway,
            ids["world"],
            "Wren waits",
            "e6-fix-dupe-1",
            [
                {
                    "kind": "direct_attempt",
                    "explanation": "Wren waits.",
                    "character_id": str(ids["wren"]),
                    "family": "wait",
                    "action": {},
                }
            ],
        )
        second = await _submit(
            factory,
            gateway,
            ids["world"],
            "Wren waits again",
            "e6-fix-dupe-2",
            [
                {
                    "kind": "direct_attempt",
                    "explanation": "Wren waits again.",
                    "character_id": str(ids["wren"]),
                    "family": "wait",
                    "action": {},
                }
            ],
        )
        planned = await service.plan_attempts(factory, ids["world"], new_snapshot_id())
        assert [p.actor for p in planned] == [ids["wren"]]

        states = []
        for item in (first, second):
            for step in await _steps_of(factory, item.id):
                states.append(step.status)
        # One attempt plans; the other is rejected with a reason. Both
        # are accounted for: nothing silently disappears.
        assert states.count(StepStatus.QUEUED) == 1
        assert states.count(StepStatus.FAILED) == 1
        reasons = [
            step.failure_reason
            for item in (first, second)
            for step in await _steps_of(factory, item.id)
            if step.status == StepStatus.FAILED
        ]
        assert len(reasons) == 1 and "already directed" in reasons[0]

    _run(_inner())


def test_gate_taken_before_effect_recovers_by_applying(migrated_db: None) -> None:
    """A claim with no outcome means a crashed claimer: apply (issue 3)."""

    async def _inner() -> None:
        ids = await _seed_world()
        factory = _factory()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        item = await _submit(
            factory,
            gateway,
            ids["world"],
            "Send Wren to Market",
            "e6-fix-gate-1",
            [_travel_step(ids["wren"], ids["market"])],
        )
        (step,) = await _steps_of(factory, item.id)
        assert await _claim_gate(factory, ids["world"], item.id, step.seq) is True

        chars = await _characters(factory, ids["world"])
        await service._apply_effect_step(factory, ids["world"], 1, step, item.id, chars)

        (done,) = await _steps_of(factory, item.id)
        assert done.status == StepStatus.COMPLETED
        assert done.result_activity_id is not None
        async with factory() as uow:
            actives = await uow.activities.list_active_for_world(ids["world"])
        mine = [a for a in actives if a.character_id == ids["wren"]]
        assert len(mine) == 1

    _run(_inner())


def test_effect_persisted_before_mark_is_adopted(migrated_db: None) -> None:
    """A crash between effect and mark adopts on recovery (issue 3)."""

    async def _inner() -> None:
        ids = await _seed_world()
        factory = _factory()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        item = await _submit(
            factory,
            gateway,
            ids["world"],
            "Send Wren to Market",
            "e6-fix-gate-2",
            [_travel_step(ids["wren"], ids["market"])],
        )
        (step,) = await _steps_of(factory, item.id)
        chars = await _characters(factory, ids["world"])
        # The crashed beat persisted the activity but never marked the step.
        activity_id = await service._start_directed_activity(
            factory, ids["world"], 1, step, step.targets, chars
        )
        assert await _claim_gate(factory, ids["world"], item.id, step.seq) is True

        await service._apply_effect_step(factory, ids["world"], 1, step, item.id, chars)

        (done,) = await _steps_of(factory, item.id)
        assert done.status == StepStatus.COMPLETED
        assert done.result_activity_id == activity_id
        async with factory() as uow:
            actives = await uow.activities.list_active_for_world(ids["world"])
        mine = [a for a in actives if a.character_id == ids["wren"]]
        assert [a.id for a in mine] == [activity_id]

    _run(_inner())


def test_overlapping_hook_application_converges_on_one_hook(migrated_db: None) -> None:
    """A racer overlapping an in-flight hook adopts it (issue 3)."""

    async def _inner() -> None:
        ids = await _seed_world()
        factory = _factory()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        item = await _submit(
            factory,
            gateway,
            ids["world"],
            "Trouble brews",
            "e6-fix-hook-1",
            [
                {
                    "kind": "propose_hook",
                    "explanation": "Trouble brews.",
                    "title": "The Grey Bell",
                    "purpose": "Trouble.",
                    "participant_ids": [str(ids["wren"])],
                }
            ],
        )
        (step,) = await _steps_of(factory, item.id)
        chars = await _characters(factory, ids["world"])
        # Owner A holds the gate and persists the hook; owner B overlaps
        # the gate-to-mark window and must adopt, not duplicate.
        assert await _claim_gate(factory, ids["world"], item.id, step.seq) is True
        await service._accept_hook(factory, ids["world"], 1, step, step.targets, chars)
        await service._apply_effect_step(factory, ids["world"], 1, step, item.id, chars)

        (done,) = await _steps_of(factory, item.id)
        assert done.status == StepStatus.COMPLETED
        async with factory() as uow:
            hooks = await uow.narrative.list_hooks_for_world(ids["world"])
        assert [h.title for h in hooks].count("The Grey Bell") == 1

    _run(_inner())


def test_distinct_directions_sharing_title_and_label_both_apply(migrated_db: None) -> None:
    """Same title/label across filings never conflates (issue 3)."""

    async def _inner() -> None:
        ids = await _seed_world()
        factory = _factory()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        for key in ("e6-fix-same-1", "e6-fix-same-2"):
            await _submit(
                factory,
                gateway,
                ids["world"],
                "Trouble brews",
                key,
                [
                    {
                        "kind": "propose_hook",
                        "explanation": "Trouble brews.",
                        "title": "The Grey Bell",
                        "purpose": "Trouble.",
                        "participant_ids": [str(ids["wren"])],
                    }
                ],
            )
        batch = await service.claim_for_boundary(factory, ids["world"], "e6-fix")
        await service.apply_batch(factory, ids["world"], 1, batch, set())
        async with factory() as uow:
            hooks = await uow.narrative.list_hooks_for_world(ids["world"])
        assert [h.title for h in hooks].count("The Grey Bell") == 2

        for key in ("e6-fix-same-3", "e6-fix-same-4"):
            await _submit(
                factory,
                gateway,
                ids["world"],
                "A cough spreads",
                key,
                [
                    {
                        "kind": "world_condition",
                        "explanation": "A cough spreads.",
                        "label": "Grey Cough",
                        "detail": "A harsh cough.",
                        "location_ids": [str(ids["hearth"])],
                        "severity": 2,
                        "duration_phases": 3,
                    }
                ],
            )
        batch = await service.claim_for_boundary(factory, ids["world"], "e6-fix")
        await service.apply_batch(factory, ids["world"], 1, batch, set())
        async with factory() as uow:
            conditions = await uow.conditions.list_active_for_world(ids["world"])
        assert [c.public_label for c in conditions].count("Grey Cough") == 2

    _run(_inner())


def test_override_step_key_replays_the_same_event(migrated_db: None) -> None:
    """A step-derived override key collides instead of duplicating (issue 3)."""

    async def _inner() -> None:
        ids = await _seed_world()
        factory = _factory()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        item = await _submit(
            factory,
            gateway,
            ids["world"],
            "Wren catches breath",
            "e6-fix-override-1",
            [
                {
                    "kind": "override_character",
                    "explanation": "Wren catches breath.",
                    "character_id": str(ids["wren"]),
                    "stamina": 50,
                }
            ],
        )
        (step,) = await _steps_of(factory, item.id)
        first = await service._apply_override_step(factory, ids["world"], 1, step, item.id)
        second = await service._apply_override_step(factory, ids["world"], 1, step, item.id)
        assert first == second

    _run(_inner())
