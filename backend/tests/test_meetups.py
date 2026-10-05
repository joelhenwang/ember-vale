"""Characters heading for each other meet instead of swapping places."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for, _seed_two

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.commands import MoveAction, ObserveAction, WaitAction
from worldsim.domain.rules.meetups import resolve_meetups
from worldsim.domain.scenes import Intent
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

SNAP = uuid.uuid4()
HEARTH, MARKET, MILL = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _ids(*names: str) -> dict[str, uuid.UUID]:
    # Sorted uuids so "which id sorts first" is predictable in tests.
    made = sorted((uuid.uuid4() for _ in names), key=lambda u: u.hex)
    return dict(zip(names, made, strict=True))


def _move(actor: uuid.UUID, to: uuid.UUID, key: str = "character:t") -> Intent:
    return Intent(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        snapshot_id=SNAP,
        phase_run_id=uuid.uuid4(),
        author_character_id=actor,
        action=MoveAction(character_id=actor, snapshot_id=SNAP, destination_location_id=to),
        idempotency_key=key,
    )


def _families(intents: list[Intent]) -> list[str]:
    return [i.action.family.value for i in intents]


def test_crossing_moves_become_a_meeting() -> None:
    ids = _ids("ash", "wren")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET}
    names = {ids["ash"]: "Ash", ids["wren"]: "Wren"}
    out = resolve_meetups([_move(ids["ash"], MARKET), _move(ids["wren"], HEARTH)], where, names)
    assert _families(out) == ["observe", "move"]  # Ash (first id) stays
    stay = out[0].action
    assert isinstance(stay, ObserveAction) and stay.focus == "watching for Wren to arrive"
    assert out[0].author_character_id == ids["ash"]


def test_a_player_always_travels() -> None:
    ids = _ids("ash", "wren")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET}
    out = resolve_meetups(
        [_move(ids["ash"], MARKET, key="player:t"), _move(ids["wren"], HEARTH)], where, {}
    )
    assert _families(out) == ["move", "observe"]  # the AI character waits


def test_two_players_or_directed_moves_are_left_alone() -> None:
    ids = _ids("ash", "wren")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET}
    intents = [_move(ids["ash"], MARKET, key="player:a"), _move(ids["wren"], HEARTH, "direct:b")]
    assert resolve_meetups(intents, where, {}) == intents


def test_one_way_and_unrelated_moves_are_untouched() -> None:
    ids = _ids("ash", "wren", "tam")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET, ids["tam"]: MILL}
    intents = [
        _move(ids["ash"], MARKET),  # toward Wren, but Wren goes to the mill
        _move(ids["wren"], MILL),
        Intent(
            id=uuid.uuid4(),
            world_id=uuid.uuid4(),
            snapshot_id=SNAP,
            phase_run_id=uuid.uuid4(),
            author_character_id=ids["tam"],
            action=WaitAction(character_id=ids["tam"], snapshot_id=SNAP),
            idempotency_key="character:t",
        ),
    ]
    assert resolve_meetups(intents, where, {}) == intents


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_beat_with_crossing_decisions_files_one_wait_and_watch(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())  # Wren at the Hearth, Ash at the Market
    places = {
        p["name"]: p["id"]
        for p in client.get(
            "/api/v1/stage2/map",
            params={"world_id": str(ids["world"])},
            headers={"X-Worldsim-Role": "watcher"},
        ).json()["places"]
    }
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You decide" in (request.system or ""):
            wren = "<<untrusted:identity>>Wren" in request.prompt
            to = places["Market"] if wren else places["Hearth"]
            return json.dumps({"family": "move", "destination_location_id": to})
        return base(request)

    gateway.route = route
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text

    watcher = {"X-Worldsim-Role": "watcher"}
    scenes = client.get(
        "/api/v1/stage1/scenes", params={"phase_run_id": report.json()["run_id"]}, headers=watcher
    ).json()
    families: list[Any] = []
    for scene in scenes:
        detail = client.get(f"/api/v1/stage1/scenes/{scene['id']}", headers=watcher).json()
        families += [(i["detail"]["family"], i["detail"].get("focus")) for i in detail["intents"]]
    assert sorted(f for f, _ in families) == ["move", "observe"]
    assert any(focus and focus.startswith("watching for") for _, focus in families)
