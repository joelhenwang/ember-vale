"""Terrain on a world map: read as a grid, corrected by hand, weighing travel."""

from __future__ import annotations

import json

import pytest

from worldsim.domain.geography import (
    MapPin,
    MapRoad,
    TerrainGrid,
    TravelScale,
    effort_length,
    road_length,
    timed_roads,
)
from worldsim.domain.presets import WorldLocationPreset, WorldPresetPayload, canonical_payload_hash
from worldsim.infrastructure.geography.openrouter import TERRAIN_PROMPT, parse_terrain

# Left half plains, right half mountains, 4 x 2.
HALVES = TerrainGrid(cols=4, rows=2, cells="ppmmppmm")


def test_a_grid_has_the_right_shape_and_letters() -> None:
    assert HALVES.at(0.1, 0.9) == "p" and HALVES.at(0.9, 0.1) == "m"
    assert HALVES.at(1.0, 1.0) == "m"  # the far edge belongs to the last cell
    with pytest.raises(ValueError):
        TerrainGrid(cols=4, rows=2, cells="ppmm")
    with pytest.raises(ValueError):
        TerrainGrid(cols=2, rows=2, cells="ppzz")


def test_roads_through_hard_country_take_longer() -> None:
    plains = [(100, 500), (400, 500)]
    peaks = [(600, 500), (900, 500)]
    assert road_length(plains, 1000, 1000) == pytest.approx(road_length(peaks, 1000, 1000))
    assert effort_length(plains, 1000, 1000, HALVES) == pytest.approx(300)
    assert effort_length(peaks, 1000, 1000, HALVES) == pytest.approx(300 * 2.6)
    # Water routes are not slowed by what lies under them; no grid is the drawn length.
    assert effort_length(peaks, 1000, 1000, HALVES, "sea") == pytest.approx(300)
    assert effort_length(peaks, 1000, 1000, None) == pytest.approx(300)

    pins = [
        MapPin(key="a", kind="town", point=(100, 500)),
        MapPin(key="b", kind="town", point=(400, 500)),
        MapPin(key="c", kind="town", point=(600, 500)),
        MapPin(key="d", kind="town", point=(900, 500)),
    ]
    roads = [MapRoad(a="a", b="b"), MapRoad(a="c", b="d")]
    scale = TravelScale(shortest_phases=2, longest_phases=8)
    flat = timed_roads(roads, pins, 1000, 1000, scale)
    hilly = timed_roads(roads, pins, 1000, 1000, scale, HALVES)
    assert [r.phases for r in flat] == [2, 2]  # same drawn length
    assert [r.phases for r in hilly] == [2, 8]  # the mountain road is the long one


def test_a_world_without_terrain_keeps_its_hash() -> None:
    world = WorldPresetPayload(
        name="Vale",
        locations=[WorldLocationPreset(key="hearth", name="Hearth")],
        starting_location_key="hearth",
    )
    data = world.model_dump(mode="json")
    assert "map" not in json.dumps(data) or data.get("map") is None
    assert canonical_payload_hash(world) == canonical_payload_hash(
        WorldPresetPayload.model_validate(data)
    )


def test_an_answer_becomes_a_grid_even_when_ragged() -> None:
    assert "6 columns and 3 rows" in TERRAIN_PROMPT.format(cols=6, rows=3)
    grid = parse_terrain('```json\n{"rows": ["wwppff", "ppx", "MMMMMMMM"]}\n```', 6, 4)
    assert grid is not None
    # unknown letters read as plains, short rows run on, long rows are cut,
    # missing rows repeat the last one, capitals are fine
    assert grid.cells == "wwppff" + "pppppp" + "mmmmmm" + "mmmmmm"
    assert parse_terrain('{"rows": []}', 6, 3) is None
