"""Fold a read map into a world preset: its places, roads and travel times."""

from __future__ import annotations

import re
from dataclasses import dataclass

from worldsim.domain.geography import MapPin, MapRoad, TravelScale, WorldMap, timed_roads
from worldsim.domain.presets import WorldLocationPreset, WorldPresetPayload


@dataclass(frozen=True)
class PinnedPlace:
    name: str
    kind: str
    point: tuple[int, int]
    #: The world location this is; None matches by name or adds a place.
    key: str | None = None


@dataclass(frozen=True)
class DrawnRoad:
    #: Indexes into the pinned places.
    a: int
    b: int
    by: str
    points: tuple[tuple[int, int], ...]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:56] or "place"


def world_with_map(
    world: WorldPresetPayload,
    asset_id: str,
    width: int,
    height: int,
    places: list[PinnedPlace],
    roads: list[DrawnRoad],
    scale: TravelScale,
) -> WorldPresetPayload:
    """The world with these pins and roads; nothing else of it changes.

    A pin keeps its place (renamed to the map's name) when it names one by
    key or by name; otherwise it adds a place. Places off the map stay, as
    do travel pairs the previous map did not draw. Roads go both ways.
    """
    locations = list(world.locations)
    by_key = {place.key: i for i, place in enumerate(locations)}
    by_name = {place.name.strip().lower(): place.key for place in locations}
    keys: list[str] = []
    for place in places:
        key = place.key if place.key in by_key else by_name.get(place.name.strip().lower())
        if key is not None and key in keys:
            key = None  # two pins claimed one place: the second is a new one
        if key is None:
            base, n = _slug(place.name), 1
            key = base
            while key in by_key:
                n += 1
                key = f"{base}-{n}"
            by_key[key] = len(locations)
            locations.append(WorldLocationPreset(key=key, name=place.name))
        else:
            current = locations[by_key[key]]
            locations[by_key[key]] = current.model_copy(update={"name": place.name})
        keys.append(key)
    pins = [
        MapPin(key=key, kind=place.kind, point=place.point)
        for key, place in zip(keys, places, strict=True)
    ]
    drawn: list[MapRoad] = []
    seen: set[frozenset[str]] = set()
    for road in roads:
        if not (0 <= road.a < len(keys) and 0 <= road.b < len(keys)):
            raise ValueError(f"road {road.a} - {road.b} names a place that is not pinned")
        a, b = keys[road.a], keys[road.b]
        pair = frozenset((a, b))
        if a == b or pair in seen:
            continue
        seen.add(pair)
        drawn.append(MapRoad(a=a, b=b, by=road.by, points=list(road.points)))
    drawn = timed_roads(drawn, pins, width, height, scale)
    old: set[frozenset[str]] = (
        {frozenset((r.a, r.b)) for r in world.map.roads} if world.map else set()
    )
    travel = [leg for leg in world.travel if frozenset(leg) not in old]
    have = {tuple(leg) for leg in travel}
    for road in drawn:
        for leg in ((road.a, road.b), (road.b, road.a)):
            if leg not in have:
                have.add(leg)
                travel.append(list(leg))
    world_map = WorldMap(
        asset_id=asset_id, width=width, height=height, pins=pins, roads=drawn, scale=scale
    )
    return WorldPresetPayload.model_validate(
        world.model_dump() | {"locations": locations, "travel": travel, "map": world_map}
    )
