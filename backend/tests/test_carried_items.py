"""What a character carries in the studio, they hold when a story starts."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient
from test_story_travel import ASH_PRESET_ID, MIGRATIONS, SEED_DIR, WORLD_PRESET_ID, _create

from worldsim.domain.carried import MAX_CARRIED, carried_items
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

LOOK = "\n".join(
    [
        "A quick girl from the ferry clans.",
        "Age: 17",
        "Carries: Her grandmother's brass bell, a coil of line; chalk",
        "  and a tide chart tucked in waxed cloth.",
        "Condition: Tired",
    ]
)


def test_the_carries_line_becomes_item_names() -> None:
    assert carried_items(LOOK) == [
        "Grandmother's brass bell",
        "Coil of line",
        "Chalk",
        "Tide chart tucked in waxed cloth",
    ]
    assert carried_items("Steady stance, weather-worn cloak.") == []
    assert carried_items(None) == []
    many = "Carries: " + ", ".join(f"thing {n}" for n in range(12)) + ", Thing 1"
    assert len(carried_items(many)) == MAX_CARRIED


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw)


def test_a_story_starts_with_what_they_carry(client: ApiClient) -> None:
    made = client.post(
        "/api/v1/library/presets",
        json={
            "kind": "character",
            "name": "Mara",
            "payload": {"name": "Mara", "appearance": LOOK},
        },
        headers={},
    )
    assert made.status_code == 200, made.text
    draft = client.post(
        "/api/v1/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": WORLD_PRESET_ID, "preset_revision": 2},
                "cast": [
                    {
                        "instance_key": "cast-mara",
                        "preset_id": made.json()["id"],
                        "preset_revision": 1,
                        "name": "Mara",
                        "location_key": "hearth",
                    },
                    {
                        "instance_key": "cast-ash",
                        "preset_id": ASH_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Ash",
                        "location_key": "market",
                    },
                ],
                "mode": {"role": "watcher"},
                "story": {"title": "What Mara Carries", "tone": "hopeful mystery"},
                "ai": {"art_source": "curated"},
            },
            "current_step": "review",
        },
        headers={},
    )
    assert draft.status_code == 200, draft.text
    created = _create(client, draft.json()["id"], "carried-story")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["story_id"])

    async def held() -> dict[str, list[str]]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                people = await uow.characters.list_for_world(world_id)
                return {
                    c.name: sorted(
                        i.name or i.item_key
                        for i in await uow.inventory.list_for_owner(world_id, c.id)
                    )
                    for c in people
                }
        finally:
            await engine.dispose()

    holdings = asyncio.run(held())
    assert holdings["Mara"] == sorted(carried_items(LOOK))
    assert holdings["Ash"] == []


def test_places_without_a_map_are_spread_apart() -> None:
    from itertools import combinations
    from uuid import uuid4

    from worldsim.application.queries.presentation import schematic_anchors

    for count in (1, 2, 3, 5, 8, 9, 14):
        ids = [uuid4() for _ in range(count)]
        at = schematic_anchors(ids)
        assert set(at) == set(ids)
        assert all(0.05 <= x <= 0.95 and 0.05 <= y <= 0.95 for x, y in at.values())
        for (ax, ay), (bx, by) in combinations(at.values(), 2):
            assert abs(ax - bx) + abs(ay - by) > 0.1
        assert schematic_anchors(list(reversed(ids))) == at  # stable


def test_a_snippet_ends_on_a_whole_word() -> None:
    from worldsim.interfaces.http.routes.stage2 import clip

    long = "The harbor is quiet, the air thick with the scent of salt and seaweed. " * 4
    short = clip(long)
    assert len(short) <= 160 and short.endswith("…")
    assert long.startswith(short[:-1]) and long[len(short) - 1] == " "
    assert clip("Ash waits.") == "Ash waits."
