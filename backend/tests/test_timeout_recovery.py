"""Timed-out-run diagnosis and ordinary-user recovery (owned by REL-REC-001).

A dropped client connection is not a failed beat: cancelling mid-flight
leaves the run open with partial progress, and resubmitting the same index
resumes it without duplicating events, effects, or player submissions.
Server interruption after partial commit behaves the same way. Budgets,
models, prompts, and retry policy are untouched; these tests pin the
recovery contract only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from test_stage1_api import (  # pyright: ignore[reportPrivateUsage]
    _route_for,
    _seed_two,
)
from test_stage1_orchestration import (
    _orchestrator,
    _role_gateways,
    _seed,
)

import worldsim.application.execution as execution
from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.ports.model_gateway import CompletionRequest, ProbeResult
from worldsim.domain.commands import CommunicateAction
from worldsim.domain.ids import derive_intent_id
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import (
    CHARACTER_FAKE_PROFILE,
    FAKE_TEST_PROFILE,
)
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


def _player_intents(ids: dict[str, UUID]) -> dict[UUID, CommunicateAction]:
    return {
        ids["ash"]: CommunicateAction(
            character_id=ids["ash"],
            snapshot_id=derive_snapshot_id(derive_run_id(ids["world"], 1)),
            target_character_id=ids["wren"],
            topic="dawn patrol",
        )
    }


class _GatedGateway:
    """ModelGateway that blocks role calls until released (disconnect rig)."""

    profile = CHARACTER_FAKE_PROFILE

    def __init__(self, inner: FakeGateway) -> None:
        self._inner = inner
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, request: CompletionRequest) -> Any:
        self.entered.set()
        await self.release.wait()
        return await self._inner.complete(request)

    async def embed(self, request: Any) -> Any:
        return await self._inner.embed(request)

    async def probe(self) -> ProbeResult:
        return await self._inner.probe()


async def _ash_intent_topic(ids: dict[str, UUID], snapshot_id: UUID) -> str | None:
    from worldsim.domain.errors import DomainError

    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            try:
                intent = await uow.scenes.get_intent(
                    derive_intent_id(ids["world"], snapshot_id, ids["ash"])
                )
            except DomainError:
                return None
            action = intent.action
            return action.topic if isinstance(action, CommunicateAction) else None
    finally:
        await engine.dispose()


async def _open_run_id(ids: dict[str, UUID]) -> UUID | None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            run = await uow.phases.find_open_run(ids["world"])
            return run.id if run is not None else None
    finally:
        await engine.dispose()


async def _event_count(ids: dict[str, UUID]) -> int:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return await uow.events.count_events(ids["world"])
    finally:
        await engine.dispose()


def test_client_disconnect_leaves_resumable_run(migrated_db: None) -> None:
    """Cancelling mid-flight (dropped connection) keeps a resumable run.

    The run stays open with partial progress; resubmitting the same index
    with the same player submission completes exactly one beat.
    """

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        gateways["character"] = _GatedGateway(gateways["character"])
        orch = _orchestrator(gateways)
        player = _player_intents(ids)

        flight = asyncio.ensure_future(
            orch.advance_phase(ids["world"], 1, player, submitter_id=ids["ash"])
        )
        await gateways["character"].entered.wait()
        await asyncio.sleep(0)
        flight.cancel()
        with pytest.raises(asyncio.CancelledError):
            await flight

        # Interrupted, not failed: the run is still open.
        assert await _open_run_id(ids) == derive_run_id(ids["world"], 1)

        # Resume with the same submission; the gate is now open.
        gateways["character"].release.set()
        report = await orch.advance_phase(ids["world"], 1, player, submitter_id=ids["ash"])
        assert not report.duplicate
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.get_run(report.run_id)
                assert run.state.value == "completed"
                # One tick plus one event per committed scene, never doubled.
                assert await uow.events.count_events(ids["world"]) == 1 + len(report.scenes)
        finally:
            await engine.dispose()
        # The player submission filed before the disconnect commits once.
        assert await _ash_intent_topic(ids, report.snapshot_id) == "dawn patrol"
        assert await _open_run_id(ids) is None

    asyncio.run(_inner())


def test_interruption_after_partial_commit_resumes_once(migrated_db: None) -> None:
    """Server interruption after commit still resumes without duplication.

    The player submission filed before the interruption commits exactly
    once; already committed scenes are not re-executed.
    """

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        fired: list[str] = []

        def _hook(point: str) -> None:
            if point == "after_scene" and not fired:
                fired.append(point)
                raise RuntimeError("injected at after_scene")

        orch = _orchestrator(gateways, hook=_hook)
        player = _player_intents(ids)
        with pytest.raises(RuntimeError, match="injected"):
            await orch.advance_phase(ids["world"], 1, player, submitter_id=ids["ash"])
        mid = await _event_count(ids)
        assert mid >= 1
        assert await _open_run_id(ids) == derive_run_id(ids["world"], 1)

        orch = _orchestrator(gateways)
        report = await orch.advance_phase(ids["world"], 1, player, submitter_id=ids["ash"])
        assert not report.duplicate
        assert await _event_count(ids) == mid + len(report.scenes)
        assert await _ash_intent_topic(ids, report.snapshot_id) == "dawn patrol"
        assert await _open_run_id(ids) is None

    asyncio.run(_inner())


def _player_headers(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


def _advance_body(ids: dict[str, UUID], snapshot: UUID) -> dict[str, object]:
    return {
        "world_id": str(ids["world"]),
        "absolute_index": 1,
        "player_intents": {
            str(ids["ash"]): {
                "family": "communicate",
                "character_id": str(ids["ash"]),
                "snapshot_id": str(snapshot),
                "target_character_id": str(ids["wren"]),
                "topic": "dawn patrol",
            }
        },
    }


def test_room_recovers_timed_out_beat(migrated_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Disconnect strands the beat; status names it; resume completes it once.

    The room's own calls over HTTP: the beat starts server-side, then the
    connection drops. A reload-equivalent status read names the stranded
    open run (with its index); resubmitting the same index with the
    preserved player submission completes exactly one beat, and a fresh
    timeline read shows the committed content. The execution-slot lease
    (which a disconnected owner cannot release) is compressed to zero so
    the test does not wait out the production window; the takeover
    mechanism is unchanged.
    """

    async def _inner() -> None:
        monkeypatch.setattr(execution, "LEASE_SECONDS", 0)
        ids = await _seed_two()
        snapshot = derive_snapshot_id(derive_run_id(ids["world"], 1))
        inner = FakeGateway(profile=FAKE_TEST_PROFILE)
        inner.route = _route_for(ids, {1: snapshot})
        gateway = _GatedGateway(inner)
        app = create_app(
            Settings(),
            seed_dir=SEED_DIR,
            migrations_dir=MIGRATIONS,
            gateway_factory=lambda: gateway,
        )
        headers = _player_headers(ids["ash"])
        body = _advance_body(ids, snapshot)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://room") as client:
            flight = asyncio.ensure_future(
                client.post("/api/v1/stage1/advance", json=body, headers=headers)
            )
            await gateway.entered.wait()
            await asyncio.sleep(0)
            flight.cancel()
            with pytest.raises(asyncio.CancelledError):
                await flight

            status = await client.get(
                "/api/v1/simulation/status",
                params={"world_id": str(ids["world"])},
                headers=headers,
            )
            assert status.status_code == 200, status.text
            stranded = status.json()
            assert stranded["open_run_id"] == str(derive_run_id(ids["world"], 1))
            assert stranded["open_run_index"] == 1
            assert stranded["open_run_state"] != "completed"

            gateway.release.set()
            resumed = await client.post("/api/v1/stage1/advance", json=body, headers=headers)
            assert resumed.status_code == 200, resumed.text
            report = resumed.json()
            assert report["duplicate"] is False
            assert report["run_id"] == str(derive_run_id(ids["world"], 1))
            assert len(report["scenes"]) >= 1

            done = await client.get(
                "/api/v1/simulation/status",
                params={"world_id": str(ids["world"])},
                headers=headers,
            )
            assert done.json()["open_run_id"] is None
            timeline = await client.get(
                "/api/v1/stage2/timeline",
                params={"world_id": str(ids["world"]), "after": 0, "limit": 50},
                headers=headers,
            )
            assert timeline.status_code == 200, timeline.text
            seen = {entry["event_id"] for entry in timeline.json()["entries"]}
            for scene in report["scenes"]:
                assert scene["event_id"] in seen
            assert await _ash_intent_topic(ids, UUID(report["snapshot_id"])) == "dawn patrol"

    asyncio.run(_inner())
