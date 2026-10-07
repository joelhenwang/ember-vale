"""A beat returns once its scenes commit; narration lands behind it."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

from test_stage1_orchestration import PROFILES, _role_gateways, _seed

from worldsim.application.orchestration.background import BackgroundNarration
from worldsim.application.orchestration.stage1 import Stage1Orchestrator
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import NullExporter


def _orchestrator(
    gateways: dict[str, FakeGateway], narration: BackgroundNarration
) -> tuple[Stage1Orchestrator, Any]:
    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731
    orchestrator = Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        lambda role: gateways[role],
        PROFILES,
        narration=narration,
    )
    return orchestrator, engine


async def _narrated(engine: Any, event_ids: list[Any]) -> list[bool]:
    async with create_unit_of_work(engine) as uow:
        return [bool(await uow.scenes.narrations_for_event(e)) for e in event_ids]


def test_the_beat_returns_before_its_narration_and_the_next_waits(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        narration = BackgroundNarration()
        orchestrator, engine = _orchestrator(_role_gateways(ids), narration)
        try:
            first = await orchestrator.advance_phase(ids["world"], 1)
            assert first.scenes and all(s.narration == "pending" for s in first.scenes)
            await orchestrator.advance_phase(ids["world"], 2)  # waits for beat 1's words
            assert all(await _narrated(engine, [s.event_id for s in first.scenes]))
            await narration.drain()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


class _Dropping(BackgroundNarration):
    """Loses its work, as a process stopped mid-narration would."""

    def start(self, world_id: Any, work: Awaitable[Any]) -> asyncio.Future[Any]:
        future = asyncio.ensure_future(work)
        future.cancel()
        return future


def test_narration_lost_with_its_process_is_written_by_the_next_beat(
    migrated_db: None,
) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orchestrator, engine = _orchestrator(_role_gateways(ids), _Dropping())
        try:
            first = await orchestrator.advance_phase(ids["world"], 1)
            await asyncio.sleep(0)
            events = [s.event_id for s in first.scenes]
            assert not any(await _narrated(engine, events))
            await orchestrator.advance_phase(ids["world"], 2)
            assert all(await _narrated(engine, events))
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_scenes_prepare_side_by_side_and_redo_on_a_conflict(migrated_db: None) -> None:
    from worldsim.domain.errors import DomainError, ErrorCode

    async def _inner() -> None:
        ids = await _seed()  # Wren at the Hearth, Ash at the Market: two scenes
        orchestrator, engine = _orchestrator(_role_gateways(ids), BackgroundNarration())
        real = orchestrator._commit_prepared  # pyright: ignore[reportPrivateUsage]
        conflicts: list[Any] = []

        async def first_conflicts(*args: Any) -> Any:
            if not conflicts:
                conflicts.append(args[4])
                raise DomainError(ErrorCode.VERSION_CONFLICT, "injected")
            return await real(*args)

        orchestrator._commit_prepared = first_conflicts  # type: ignore[method-assign]
        try:
            report = await orchestrator.advance_phase(ids["world"], 1)
            assert len(report.scenes) == 2 and conflicts  # the redo committed it anyway
            async with create_unit_of_work(engine) as uow:
                for scene in report.scenes:
                    assert (await uow.scenes.get_scene(scene.scene_id)).event_id == scene.event_id
        finally:
            await engine.dispose()

    asyncio.run(_inner())
