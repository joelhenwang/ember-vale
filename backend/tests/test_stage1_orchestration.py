"""Three-phase autonomous orchestration checks (owned by S1-ORCH-001)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text as sql_text

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.orchestration.stage1 import Stage1Orchestrator
from worldsim.application.ports.model_gateway import CompletionRequest, ProbeResult
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.commands import CommunicateAction
from worldsim.domain.enums import NarrationKind, UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    derive_intent_id,
    new_card_id,
    new_character_id,
    new_location_id,
    new_role_grant_id,
    new_world_id,
)
from worldsim.domain.narration import NarrationBeat
from worldsim.domain.phases import PhaseRun
from worldsim.domain.roles import RoleGrant
from worldsim.domain.stories import StoryInitialSetup
from worldsim.domain.time import absolute_index
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import (
    CHARACTER_FAKE_PROFILE,
    DIRECTOR_FAKE_PROFILE,
    NARRATOR_FAKE_PROFILE,
    REACTION_FAKE_PROFILE,
    RESOLVER_FAKE_PROFILE,
)
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import NullExporter

PROFILES = {
    "character": CHARACTER_FAKE_PROFILE,
    "reaction": REACTION_FAKE_PROFILE,
    "resolver": RESOLVER_FAKE_PROFILE,
    "narrator": NARRATOR_FAKE_PROFILE,
    "director": DIRECTOR_FAKE_PROFILE,
}


async def _seed() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Orch", seed_version="s1-test"))
            hearth, market = new_location_id(), new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market"))
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name, version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=place,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.versions.ensure(wid, wid, "world")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash, "hearth": hearth, "market": market}
    finally:
        await engine.dispose()


def _wait_json(actor: UUID, snapshot: UUID) -> str:
    return json.dumps({"family": "wait", "character_id": str(actor), "snapshot_id": str(snapshot)})


def _beats_json() -> str:
    return json.dumps([{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}])


def _role_gateways(
    ids: dict[str, UUID], narrator_text: str | None = None
) -> dict[str, FakeGateway]:
    snapshot_cache: dict[int, UUID] = {}

    def snapshot_for(index: int) -> UUID:
        if index not in snapshot_cache:
            snapshot_cache[index] = derive_snapshot_id(derive_run_id(ids["world"], index))
        return snapshot_cache[index]

    def character_route(request: CompletionRequest) -> str | None:
        for index in (1, 2, 3):
            snapshot = snapshot_for(index)
            if "Wren" in request.prompt:
                return _wait_json(ids["wren"], snapshot)
            if "Ash" in request.prompt:
                return _wait_json(ids["ash"], snapshot)
        return None

    def reaction_route(request: CompletionRequest) -> str | None:
        for index in (1, 2, 3):
            snapshot = snapshot_for(index)
            if "Wren" in request.prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": str(snapshot),
                        "focus": "Ash",
                    }
                )
            if "Ash" in request.prompt:
                return _wait_json(ids["ash"], snapshot)
        return None

    character = FakeGateway(profile=CHARACTER_FAKE_PROFILE, route=character_route)
    reaction = FakeGateway(profile=REACTION_FAKE_PROFILE, route=reaction_route)
    resolver = FakeGateway(
        profile=RESOLVER_FAKE_PROFILE,
        default_text=json.dumps(
            {
                "outcome": "success",
                "effects": [
                    {
                        "schema_version": 1,
                        "affected_ids": [str(ids["wren"])],
                        "expected_versions": {str(ids["wren"]): 0},
                        "effect_type": "record_observation",
                        "observer_character_id": str(ids["wren"]),
                        "facts": [{"key": "greeting", "value": "dawn patrol"}],
                    }
                ],
                "rationale": "Wren hears the patrol call.",
            }
        ),
    )
    narrator = FakeGateway(
        profile=NARRATOR_FAKE_PROFILE, default_text=narrator_text or _beats_json()
    )
    director = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
    return {
        "character": character,
        "reaction": reaction,
        "resolver": resolver,
        "narrator": narrator,
        "director": director,
    }


def _orchestrator(
    gateways: dict[str, FakeGateway],
    hook: Callable[[str], None] | None = None,
) -> Stage1Orchestrator:
    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731

    def _factory_role(role: str) -> FakeGateway:
        return gateways[role]

    return Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory, pre_commit_hook=hook),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        _factory_role,
        PROFILES,
        fault_hook=hook,
    )


def test_three_phases_complete_with_shared_snapshots(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        reports = await orch.advance_three_phases(ids["world"], 1)
        assert len(reports) == 3
        for report in reports:
            assert not report.duplicate
            assert len(report.scenes) >= 1
            assert all(s.narration in ("narrated", "fallback") for s in report.scenes)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                world = await uow.worlds.get(ids["world"])
                assert absolute_index(world.day, world.phase) == 3
                assert await uow.events.count_events(ids["world"]) >= 6
                run = await uow.phases.get_run(reports[0].run_id)
                assert run.state.value == "completed"
                snapshot = await uow.phases.get_snapshot(reports[1].snapshot_id)
                assert len(snapshot.characters) == 2
                calls = await uow.traces.list_for_phase_run(reports[2].run_id)
                assert len(calls) >= 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_duplicate_phase_replays_without_new_canon(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        first = await orch.advance_phase(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                before = await uow.events.count_events(ids["world"])
            second = await orch.advance_phase(ids["world"], 1)
            assert second.duplicate
            assert [s.event_id for s in second.scenes] == [s.event_id for s in first.scenes]
            # A fresh phase reports per-stage wall time; a replay does no work.
            stages = {"probe", "director", "decide", "react", "resolve", "narrate", "scenes"}
            assert stages | {"total"} <= set(first.timings_ms)
            assert all(ms >= 0 for ms in first.timings_ms.values())
            assert first.timings_ms["total"] >= first.timings_ms["scenes"]
            assert second.timings_ms == {}
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == before
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_advance_refuses_second_open_run(migrated_db: None) -> None:
    """Overlapping advances cannot stack another open run.

    A later request for a different index while the first run is
    still active must fail closed (409) instead of creating a
    second open run that breaks reconciliation later.
    """
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        engine = create_engine(Settings())
        try:
            # Simulate an advance still in flight on another path.
            async with create_unit_of_work(engine) as uow:
                await uow.phases.create_run(
                    PhaseRun(
                        id=derive_run_id(ids["world"], 2),
                        world_id=ids["world"],
                        absolute_index=2,
                    )
                )
                await uow.commit()
            with pytest.raises(DomainError) as caught:
                await orch.advance_phase(ids["world"], 1)
            assert caught.value.code is ErrorCode.PRECONDITION_FAILED
            async with create_unit_of_work(engine) as uow:
                open_run = await uow.phases.find_open_run(ids["world"])
                assert open_run is not None and open_run.absolute_index == 2
                try:
                    await uow.phases.get_run(derive_run_id(ids["world"], 1))
                except DomainError:
                    pass
                else:
                    raise AssertionError("second open run must not be created")
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_restart_during_commit_resolves_once(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        fired: list[str] = []

        def _hook(point: str) -> None:
            if point == "after_scene" and not fired:
                fired.append(point)
                raise RuntimeError("injected at after_scene")

        orch = _orchestrator(gateways, hook=_hook)
        with pytest.raises(RuntimeError, match="injected"):
            await orch.advance_phase(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                mid = await uow.events.count_events(ids["world"])
            assert mid >= 1
            orch = _orchestrator(gateways)
            report = await orch.advance_phase(ids["world"], 1)
            assert not report.duplicate
            async with create_unit_of_work(engine) as uow:
                after = await uow.events.count_events(ids["world"])
                # One tick plus one event per committed scene, never doubled.
                assert after == mid + len(report.scenes)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_restart_before_narration_heals(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        fired: list[str] = []

        def _hook(point: str) -> None:
            if point == "before_narration" and not fired:
                fired.append(point)
                raise RuntimeError("injected at before_narration")

        orch = _orchestrator(gateways, hook=_hook)
        with pytest.raises(RuntimeError, match="injected"):
            await orch.advance_phase(ids["world"], 1)
        orch = _orchestrator(gateways)
        report = await orch.advance_phase(ids["world"], 1)
        assert all(s.narration in ("narrated", "fallback") for s in report.scenes)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                for scene in report.scenes:
                    assert await uow.scenes.narrations_for_event(scene.event_id)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_player_substitution_controls_attempt(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)

        def _ash_only(request: CompletionRequest) -> str | None:
            if "Ash" in request.prompt:
                raise AssertionError("Ash is player-controlled; no model call expected")
            if "Wren" in request.prompt:
                snapshot = derive_snapshot_id(derive_run_id(ids["world"], 1))
                return _wait_json(ids["wren"], snapshot)
            return None

        gateways["character"].route = _ash_only
        orch = _orchestrator(gateways)
        player = {
            ids["ash"]: CommunicateAction(
                character_id=ids["ash"],
                snapshot_id=derive_snapshot_id(derive_run_id(ids["world"], 1)),
                target_character_id=ids["wren"],
                topic="dawn patrol",
            )
        }
        # No grant: pass the request-time submitter as the HTTP route would.
        report = await orch.advance_phase(
            ids["world"], 1, player, submitter_id=ids["ash"]
        )
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                intent = await uow.scenes.get_intent(
                    derive_intent_id(
                        ids["world"],
                        report.snapshot_id,
                        ids["ash"],
                    )
                )
                assert intent.action.family.value == "communicate"
                assert intent.action.topic == "dawn patrol"  # type: ignore[union-attr]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_pause_blocks_until_resume(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        run_id = derive_run_id(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.phases.create_run(
                    PhaseRun(id=run_id, world_id=ids["world"], absolute_index=1)
                )
                await uow.commit()
        finally:
            await engine.dispose()
        await orch.pause_phase(run_id)
        with pytest.raises(DomainError) as excinfo:
            await orch.advance_phase(ids["world"], 1)
        assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
        await orch.resume_phase(run_id)
        report = await orch.advance_phase(ids["world"], 1)
        assert not report.duplicate

    asyncio.run(_inner())


class _DeadGateway:
    profile = CHARACTER_FAKE_PROFILE

    async def complete(self, request: CompletionRequest) -> Any:
        raise AssertionError("must not be called")

    async def probe(self) -> ProbeResult:
        return ProbeResult(ok=False, profile="dead", latency_ms=0, detail="quota exhausted")

    async def embed(self, request: Any) -> Any:
        raise AssertionError("must not be called")


def test_probe_gate_blocks_batch_before_commit(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        dead = _DeadGateway()

        def _gateway_for(role: str) -> FakeGateway | _DeadGateway:
            return dead if role == "character" else gateways[role]

        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            orch = Stage1Orchestrator(
                factory,
                CanonicalTransaction(factory),
                TaskService(factory),
                TraceService(factory, NullExporter()),
                _gateway_for,
                PROFILES,
            )
            with pytest.raises(DomainError) as excinfo:
                await orch.advance_phase(ids["world"], 1)
            assert excinfo.value.code is ErrorCode.PRECONDITION_FAILED
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == 0
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_narration_failure_completes_phase(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        from worldsim.application.ports.model_gateway import ModelUnavailableError

        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        # Default text would mask the outage; clear it for this phase.
        gateways["narrator"].default_text = None
        orch = _orchestrator(gateways)
        report = await orch.advance_phase(ids["world"], 1)
        assert not report.duplicate
        assert all(s.narration == "fallback" for s in report.scenes)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) >= 2
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_derived_ids_converge() -> None:
    world, snapshot, author = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first = derive_intent_id(world, snapshot, author)
    assert derive_intent_id(world, snapshot, author) == first
    assert derive_intent_id(world, snapshot, uuid.uuid4()) != first


def test_concurrent_admission_leaves_single_open_run(migrated_db: None) -> None:
    """Competing advances cannot stack open runs, even when overlapping.

    Two threads drive indexes 1 and 2 with separate engines and
    rendezvous at admission entry, so the admission transactions truly
    overlap. Index 1 must complete; index 2 must fail closed (4xx);
    no second run row may exist; a later index 2 advance (the
    reconciliation path) must then succeed.
    """
    import threading

    from worldsim.application.orchestration.stage1 import Stage1PhaseReport

    entered: list[str] = []
    barrier = threading.Barrier(2, timeout=120)

    def _hook(point: str) -> None:
        if point == "before_admission":
            entered.append(point)
            barrier.wait(timeout=120)

    async def _seed_once() -> dict[str, Any]:
        return await _seed()

    ids = asyncio.run(_seed_once())
    world_id = ids["world"]
    outcomes: dict[str, object] = {}

    def _advance(index: int, key: str) -> None:
        async def _run() -> None:
            orch = _orchestrator(_role_gateways(ids), hook=_hook)
            try:
                outcomes[key] = await orch.advance_phase(world_id, index)
            except DomainError as exc:
                outcomes[key] = exc

        asyncio.run(_run())

    first = threading.Thread(target=_advance, args=(1, "first"))
    second = threading.Thread(target=_advance, args=(2, "second"))
    first.start()
    second.start()
    first.join(timeout=300)
    second.join(timeout=300)
    assert not first.is_alive(), "index 1 advance hung"
    assert not second.is_alive(), "index 2 advance hung"
    assert len(entered) == 2, "both admissions must overlap at the barrier"

    async def _verify() -> None:
        won = outcomes["first"]
        assert isinstance(won, Stage1PhaseReport), outcomes
        assert not won.duplicate
        lost = outcomes["second"]
        assert isinstance(lost, DomainError), outcomes
        # Either refusal is fail-closed, depending on which admission
        # wins the world-row lock: a too-early index trips the clock
        # check, a too-late one trips the previous/open checks.
        assert lost.code in (
            ErrorCode.PRECONDITION_FAILED,
            ErrorCode.VALIDATION_FAILED,
        ), lost
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.phases.find_open_run(world_id) is None
                try:
                    await uow.phases.get_run(derive_run_id(world_id, 2))
                except DomainError:
                    pass
                else:
                    raise AssertionError("second open run must not exist")
        finally:
            await engine.dispose()
        orch = _orchestrator(_role_gateways(ids))
        followup = await orch.advance_phase(world_id, 2)
        assert not followup.duplicate

    asyncio.run(_verify())


async def _set_grant(ids: dict[str, UUID], role: str, character: UUID | None) -> None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await uow.roles.set_grant(
                RoleGrant(
                    id=new_role_grant_id(),
                    world_id=ids["world"],
                    role=UserRole(role),
                    character_id=character,
                    granted_absolute=0,
                )
            )
            await uow.commit()
    finally:
        await engine.dispose()


def _agency_gateways(ids: dict[str, UUID]) -> dict[str, FakeGateway]:
    """Fake roles where any model proposal for Wren is a test failure."""
    gateways = _role_gateways(ids)
    base_decide = gateways["character"].route

    def _no_wren_decision(request: CompletionRequest) -> str | None:
        # Decision prompts name only the decider in the identity block;
        # later-phase history may mention anyone anywhere else.
        if "identity>>Wren" in request.prompt:
            raise AssertionError("controlled Wren must not reach model decision")
        assert base_decide is not None
        return base_decide(request)

    def _ash_answers(request: CompletionRequest) -> str | None:
        # Reaction prompts name every participant; the identity block names the reactor.
        if "identity>>Wren" in request.prompt:
            raise AssertionError("controlled Wren must not reach model reaction")
        if "identity>>Ash" in request.prompt:
            return json.dumps(
                {
                    "family": "communicate",
                    "character_id": str(ids["ash"]),
                    "snapshot_id": "00000000-0000-0000-0000-000000000000",
                    "target_character_id": str(ids["wren"]),
                    "topic": '"Dawn patrol passed at first light."',
                }
            )
        return None

    gateways["character"].route = _no_wren_decision
    gateways["reaction"].route = _ash_answers
    return gateways


def _wren_ask(ids: dict[str, UUID]) -> dict[UUID, CommunicateAction]:
    return {
        ids["wren"]: CommunicateAction(
            character_id=ids["wren"],
            snapshot_id=derive_snapshot_id(derive_run_id(ids["world"], 1)),
            target_character_id=ids["ash"],
            topic="dawn patrol",
        )
    }


def test_controlled_character_has_no_model_proposals(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        orch = _orchestrator(_agency_gateways(ids))
        report = await orch.advance_phase(ids["world"], 1, _wren_ask(ids))
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.get_run(report.run_id)
                assert run.state.value == "completed"
                intent = await uow.scenes.get_intent(
                    derive_intent_id(ids["world"], report.snapshot_id, ids["wren"])
                )
                assert intent.action.family.value == "communicate"
                assert intent.action.topic == "dawn patrol"  # type: ignore[union-attr]
                reactions = []
                for scene in await uow.scenes.list_for_run(report.run_id):
                    reactions.extend(await uow.scenes.reactions_for_scene(scene.id))
                ash_answers = [
                    r for r in reactions if r.reactor_character_id == ids["ash"]
                ]
                assert len(ash_answers) == 1
                assert ash_answers[0].action.topic.startswith('"')  # type: ignore[union-attr]
                assert not [r for r in reactions if r.reactor_character_id == ids["wren"]]
                calls = await uow.traces.list_for_phase_run(report.run_id)
                assert not [
                    c
                    for c in calls
                    if c.role in ("character_decision", "reaction")
                    and c.actor_id == ids["wren"]
                ]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_controlled_ownership_survives_reload_and_retry(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        gateways = _agency_gateways(ids)
        first = await _orchestrator(gateways).advance_phase(ids["world"], 1, _wren_ask(ids))
        assert not first.duplicate
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                before = await uow.events.count_events(ids["world"])
            replay = await _orchestrator(gateways).advance_phase(ids["world"], 1)
            assert replay.duplicate
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == before
            # Fresh orchestrator, no player input: Wren still gets nothing.
            second = await _orchestrator(gateways).advance_phase(ids["world"], 2)
            assert not second.duplicate
            async with create_unit_of_work(engine) as uow:
                try:
                    await uow.scenes.get_intent(
                        derive_intent_id(ids["world"], second.snapshot_id, ids["wren"])
                    )
                except DomainError:
                    pass
                else:
                    raise AssertionError("controlled Wren must have no model intent")
                calls = await uow.traces.list_for_phase_run(second.run_id)
                assert not [
                    c
                    for c in calls
                    if c.role in ("character_decision", "reaction")
                    and c.actor_id == ids["wren"]
                ]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


async def _grant_ids(role: str | None, character: UUID | None = None) -> dict[str, UUID]:
    ids = await _seed()
    if role is not None:
        await _set_grant(ids, role, character)
    return ids


async def _resolve_grant(world_id: UUID) -> UUID | None:
    from worldsim.application.settings.resolution import resolve_controlled_character

    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return await resolve_controlled_character(uow, world_id)
    finally:
        await engine.dispose()


def test_resolve_controlled_character_reads_player_grant(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _grant_ids("player", None)
        assert await _resolve_grant(ids["world"]) is None
        await _set_grant(ids, "player", ids["wren"])
        assert await _resolve_grant(ids["world"]) == ids["wren"]

    asyncio.run(_inner())


def test_resolve_controlled_character_rejects_other_grants(migrated_db: None) -> None:
    async def _inner() -> None:
        assert await _resolve_grant((await _seed())["world"]) is None
        assert await _resolve_grant((await _grant_ids("watcher"))["world"]) is None

    asyncio.run(_inner())

def test_observer_setup_with_player_grant_protects(migrated_db: None) -> None:
    """The setup snapshot says observer; the active Player grant still owns Wren."""
    asyncio.run(_observer_setup_inner())


async def _observer_setup_inner() -> None:
    ids = await _seed()
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await uow.stories.put_setup(
                StoryInitialSetup(
                    world_id=ids["world"],
                    payload={"schema_version": 1, "mode": {"role": "watcher"}},
                    content_hash="agency-observer-setup",
                )
            )
            await uow.commit()
    finally:
        await engine.dispose()
    await _set_grant(ids, "player", ids["wren"])
    orch = _orchestrator(_agency_gateways(ids))
    report = await orch.advance_phase(ids["world"], 1, _wren_ask(ids))
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            run = await uow.phases.get_run(report.run_id)
            assert run.state.value == "completed"
            intent = await uow.scenes.get_intent(
                derive_intent_id(ids["world"], report.snapshot_id, ids["wren"])
            )
            assert intent.action.topic == "dawn patrol"  # type: ignore[union-attr]
            reactions = []
            for scene in await uow.scenes.list_for_run(report.run_id):
                reactions.extend(await uow.scenes.reactions_for_scene(scene.id))
            assert len([r for r in reactions if r.reactor_character_id == ids["ash"]]) == 1
            assert not [r for r in reactions if r.reactor_character_id == ids["wren"]]
            calls = await uow.traces.list_for_phase_run(report.run_id)
            assert not [
                c
                for c in calls
                if c.role in ("character_decision", "reaction") and c.actor_id == ids["wren"]
            ]
    finally:
        await engine.dispose()


def test_role_change_moves_protection_to_ash(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        first = await _orchestrator(_agency_gateways(ids)).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not first.duplicate
        await _set_grant(ids, "player", ids["ash"])
        second = await _orchestrator(_role_gateways(ids)).advance_phase(ids["world"], 2)
        assert not second.duplicate
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.get_run(second.run_id)
                assert run.state.value == "completed"
                intent = await uow.scenes.get_intent(
                    derive_intent_id(ids["world"], second.snapshot_id, ids["wren"])
                )
                assert intent.action.family.value == "wait"
                calls = await uow.traces.list_for_phase_run(second.run_id)
                assert [
                    c
                    for c in calls
                    if c.role == "character_decision" and c.actor_id == ids["wren"]
                ]
                assert not [
                    c
                    for c in calls
                    if c.role in ("character_decision", "reaction")
                    and c.actor_id == ids["ash"]
                ]
                try:
                    await uow.scenes.get_intent(
                        derive_intent_id(ids["world"], second.snapshot_id, ids["ash"])
                    )
                except DomainError:
                    pass
                else:
                    raise AssertionError("newly controlled Ash must have no model intent")
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_observer_grant_restores_automatic_behavior(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        first = await _orchestrator(_agency_gateways(ids)).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not first.duplicate
        await _set_grant(ids, "watcher", None)
        second = await _orchestrator(_role_gateways(ids)).advance_phase(ids["world"], 2)
        assert not second.duplicate
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                calls = await uow.traces.list_for_phase_run(second.run_id)
                for character_id in (ids["wren"], ids["ash"]):
                    assert [
                        c
                        for c in calls
                        if c.role == "character_decision" and c.actor_id == character_id
                    ]
                    intent = await uow.scenes.get_intent(
                        derive_intent_id(ids["world"], second.snapshot_id, character_id)
                    )
                    assert intent.action.family.value == "wait"
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_admitted_ownership_follows_grant_changed_during_preflight(
    migrated_db: None,
) -> None:
    """Admission captures the grant it runs under, not the one at advance start.

    The advance holds at provider preflight while the grant moves Wren to
    Ash; the admitted run must protect Ash and treat Wren as automatic.
    No player intent is filed, so both characters can only act by model
    decision: ownership alone decides who the model may move.
    """
    import threading

    from worldsim.application.orchestration.stage1 import Stage1PhaseReport

    async def _setup() -> dict[str, UUID]:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        return ids

    ids = asyncio.run(_setup())
    arrived = threading.Event()
    release = threading.Event()
    outcomes: dict[str, object] = {}

    def _hook(point: str) -> None:
        if point == "before_probe":
            arrived.set()
            assert release.wait(timeout=120)

    def _advance() -> None:
        async def _run() -> None:
            orch = _orchestrator(_role_gateways(ids), hook=_hook)
            try:
                outcomes["report"] = await orch.advance_phase(ids["world"], 1)
            except Exception as exc:  # recorded for the verdict
                outcomes["report"] = exc

        asyncio.run(_run())

    thread = threading.Thread(target=_advance)
    thread.start()
    assert arrived.wait(timeout=120)
    asyncio.run(_set_grant(ids, "player", ids["ash"]))
    release.set()
    thread.join(timeout=300)

    async def _verify() -> None:
        report = outcomes["report"]
        assert isinstance(report, Stage1PhaseReport)
        assert not report.duplicate
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.get_run(report.run_id)
                assert run.state.value == "completed"
                intent = await uow.scenes.get_intent(
                    derive_intent_id(ids["world"], report.snapshot_id, ids["wren"])
                )
                assert intent.action.family.value == "wait"
                calls = await uow.traces.list_for_phase_run(report.run_id)
                assert [
                    c
                    for c in calls
                    if c.role == "character_decision" and c.actor_id == ids["wren"]
                ]
                assert not [
                    c
                    for c in calls
                    if c.role in ("character_decision", "reaction")
                    and c.actor_id == ids["ash"]
                ]
                try:
                    await uow.scenes.get_intent(
                        derive_intent_id(ids["world"], report.snapshot_id, ids["ash"])
                    )
                except DomainError:
                    pass
                else:
                    raise AssertionError("newly controlled Ash must have no model intent")
        finally:
            await engine.dispose()

    asyncio.run(_verify())


def test_retry_after_grant_change_keeps_admitted_ownership(migrated_db: None) -> None:
    """A duplicate re-advance after a grant change adds no canon for the old run."""
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        first = await _orchestrator(_agency_gateways(ids)).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not first.duplicate
        await _set_grant(ids, "player", ids["ash"])
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                before_events = await uow.events.count_events(ids["world"])
                before_calls = len(await uow.traces.list_for_phase_run(first.run_id))
            replay = await _orchestrator(_agency_gateways(ids)).advance_phase(ids["world"], 1)
            assert replay.duplicate
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(ids["world"]) == before_events
                assert len(await uow.traces.list_for_phase_run(first.run_id)) == before_calls
        finally:
            await engine.dispose()

    asyncio.run(_inner())


async def _set_narration_mode(ids: dict[str, UUID], mode: str) -> None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await uow.worlds.put_config(ids["world"], "narration.mode", mode)
            await uow.commit()
    finally:
        await engine.dispose()


async def _beats_for_report(report: Any) -> list[NarrationBeat]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            beats: list[NarrationBeat] = []
            for outcome in report.scenes:
                beats.extend(await uow.scenes.narrations_for_event(outcome.event_id))
            return beats
    finally:
        await engine.dispose()


def test_structured_narration_skips_narrator_and_keeps_dialogue(
    migrated_db: None,
) -> None:
    """Structured mode issues no narrator call yet persists cited dialogue."""
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        await _set_narration_mode(ids, "structured")
        gateways = _agency_gateways(ids)
        report = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not report.duplicate
        assert report.scenes
        assert all(s.narration == "structured" for s in report.scenes)
        assert gateways["narrator"].calls == []
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                calls = await uow.traces.list_for_phase_run(report.run_id)
                assert not [c for c in calls if c.role == "narrator"]
        finally:
            await engine.dispose()
        beats = await _beats_for_report(report)
        assert beats
        dialogue = [b for b in beats if b.kind == NarrationKind.DIALOGUE]
        assert len(dialogue) == 1
        assert dialogue[0].speaker_id == ids["ash"]
        assert "Dawn patrol" in dialogue[0].text
        assert dialogue[0].cited_fact_keys

    asyncio.run(_inner())


def test_structured_dialogue_survives_reload_and_replay(migrated_db: None) -> None:
    """Structured beats reload identically and duplicate replay adds no canon."""
    async def _read_texts(report: Any) -> list[tuple[str, str]]:
        return [(b.kind.value, b.text) for b in await _beats_for_report(report)]

    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        await _set_narration_mode(ids, "structured")
        gateways = _agency_gateways(ids)
        first = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not first.duplicate
        before = await _read_texts(first)
        assert before
        assert any(kind == NarrationKind.DIALOGUE.value for kind, _text in before)
        replay = await _orchestrator(gateways).advance_phase(ids["world"], 1)
        assert replay.duplicate
        assert await _read_texts(first) == before
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                calls = await uow.traces.list_for_phase_run(first.run_id)
                assert not [c for c in calls if c.role == "narrator"]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_default_narration_mode_still_calls_narrator(migrated_db: None) -> None:
    """Without the opt-in flag the narrator gateway is invoked as before."""
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        gateways = _agency_gateways(ids)
        report = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not report.duplicate
        assert gateways["narrator"].calls != []
        assert all(s.narration in ("narrated", "fallback") for s in report.scenes)
        assert all(s.narration != "structured" for s in report.scenes)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                calls = await uow.traces.list_for_phase_run(report.run_id)
                assert [c for c in calls if c.role == "narrator"]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_structured_status_distinct_from_generation_failure(
    migrated_db: None,
) -> None:
    """Configured skips report "structured"; failed attempts never do."""
    from worldsim.application.ports.model_gateway import ModelUnavailableError

    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        await _set_narration_mode(ids, "structured")
        gateways = _agency_gateways(ids)
        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        report = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not report.duplicate
        assert all(s.narration == "structured" for s in report.scenes)
        assert gateways["narrator"].calls == []

        broken_ids = await _seed()
        await _set_grant(broken_ids, "player", broken_ids["wren"])
        broken_gateways = _agency_gateways(broken_ids)
        broken_gateways["narrator"].enqueue_error(ModelUnavailableError("down"))
        broken_gateways["narrator"].enqueue_error(ModelUnavailableError("down"))
        broken_gateways["narrator"].default_text = None
        broken = await _orchestrator(broken_gateways).advance_phase(
            broken_ids["world"], 1, _wren_ask(broken_ids)
        )
        assert not broken.duplicate
        assert broken_gateways["narrator"].calls != []
        assert all(s.narration != "structured" for s in broken.scenes)

    asyncio.run(_inner())


def test_structured_narration_defers_to_model_for_party_roster(
    migrated_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Party scenes always take the model path, even in structured mode."""
    from worldsim.application.commands.party import recruit_companion
    from worldsim.domain.rules.dnd import load_data

    root = Path(__file__).resolve().parent.parent.parent
    # Party narration loads the vendored SRD tables from the repo-root
    # content dir (as in production); run that beat from the repo root.
    monkeypatch.chdir(root)

    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        await _set_narration_mode(ids, "structured")
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                data = load_data(root / "content" / "dnd")
                await recruit_companion(
                    uow, data, ids["world"], "Lyra", "elf ranger, level 3"
                )
        finally:
            await engine.dispose()
        gateways = _agency_gateways(ids)
        report = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not report.duplicate
        assert gateways["narrator"].calls != []
        assert all(s.narration != "structured" for s in report.scenes)

    asyncio.run(_inner())


def test_structured_mode_saves_delayed_narrator_time(migrated_db: None) -> None:
    """Controlled delayed narrator, upstream constant: time saved, canon kept.

    The model narrator sleeps before answering; structured mode must save
    about that delay while committing the same scenes, outcomes, and events,
    with the committed answer voiced as attributed dialogue.
    """
    delay = 1.0

    async def _run_world(structured: bool) -> tuple[Any, Any, Any, float]:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        if structured:
            await _set_narration_mode(ids, "structured")
        gateways = _agency_gateways(ids)
        narrator = gateways["narrator"]
        spent = {"seconds": 0.0}
        original = narrator.complete

        async def _delayed(request: CompletionRequest) -> Any:
            start = perf_counter()
            try:
                await asyncio.sleep(delay)
                return await original(request)
            finally:
                spent["seconds"] += perf_counter() - start

        narrator.complete = _delayed  # type: ignore[method-assign]
        report = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        return ids, gateways, report, spent["seconds"]

    async def _inner() -> None:
        _ids_a, _gates_a, rep_a, spent_a = await _run_world(False)
        ids_b, gates_b, rep_b, spent_b = await _run_world(True)
        # Controlled timing only: the sleep-accounted narrator time is
        # deterministic, unlike a wall-clock comparison of two
        # database-backed runs. The half-delay margin absorbs float
        # rounding at the sleep boundary; without the injected sleep the
        # accounted time would be milliseconds. Observed walls (model
        # 1.70s, structured 0.67s) are recorded in
        # docs/evidence/structured-narration-001.
        assert spent_a >= 0.5 * delay
        assert spent_a > spent_b
        assert gates_b["narrator"].calls == []
        assert spent_b == 0.0
        assert [s.resolution_outcome for s in rep_a.scenes] == [
            s.resolution_outcome for s in rep_b.scenes
        ]
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                assert await uow.events.count_events(rep_a.world_id) == (
                    await uow.events.count_events(rep_b.world_id)
                )
        finally:
            await engine.dispose()
        beats = await _beats_for_report(rep_b)
        dialogue = [b for b in beats if b.kind == NarrationKind.DIALOGUE]
        assert len(dialogue) == 1
        assert dialogue[0].speaker_id == ids_b["ash"]

    asyncio.run(_inner())


async def _stored_narration_statuses(report: Any) -> list[str | None]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return [
                (await uow.scenes.get_scene(outcome.scene_id)).narration_status
                for outcome in report.scenes
            ]
    finally:
        await engine.dispose()


async def _null_stored_narration_statuses(report: Any) -> None:
    """Simulate legacy scene rows that predate the narration-status record."""
    engine = create_engine(Settings())
    try:
        async with engine.connect() as conn:
            for outcome in report.scenes:
                await conn.execute(
                    sql_text("UPDATE scene SET narration_status = NULL WHERE id = :id"),
                    {"id": outcome.scene_id},
                )
            await conn.commit()
    finally:
        await engine.dispose()


async def _canon_counts(ids: dict[str, UUID], run_id: UUID) -> tuple[int, int]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return (
                await uow.events.count_events(ids["world"]),
                len(await uow.traces.list_for_phase_run(run_id)),
            )
    finally:
        await engine.dispose()


def test_duplicate_replay_returns_stored_structured_status(
    migrated_db: None,
) -> None:
    """Duplicate replays report the recorded source, never infer narrated."""
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        await _set_narration_mode(ids, "structured")
        gateways = _agency_gateways(ids)
        first = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not first.duplicate
        assert first.scenes
        assert all(s.narration == "structured" for s in first.scenes)
        stored = await _stored_narration_statuses(first)
        assert stored and all(s == "structured" for s in stored)
        before = await _canon_counts(ids, first.run_id)
        replay = await _orchestrator(gateways).advance_phase(ids["world"], 1)
        assert replay.duplicate
        assert [s.narration for s in replay.scenes] == [
            s.narration for s in first.scenes
        ]
        assert await _canon_counts(ids, first.run_id) == before

    asyncio.run(_inner())


def test_duplicate_replay_returns_stored_model_and_fallback_statuses(
    migrated_db: None,
) -> None:
    """Recorded narrated/fallback sources replay verbatim, not as narrated."""
    from worldsim.application.ports.model_gateway import ModelUnavailableError

    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        gateways = _agency_gateways(ids)
        first = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not first.duplicate
        assert gateways["narrator"].calls != []
        stored = await _stored_narration_statuses(first)
        assert stored and all(s in ("narrated", "fallback") for s in stored)
        replay = await _orchestrator(gateways).advance_phase(ids["world"], 1)
        assert replay.duplicate
        assert [s.narration for s in replay.scenes] == [
            s.narration for s in first.scenes
        ]

        broken_ids = await _seed()
        await _set_grant(broken_ids, "player", broken_ids["wren"])
        broken_gateways = _agency_gateways(broken_ids)
        broken_gateways["narrator"].enqueue_error(ModelUnavailableError("down"))
        broken_gateways["narrator"].enqueue_error(ModelUnavailableError("down"))
        broken_gateways["narrator"].default_text = None
        broken = await _orchestrator(broken_gateways).advance_phase(
            broken_ids["world"], 1, _wren_ask(broken_ids)
        )
        assert not broken.duplicate
        assert all(s.narration == "fallback" for s in broken.scenes)
        broken_stored = await _stored_narration_statuses(broken)
        assert broken_stored and all(s == "fallback" for s in broken_stored)
        broken_replay = await _orchestrator(broken_gateways).advance_phase(
            broken_ids["world"], 1
        )
        assert broken_replay.duplicate
        assert all(s.narration == "fallback" for s in broken_replay.scenes)

    asyncio.run(_inner())


def _talking_gateways(ids: dict[str, UUID]) -> dict[str, FakeGateway]:
    """Autonomous gateways where Ash communicates (never a quiet phase)."""
    gateways = _role_gateways(ids)
    snapshot = derive_snapshot_id(derive_run_id(ids["world"], 1))

    def _decide(request: CompletionRequest) -> str | None:
        if "identity>>Ash" in request.prompt:
            return json.dumps(
                {
                    "family": "communicate",
                    "character_id": str(ids["ash"]),
                    "snapshot_id": str(snapshot),
                    "target_character_id": str(ids["wren"]),
                    "topic": "dawn patrol",
                }
            )
        if "identity>>Wren" in request.prompt:
            return _wait_json(ids["wren"], snapshot)
        return None

    gateways["character"].route = _decide
    return gateways


def test_interrupted_structured_commit_resumes_with_source_intact(
    migrated_db: None,
) -> None:
    """Fault after narration persistence must keep the exact source on resume.

    Boundary: beats plus structured source committed, phase still open. A
    fresh controller resumes with no extra beats and no narrator calls.
    """
    async def _inner() -> None:
        control_ids = await _seed()
        await _set_narration_mode(control_ids, "structured")
        await _orchestrator(_talking_gateways(control_ids)).advance_phase(
            control_ids["world"], 1
        )
        control_run = derive_run_id(control_ids["world"], 1)
        control_keys = await _beat_keys_for_run(control_run)
        assert control_keys

        ids = await _seed()
        await _set_narration_mode(ids, "structured")
        gateways = _talking_gateways(ids)
        fired: list[str] = []

        def _hook(point: str) -> None:
            if point == "after_scenes_committed" and not fired:
                fired.append(point)
                raise RuntimeError("injected after commit")

        with pytest.raises(RuntimeError, match="injected"):
            await _orchestrator(gateways, hook=_hook).advance_phase(ids["world"], 1)
        assert fired
        run_id = derive_run_id(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                scenes = await uow.scenes.list_for_run(run_id)
                assert scenes
                stored = await uow.scenes.get_scene(scenes[0].id)
                assert stored.narration_status == "structured"
        finally:
            await engine.dispose()
        mid_keys = await _beat_keys_for_run(run_id)
        assert mid_keys == control_keys

        resume_gateways = _talking_gateways(ids)
        report = await _orchestrator(resume_gateways).advance_phase(ids["world"], 1)
        assert all(s.narration == "structured" for s in report.scenes)
        assert gateways["narrator"].calls == []
        assert resume_gateways["narrator"].calls == []
        assert await _beat_keys_for_run(run_id) == control_keys
        stored_after = await _stored_narration_statuses(report)
        assert stored_after and all(s == "structured" for s in stored_after)

    asyncio.run(_inner())


async def _beat_keys_for_run(
    run_id: UUID,
) -> list[tuple[str, str, tuple[str, ...]]]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            beats: list[NarrationBeat] = []
            for scene in await uow.scenes.list_for_run(run_id):
                beats.extend(await uow.scenes.narrations_for_event(scene.event_id))
            return sorted(
                (b.kind.value, b.text, tuple(b.cited_fact_keys)) for b in beats
            )
    finally:
        await engine.dispose()


def test_failed_narration_resumes_to_recorded_success(
    migrated_db: None,
) -> None:
    """A failed attempt may be replaced when a resume narrates successfully."""
    async def _inner() -> None:
        ids = await _seed()
        gateways = _talking_gateways(ids)

        def _boom(_request: CompletionRequest) -> str | None:
            raise RuntimeError("narrator down")

        gateways["narrator"].route = _boom
        fired: list[str] = []

        def _hook(point: str) -> None:
            if point == "after_scenes_committed" and not fired:
                fired.append(point)
                raise RuntimeError("injected after commit")

        with pytest.raises(RuntimeError, match="injected"):
            await _orchestrator(gateways, hook=_hook).advance_phase(ids["world"], 1)
        assert fired
        run_id = derive_run_id(ids["world"], 1)
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                scenes = await uow.scenes.list_for_run(run_id)
                assert scenes
                stored = await uow.scenes.get_scene(scenes[0].id)
                assert stored.narration_status == "failed"
                assert await uow.scenes.narrations_for_event(scenes[0].event_id) == []
        finally:
            await engine.dispose()

        resume = await _orchestrator(_talking_gateways(ids)).advance_phase(
            ids["world"], 1
        )
        assert all(s.narration in ("narrated", "fallback") for s in resume.scenes)
        assert all(s.narration != "failed" for s in resume.scenes)
        stored_after = await _stored_narration_statuses(resume)
        assert stored_after and all(s != "failed" for s in stored_after)
        assert await _beat_keys_for_run(run_id)

    asyncio.run(_inner())


def test_duplicate_replay_reports_unknown_for_legacy_rows(
    migrated_db: None,
) -> None:
    """Rows predating the record replay as unknown, with beats intact."""
    async def _inner() -> None:
        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        await _set_narration_mode(ids, "structured")
        gateways = _agency_gateways(ids)
        first = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not first.duplicate
        before_texts = [(b.kind.value, b.text) for b in await _beats_for_report(first)]
        assert before_texts
        await _null_stored_narration_statuses(first)
        replay = await _orchestrator(gateways).advance_phase(ids["world"], 1)
        assert replay.duplicate
        assert all(s.narration == "unknown" for s in replay.scenes)
        after_texts = [(b.kind.value, b.text) for b in await _beats_for_report(first)]
        assert after_texts == before_texts

    asyncio.run(_inner())


def test_two_observers_produce_one_narration_fact(migrated_db: None) -> None:
    """One action seen by two characters narrates once (fallback path).

    Wren asks across locations and Ash answers, linking one two-participant
    scene. The narrator is down, so deterministic fallback beats persist.
    Each underlying attempt must yield exactly one beat even though both
    participants observe it; observer records themselves stay per-observer.
    """
    async def _inner() -> None:
        from worldsim.application.ports.model_gateway import ModelUnavailableError

        ids = await _seed()
        await _set_grant(ids, "player", ids["wren"])
        gateways = _agency_gateways(ids)
        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        gateways["narrator"].enqueue_error(ModelUnavailableError("provider down"))
        gateways["narrator"].default_text = None
        report = await _orchestrator(gateways).advance_phase(
            ids["world"], 1, _wren_ask(ids)
        )
        assert not report.duplicate
        assert all(s.narration == "fallback" for s in report.scenes)
        beats = await _beats_for_report(report)
        assert beats
        signatures = [
            (b.kind.value, b.text, tuple(b.cited_fact_keys)) for b in beats
        ]
        assert len(signatures) == len(set(signatures)), signatures
        dialogue = [b for b in beats if b.kind == NarrationKind.DIALOGUE]
        assert len(dialogue) == 1
        assert dialogue[0].speaker_id == ids["ash"]
        assert dialogue[0].cited_fact_keys
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                observations = 0
                for outcome in report.scenes:
                    observations += len(
                        await uow.perception.observations_for_event(outcome.event_id)
                    )
                assert observations >= 2 * len(report.scenes)
                replay = await _orchestrator(gateways).advance_phase(ids["world"], 1)
                assert replay.duplicate
                again = await _beats_for_report(report)
                assert [(b.kind.value, b.text) for b in again] == [
                    (b.kind.value, b.text) for b in beats
                ]
        finally:
            await engine.dispose()

    asyncio.run(_inner())
