"""Intervention queue proof for E6 (Director/God interventions).

Covers the packet proof at the service boundary with scripted model
output: typed travel/spar/plague plans queue, same-key resubmission
replays without duplicating, roles and modes are enforced,
clarification/edit/cancel behave, and claiming plus applying produces
auditable permitted effects.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import pytest

from worldsim.application import interventions as service
from worldsim.application.interventions import Scope
from worldsim.domain.activities import TravelRoute
from worldsim.domain.characters import Character
from worldsim.domain.enums import UserRole
from worldsim.domain.errors import DomainError, ErrorCode
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


async def _seed_travel_world() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            hearth = new_location_id()
            market = new_location_id()
            wren = new_character_id()
            ash = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="e6-test"))
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth", capacity=4))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market", capacity=4))
            # Travel requires connected locations; the return leg needs
            # the reverse route as well.
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


def _travel_plan(wren: UUID, market: UUID) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "steps": [
                {
                    "kind": "direct_activity",
                    "explanation": "Wren walks to the Market.",
                    "character_id": str(wren),
                    "activity": "travel",
                    "to_location_id": str(market),
                }
            ],
            "clarification": "",
        }
    )


def test_deity_travel_queues_and_applies(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        gateway.enqueue_text(_travel_plan(ids["wren"], ids["market"]))
        factory = _factory()
        item = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DEITY,
            InterventionMode.FORCE,
            "Send Wren to the Market",
            Scope(),
            "e6-travel-1",
        )
        assert item.status == InterventionStatus.QUEUED
        async with factory() as uow:
            steps = await uow.interventions.list_steps(item.id)
        assert len(steps) == 1
        assert steps[0].status == StepStatus.QUEUED

        batch = await service.claim_for_boundary(factory, ids["world"], "e6-test")
        assert len(batch) == 1
        directed = await service.apply_batch(factory, ids["world"], 1, batch, set())
        assert directed == {}
        async with factory() as uow:
            steps = await uow.interventions.list_steps(item.id)
            assert steps[0].status == StepStatus.COMPLETED
            assert steps[0].result_activity_id is not None
            current = await uow.interventions.get_intervention(item.id)
            assert current.status == InterventionStatus.COMPLETED
            actives = await uow.activities.list_active_for_world(ids["world"])
        travel = [a for a in actives if a.character_id == ids["wren"]]
        assert len(travel) == 1
        assert travel[0].payload.get("to_location_id") == str(ids["market"])

    _run(_inner())


def test_same_key_replays_without_duplicating(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        # One scripted plan: a genuine second interpretation would raise
        # "no scripted fake behavior", so consuming none proves the replay.
        gateway.enqueue_text(_travel_plan(ids["wren"], ids["market"]))
        factory = _factory()
        first = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DEITY,
            InterventionMode.FORCE,
            "Send Wren to the Market",
            Scope(),
            "e6-replay-1",
        )
        second = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DEITY,
            InterventionMode.FORCE,
            "Send Wren to the Market",
            Scope(),
            "e6-replay-1",
        )
        assert second.id == first.id
        async with factory() as uow:
            steps = await uow.interventions.list_steps(first.id)
        assert len(steps) == 1

    _run(_inner())


def test_multileg_travel_chains_across_boundaries(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        plan = json.dumps(
            {
                "schema_version": 1,
                "steps": [
                    {
                        "kind": "direct_activity",
                        "explanation": "Wren walks to the Market.",
                        "character_id": str(ids["wren"]),
                        "activity": "travel",
                        "to_location_id": str(ids["market"]),
                    },
                    {
                        "kind": "direct_activity",
                        "explanation": "Wren walks back to the Hearth.",
                        "character_id": str(ids["wren"]),
                        "activity": "travel",
                        "to_location_id": str(ids["hearth"]),
                    },
                ],
                "clarification": "",
            }
        )
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        gateway.enqueue_text(plan)
        factory = _factory()
        item = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DEITY,
            InterventionMode.FORCE,
            "Wren paces between Hearth and Market",
            Scope(),
            "e6-legs-1",
        )
        async with factory() as uow:
            steps = await uow.interventions.list_steps(item.id)
        assert [s.seq for s in steps] == [0, 1]
        assert steps[1].targets.get("after_seq") == 0
        batch = await service.claim_for_boundary(factory, ids["world"], "e6-test")
        await service.apply_batch(factory, ids["world"], 1, batch, set())
        async with factory() as uow:
            steps = await uow.interventions.list_steps(item.id)
            current = await uow.interventions.get_intervention(item.id)
        # First leg completed; the second waits while Wren is travelling.
        assert steps[0].status == StepStatus.COMPLETED
        assert steps[1].status == StepStatus.QUEUED
        assert current.status == InterventionStatus.EXECUTING

    _run(_inner())


def test_roles_and_modes_are_enforced(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        factory = _factory()
        with pytest.raises(DomainError) as exc:
            await service.submit(
                factory,
                gateway,
                ids["world"],
                UserRole.WATCHER,
                InterventionMode.INFLUENCE,
                "Watchers cannot direct",
                Scope(),
                "e6-deny-1",
            )
        assert exc.value.code == ErrorCode.FORBIDDEN
        with pytest.raises(DomainError) as exc:
            await service.submit(
                factory,
                gateway,
                ids["world"],
                UserRole.DIRECTOR,
                InterventionMode.FORCE,
                "Direct mode cannot force",
                Scope(),
                "e6-deny-2",
            )
        assert exc.value.code == ErrorCode.FORBIDDEN
        # A director travel plan validates as FAILED: Direct mode proposes
        # hooks and arcs; forcing needs God mode.
        gateway.enqueue_text(_travel_plan(ids["wren"], ids["market"]))
        item = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DIRECTOR,
            InterventionMode.INFLUENCE,
            "Send Wren to the Market",
            Scope(),
            "e6-deny-3",
        )
        assert item.status == InterventionStatus.FAILED
        assert "God mode" in item.failure_reason

    _run(_inner())


def test_unmappable_text_needs_clarification(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        gateway.enqueue_text("not a plan at all")
        factory = _factory()
        item = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DIRECTOR,
            InterventionMode.INFLUENCE,
            "Do something vague",
            Scope(),
            "e6-clarify-1",
        )
        assert item.status == InterventionStatus.NEEDS_CLARIFICATION
        assert item.failure_reason != ""
        async with factory() as uow:
            assert await uow.interventions.list_steps(item.id) == []

    _run(_inner())


def test_edit_conflicts_and_cancel_preserves_history(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        gateway.enqueue_text("not a plan at all")
        factory = _factory()
        item = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DIRECTOR,
            InterventionMode.INFLUENCE,
            "Do something vague",
            Scope(),
            "e6-edit-1",
        )
        assert item.status == InterventionStatus.NEEDS_CLARIFICATION
        with pytest.raises(DomainError) as exc:
            await service.edit_text(
                factory, gateway, item.id, item.version + 99, "clearer text", Scope()
            )
        assert exc.value.code == ErrorCode.VERSION_CONFLICT
        cancelled = await service.cancel(factory, item.id, item.version)
        assert cancelled.status == InterventionStatus.CANCELLED
        with pytest.raises(DomainError) as exc:
            await service.cancel(factory, item.id, cancelled.version)
        assert exc.value.code == ErrorCode.PRECONDITION_FAILED

    _run(_inner())


def test_spar_attempt_directs_for_advance(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        plan = json.dumps(
            {
                "schema_version": 1,
                "steps": [
                    {
                        "kind": "direct_attempt",
                        "explanation": "Wren spars with Ash.",
                        "character_id": str(ids["wren"]),
                        "family": "spar",
                        "action": {
                            "character_id": str(ids["wren"]),
                            "target_character_id": str(ids["ash"]),
                            "snapshot_id": str(new_snapshot_id()),
                        },
                    }
                ],
                "clarification": "",
            }
        )
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        gateway.enqueue_text(plan)
        factory = _factory()
        item = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DEITY,
            InterventionMode.FORCE,
            "Wren spars with Ash",
            Scope(),
            "e6-spar-1",
        )
        assert item.status == InterventionStatus.QUEUED
        batch = await service.claim_for_boundary(factory, ids["world"], "e6-test")
        directed = await service.apply_batch(factory, ids["world"], 1, batch, set())
        assert set(directed) == {ids["wren"]}
        assert directed[ids["wren"]].family == "spar"
        async with factory() as uow:
            steps = await uow.interventions.list_steps(item.id)
            assert steps[0].status == StepStatus.COMPLETED

    _run(_inner())


def test_world_condition_persists(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed_travel_world()
        plan = json.dumps(
            {
                "schema_version": 1,
                "steps": [
                    {
                        "kind": "world_condition",
                        "explanation": "A cough spreads through the Hearth.",
                        "label": "Hearth cough",
                        "detail": "A mild plague for the packet proof.",
                        "location_ids": [str(ids["hearth"])],
                        "severity": 2,
                        "duration_phases": 3,
                    }
                ],
                "clarification": "",
            }
        )
        gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
        gateway.enqueue_text(plan)
        factory = _factory()
        item = await service.submit(
            factory,
            gateway,
            ids["world"],
            UserRole.DEITY,
            InterventionMode.FORCE,
            "A cough spreads through the Hearth",
            Scope(),
            "e6-plague-1",
        )
        assert item.status == InterventionStatus.QUEUED
        batch = await service.claim_for_boundary(factory, ids["world"], "e6-test")
        await service.apply_batch(factory, ids["world"], 1, batch, set())
        async with factory() as uow:
            conditions = await uow.conditions.list_active_for_world(ids["world"])
            current = await uow.interventions.get_intervention(item.id)
        assert [c.public_label for c in conditions] == ["Hearth cough"]
        assert current.status == InterventionStatus.COMPLETED

    _run(_inner())
