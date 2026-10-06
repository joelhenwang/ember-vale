"""Renown from a character's journey: places, people, deeds, settled rumours."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_meetups import _seed_connected
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for

from worldsim.domain.journey import Journey, level_floor, level_for, title_for
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def test_levels_come_at_growing_intervals() -> None:
    assert [level_floor(n) for n in (1, 2, 3, 4, 5)] == [0, 10, 30, 60, 100]
    assert [level_for(r) for r in (0, 9, 10, 29, 30, 100)] == [1, 1, 2, 2, 3, 5]
    assert title_for(1) == "Newcomer" and title_for(99) == "Legend"
    assert Journey(places=2, people=3, deeds=1, settled=1).renown == 4 + 6 + 3 + 5


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_players_see_their_journey_and_watchers_do_not(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())
    gateway.route = _route_for(ids, {})
    assert _advance(client, ids["world"], 1).status_code == 200

    def view(headers: dict[str, str]) -> dict[str, object]:
        return client.get(
            "/api/v1/world/presentation", params={"world_id": str(ids["world"])}, headers=headers
        ).json()

    wren = str(ids["wren"])
    journey = view({"X-Worldsim-Role": "player", "X-Worldsim-Character": wren})["journey"]
    assert isinstance(journey, dict)
    assert journey["places"] >= 1 and journey["level"] >= 1
    assert journey["level_floor"] <= journey["renown"] < journey["next_level_at"]
    assert view({"X-Worldsim-Role": "watcher"})["journey"] is None
