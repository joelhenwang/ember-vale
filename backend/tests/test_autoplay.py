"""Server-side autoplay: rules, routes, and the runner (E5 observatory)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import (
    MIGRATIONS,
    SEED_DIR,
    ApiClient,
    _player,
    _route_for,
    _seed_two,
    _watcher,
)

from worldsim.application.autoplay import AutoplayRunner, pause_autoplay, read_autoplay
from worldsim.application.orchestration.stage1 import Stage1PhaseReport
from worldsim.domain.autoplay import (
    PRESENCE_GRACE_SECONDS,
    AutoplayState,
    AutoplayStatus,
    StopReason,
    beat_committed,
    is_due,
    observers_gone,
    pause,
    play,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.phases import PhaseRun
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import _autoplay_beat, create_app
from worldsim.interfaces.http.state import AppState

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


# -- pure rules ---------------------------------------------------------------


def test_play_is_due_at_once_and_counts_as_presence() -> None:
    state = play(AutoplayState(world_id=uuid.uuid4()), now=T0, delay_seconds=5, beat_limit=3)
    assert state.status == AutoplayStatus.PLAYING
    assert is_due(state, T0)
    assert not observers_gone(state, T0 + timedelta(seconds=PRESENCE_GRACE_SECONDS))
    assert observers_gone(state, T0 + timedelta(seconds=PRESENCE_GRACE_SECONDS + 1))


def test_beats_wait_for_the_delay_and_stop_at_the_limit() -> None:
    state = play(AutoplayState(world_id=uuid.uuid4()), now=T0, delay_seconds=5, beat_limit=2)
    after_one = beat_committed(state, T0)
    assert after_one.beats_left == 1 and after_one.beats_run == 1
    assert not is_due(after_one, T0 + timedelta(seconds=4))
    assert is_due(after_one, T0 + timedelta(seconds=5))
    after_two = beat_committed(after_one, T0 + timedelta(seconds=5))
    assert after_two.status == AutoplayStatus.PAUSED
    assert after_two.stop_reason == StopReason.BEAT_LIMIT
    assert not is_due(after_two, T0 + timedelta(days=1))


def test_pause_is_never_due() -> None:
    state = play(AutoplayState(world_id=uuid.uuid4()), now=T0, delay_seconds=0, beat_limit=5)
    paused = pause(state, StopReason.USER)
    assert not is_due(paused, T0 + timedelta(hours=1))
    assert paused.stop_reason == StopReason.USER


# -- routes and runner against a real world ------------------------------------


@pytest.fixture
def autoplay_api(
    migrated_db: None,
) -> Iterator[tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    ids = asyncio.run(_seed_two())
    gateway.route = _route_for(ids, {})
    with TestClient(app) as raw:
        yield ApiClient(raw), raw, gateway, ids


def _state(raw: TestClient) -> AppState:
    return raw.app.state.app_state  # type: ignore[attr-defined]


def _on_app_loop[T](raw: TestClient, work: Callable[[], Awaitable[T]]) -> T:
    """Run on the app's event loop, where its database engine lives."""
    portal: Any = raw.portal
    return portal.call(work)


def _drive(
    raw: TestClient,
    *,
    clock: Callable[[], datetime] | None = None,
    advance: Callable[[UUID, int], Awaitable[Stage1PhaseReport]] | None = None,
) -> list[UUID]:
    """One runner tick, waiting for the beats it started."""
    state = _state(raw)
    runner = AutoplayRunner(
        state.uow_factory(),
        advance or (lambda world_id, index: _autoplay_beat(state, world_id, index)),
        clock=clock or (lambda: datetime.now(UTC)),
    )

    async def tick() -> list[UUID]:
        tasks = await runner.tick()
        await asyncio.gather(*tasks)
        return [UUID(int=0)] * len(tasks)

    return _on_app_loop(raw, tick)


def _clock(raw: TestClient, world: UUID) -> int:
    status = raw.get(
        "/api/v1/simulation/status", params={"world_id": str(world)}, headers=_watcher()
    )
    return int(status.json()["absolute_index"])


def test_unplayed_story_reads_paused(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, _raw, _gw, ids = autoplay_api
    view = client.get(f"/api/v1/stories/{ids['world']}/autoplay", headers=_watcher()).json()
    assert view["status"] == "paused"
    assert view["beats_left"] == 0
    assert view["runner_enabled"] is False  # disabled for the test process


def test_runner_plays_beats_until_the_limit(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, raw, _gw, ids = autoplay_api
    world = ids["world"]
    played = client.post(
        f"/api/v1/stories/{world}/autoplay/play",
        json={"delay_seconds": 0, "beat_limit": 2},
        headers=_watcher(),
    )
    assert played.status_code == 200, played.text
    assert played.json()["status"] == "playing"
    start = _clock(raw, world)

    assert len(_drive(raw)) == 1
    assert _clock(raw, world) == start + 1
    assert len(_drive(raw)) == 1
    assert _clock(raw, world) == start + 2

    view = client.get(f"/api/v1/stories/{world}/autoplay", headers=_watcher()).json()
    assert view["status"] == "paused"
    assert view["stop_reason"] == "beat_limit"
    assert view["beats_run"] == 2
    assert _drive(raw) == []  # paused: nothing more runs
    assert _clock(raw, world) == start + 2


def test_runner_pauses_when_nobody_watches(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, raw, _gw, ids = autoplay_api
    world = ids["world"]
    client.post(f"/api/v1/stories/{world}/autoplay/play", json={}, headers=_watcher())
    start = _clock(raw, world)
    later = datetime.now(UTC) + timedelta(seconds=PRESENCE_GRACE_SECONDS + 5)

    _drive(raw, clock=lambda: later)

    view = client.get(f"/api/v1/stories/{world}/autoplay", headers=_watcher()).json()
    assert view["status"] == "paused"
    assert view["stop_reason"] == "no_observers"
    assert _clock(raw, world) == start


def test_presence_keeps_autoplay_running(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, raw, _gw, ids = autoplay_api
    world = ids["world"]
    client.post(
        f"/api/v1/stories/{world}/autoplay/play",
        json={"delay_seconds": 0, "beat_limit": 5},
        headers=_watcher(),
    )
    seen = client.post(f"/api/v1/stories/{world}/autoplay/presence", headers=_watcher())
    assert seen.status_code == 200
    last_seen = datetime.fromisoformat(seen.json()["last_seen_at"])
    start = _clock(raw, world)

    _drive(raw, clock=lambda: last_seen + timedelta(seconds=PRESENCE_GRACE_SECONDS - 5))

    assert _clock(raw, world) == start + 1


def test_beat_error_pauses_with_the_reason(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, raw, _gw, ids = autoplay_api
    world = ids["world"]
    client.post(f"/api/v1/stories/{world}/autoplay/play", json={}, headers=_watcher())

    async def failing(_world: UUID, _index: int) -> Stage1PhaseReport:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, "a beat is still open")

    _drive(raw, advance=failing)

    view = client.get(f"/api/v1/stories/{world}/autoplay", headers=_watcher()).json()
    assert view["status"] == "paused"
    assert view["stop_reason"] == "error"
    assert "a beat is still open" in view["stop_detail"]


def test_pause_during_a_beat_wins(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, raw, _gw, ids = autoplay_api
    world = ids["world"]
    client.post(f"/api/v1/stories/{world}/autoplay/play", json={}, headers=_watcher())
    state = _state(raw)

    async def paused_meanwhile(world_id: UUID, index: int) -> Stage1PhaseReport:
        await pause_autoplay(state.uow_factory(), world_id)
        return Stage1PhaseReport(
            run_id=uuid.uuid4(), world_id=world_id, absolute_index=index, snapshot_id=uuid.uuid4()
        )

    _drive(raw, advance=paused_meanwhile)

    final = _on_app_loop(raw, lambda: read_autoplay(state.uow_factory(), world))
    assert final.status == AutoplayStatus.PAUSED
    assert final.stop_reason == StopReason.USER
    assert final.beats_run == 0


def test_players_cannot_autoplay(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, _raw, _gw, ids = autoplay_api
    denied = client.post(
        f"/api/v1/stories/{ids['world']}/autoplay/play", json={}, headers=_player(ids["wren"])
    )
    assert denied.status_code == 403


def test_play_rejects_out_of_range_settings(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, _raw, _gw, ids = autoplay_api
    url = f"/api/v1/stories/{ids['world']}/autoplay/play"
    assert client.post(url, json={"beat_limit": 0}, headers=_watcher()).status_code == 422
    assert client.post(url, json={"delay_seconds": -1}, headers=_watcher()).status_code == 422


def test_runner_resumes_a_beat_left_open(
    autoplay_api: tuple[ApiClient, TestClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, raw, _gw, ids = autoplay_api
    world = ids["world"]
    state = _state(raw)
    stuck = _clock(raw, world) + 1

    async def leave_open() -> None:
        async with state.uow_factory()() as uow:
            await uow.phases.create_run(
                PhaseRun(id=uuid.uuid4(), world_id=world, absolute_index=stuck)
            )
            await uow.commit()

    _on_app_loop(raw, leave_open)
    client.post(f"/api/v1/stories/{world}/autoplay/play", json={}, headers=_watcher())
    asked: list[int] = []

    async def record(world_id: UUID, index: int) -> Stage1PhaseReport:
        asked.append(index)
        return Stage1PhaseReport(
            run_id=uuid.uuid4(), world_id=world_id, absolute_index=index, snapshot_id=uuid.uuid4()
        )

    _drive(raw, advance=record)

    assert asked == [stuck]
