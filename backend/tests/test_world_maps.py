"""World maps: pins and roads read off a picture become a world's timed travel."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_stage1_api import ApiClient
from test_story_travel import ASH_PRESET_ID, MIGRATIONS, SEED_DIR, WREN_PRESET_ID, _routes

from worldsim.application.geography import DrawnRoad, PinnedPlace, world_with_map
from worldsim.application.ports.map_reader import Reading, ReadPlace, ReadRoad
from worldsim.domain.geography import TravelScale, road_length, travel_phases
from worldsim.domain.presets import (
    WorldLocationPreset,
    WorldPresetPayload,
    canonical_payload_hash,
)
from worldsim.infrastructure.geography.openrouter import parse_places, parse_roads
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"
ASSETS = SEED_DIR.parent.parent / "assets"


def test_travel_time_scales_with_drawn_length() -> None:
    scale = TravelScale(shortest_phases=2, longest_phases=10)
    assert travel_phases([100.0, 300.0, 500.0], scale) == [2, 6, 10]
    assert travel_phases([40.0, 40.0], scale) == [2, 2]  # nothing to stretch
    assert travel_phases([], scale) == []
    assert travel_phases([0.0, 1.0, 8.0], TravelScale(shortest_phases=1, longest_phases=1)) == [
        1,
        1,
        1,
    ]
    # Half rounds up, matching the client's Math.round.
    assert travel_phases([0.0, 1.0, 2.0], TravelScale(shortest_phases=1, longest_phases=2)) == [
        1,
        2,
        2,
    ]
    with pytest.raises(ValueError):
        TravelScale(shortest_phases=5, longest_phases=3)


def test_road_length_respects_the_picture_shape() -> None:
    # On a 2:1 map, crossing the full width is twice as far as the full height.
    across = road_length([(0, 500), (1000, 500)], 2000, 1000)
    down = road_length([(500, 0), (500, 1000)], 2000, 1000)
    assert across == pytest.approx(2 * down)
    bent = road_length([(0, 0), (500, 0), (500, 500)], 1000, 1000)
    assert bent == pytest.approx(1000)


def _world(**extra: Any) -> WorldPresetPayload:
    return WorldPresetPayload(
        name="Vale",
        locations=[
            WorldLocationPreset(key="hearth", name="Hearth", description="An inn."),
            WorldLocationPreset(key="market", name="Market"),
            WorldLocationPreset(key="cellar", name="Cellar"),
        ],
        travel=[["hearth", "market"], ["market", "hearth"], ["hearth", "cellar"]],
        starting_location_key="hearth",
        **extra,
    )


def test_a_map_keeps_places_and_unmapped_travel() -> None:
    world = _world()
    places = [
        PinnedPlace("Hearth", "inn", (100, 100), key="hearth"),
        PinnedPlace("market", "market", (400, 100)),  # matched by name, renamed
        PinnedPlace("Old Mill", "mill", (400, 900)),  # new place
    ]
    roads = [
        DrawnRoad(0, 1, "road", ()),
        DrawnRoad(1, 2, "path", ((400, 500),)),
        DrawnRoad(2, 1, "road", ()),  # the same road again: once is enough
    ]
    scale = TravelScale(shortest_phases=2, longest_phases=6)
    mapped = world_with_map(world, "asset-1", 1000, 1000, places, roads, scale)
    assert [(p.key, p.name) for p in mapped.locations] == [
        ("hearth", "Hearth"),
        ("market", "market"),
        ("cellar", "Cellar"),
        ("old-mill", "Old Mill"),
    ]
    assert mapped.locations[0].description == "An inn."
    assert mapped.map is not None
    assert [(r.a, r.b, r.phases) for r in mapped.map.roads] == [
        ("hearth", "market", 2),
        ("market", "old-mill", 6),
    ]
    assert mapped.map.phases_between("old-mill", "market") == 6
    assert ["hearth", "cellar"] in mapped.travel  # not drawn, kept
    assert ["old-mill", "market"] in mapped.travel and ["market", "old-mill"] in mapped.travel
    # Reading the map again replaces the roads the old map drew.
    again = world_with_map(mapped, "asset-1", 1000, 1000, places[:2], roads[:1], scale)
    assert ["market", "old-mill"] not in again.travel
    assert ["hearth", "cellar"] in again.travel
    with pytest.raises(ValueError):
        world_with_map(world, "a", 10, 10, places, [DrawnRoad(0, 7, "road", ())], scale)


def test_worlds_without_a_map_keep_their_hash() -> None:
    world = _world()
    data = world.model_dump(mode="json")
    assert data.pop("map") is None
    legacy = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    assert canonical_payload_hash(world) == legacy
    with pytest.raises(ValueError):  # a pin must be one of the world's places
        _world(
            map={
                "asset_id": "a",
                "width": 1,
                "height": 1,
                "pins": [{"key": "nowhere", "point": [1, 1]}],
            }
        )


def test_reader_answers_are_cleaned() -> None:
    places = parse_places(
        '```json\n{"places": [{"name": "Corvane", "kind": "City", "point": [120, 2000]},'
        ' {"name": "", "point": [1, 1]}, {"name": "Pell", "point": ["x", 3]}, "junk"]}\n```'
    )
    assert places == [ReadPlace("Corvane", "city", (120, 1000))]
    roads = parse_roads(
        'Here: {"connections": [{"from": 1, "to": 2, "by": "ferry", "points": [[1, 2], 5]},'
        ' {"from": 2, "to": 1}, {"from": 1, "to": 9}, {"from": "a", "to": 2}]}',
        2,
    )
    assert roads == [ReadRoad(0, 1, "road", ((1, 2),))]


class _Reader:
    def __init__(self) -> None:
        self.asked: list[list[ReadPlace]] = []

    async def places(self, image: bytes, mime: str) -> Reading[ReadPlace]:
        assert image and mime == "image/png"
        found = (
            ReadPlace("Hearth", "inn", (100, 100)),
            ReadPlace("Market", "market", (300, 100)),
            ReadPlace("Old Mill", "mill", (900, 900)),
        )
        return Reading(found, "fake/places", 0.1, 0.001)

    async def roads(self, image: bytes, mime: str, places: list[ReadPlace]) -> Reading[ReadRoad]:
        self.asked.append(places)
        return Reading(
            (ReadRoad(0, 1, "road", ()), ReadRoad(1, 2, "path", ())), "fake/roads", 0.2, 0.03
        )


@pytest.fixture
def stack(migrated_db: None) -> Iterator[tuple[ApiClient, _Reader]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    reader = _Reader()
    with TestClient(app) as raw:
        raw.app.state.app_state._map_reader = reader  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]
        yield ApiClient(raw), reader


def _png() -> str:
    out = io.BytesIO()
    Image.new("RGB", (64, 32), (40, 90, 160)).save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def test_read_a_map_and_time_the_new_story(stack: tuple[ApiClient, _Reader]) -> None:
    api, reader = stack
    builtin = api.put(
        f"/api/v1/library/presets/{WORLD_PRESET_ID}/map",
        json={
            "asset_id": str(UUID(int=1)),
            "places": [{"name": "x", "point": [1, 1]}],
            "shortest_phases": 1,
            "longest_phases": 2,
            "expected_version": 0,
        },
    )
    assert builtin.status_code == 404  # no such picture comes first
    assert (
        api.post(
            "/api/v1/library/maps",
            json={"data_url": "data:text/plain;base64,aGVsbG8gd29ybGQgaGVsbG8gd29ybGQ="},
        ).status_code
        == 422
    )
    uploaded = api.post("/api/v1/library/maps", json={"data_url": _png()})
    assert uploaded.status_code == 200, uploaded.text
    picture = uploaded.json()
    asset_id = picture["asset_id"]
    try:
        assert (picture["width"], picture["height"]) == (64, 32)
        assert api.get(f"/api/v1/library/assets/{asset_id}/bytes").status_code == 200
        places = api.post(f"/api/v1/library/maps/{asset_id}/places").json()
        assert [p["name"] for p in places["places"]] == ["Hearth", "Market", "Old Mill"]
        roads = api.post(
            f"/api/v1/library/maps/{asset_id}/roads", json={"places": places["places"]}
        ).json()
        assert roads["model"] == "fake/roads" and len(roads["roads"]) == 2
        assert [p.name for p in reader.asked[0]] == ["Hearth", "Market", "Old Mill"]

        body = {
            "asset_id": asset_id,
            "places": places["places"],
            "roads": roads["roads"],
            "shortest_phases": 2,
            "longest_phases": 7,
        }
        readonly = api.put(
            f"/api/v1/library/presets/{WORLD_PRESET_ID}/map", json={**body, "expected_version": 0}
        )
        assert readonly.status_code == 403
        copy = api.post(f"/api/v1/library/presets/{WORLD_PRESET_ID}/duplicate").json()
        saved = api.put(
            f"/api/v1/library/presets/{copy['id']}/map",
            json={**body, "expected_version": copy["version"]},
        )
        assert saved.status_code == 200, saved.text
        revision = saved.json()["revision"]
        assert revision["map"]["scale"] == {"shortest_phases": 2, "longest_phases": 7}
        assert [(r["a"], r["b"], r["phases"]) for r in revision["map"]["roads"]] == [
            ("hearth", "market", 2),
            ("market", "old-mill", 7),
        ]
        stale = api.put(
            f"/api/v1/library/presets/{copy['id']}/map",
            json={**body, "expected_version": copy["version"]},
        )
        assert stale.status_code == 409

        draft = api.post(
            "/api/v1/story-drafts",
            json={
                "payload": {
                    "world": {"preset_id": copy["id"], "preset_revision": 2},
                    "cast": [
                        {
                            "instance_key": "cast-wren",
                            "preset_id": WREN_PRESET_ID,
                            "preset_revision": 1,
                            "name": "Wren",
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
                    "story": {"title": "Mapped", "tone": "calm"},
                    "ai": {"art_source": "curated"},
                },
                "current_step": "review",
            },
            headers={},
        )
        assert draft.status_code == 200, draft.text
        created = api.post(
            "/api/v1/stories",
            json={"draft_id": draft.json()["id"], "expected_draft_version": 1},
            headers={"Idempotency-Key": "mapped-story"},
        )
        assert created.status_code == 200, created.text
        legs = _routes(UUID(created.json()["world_id"]))
        assert legs[("Hearth", "Market")] == (2, 0)
        assert legs[("Old Mill", "Market")] == (7, 0)
        assert legs[("Market", "Old Mill")] == (7, 0)
    finally:
        for stored in (ASSETS / "generated" / "maps").glob(f"{asset_id}.*"):
            stored.unlink()


def test_readings_need_a_map_picture(stack: tuple[ApiClient, _Reader]) -> None:
    api, _ = stack
    missing = api.post(f"/api/v1/library/maps/{UUID(int=7)}/places")
    assert missing.status_code == 404
    assert Path(ASSETS).exists()
