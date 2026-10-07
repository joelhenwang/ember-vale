"""A world drawn on a map: where its places are and how long its roads take.

Points are integers from 0 to 1000 across the map image's width (x) and
height (y), [0, 0] being the top-left corner, so they survive resizing.
Travel time comes from road length: the player says how many phases the
shortest and the longest road take, and every road in between scales
linearly with its drawn length.
"""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Map coordinates run 0..MAP_SPAN on both axes.
MAP_SPAN = 1000

#: How a road is travelled, as the map reader names it.
ROAD_KINDS = ("road", "path", "sea", "river", "bridge", "pass")

#: Kinds a traveller goes along rather than to: never offered as places.
THOROUGHFARES = frozenset(
    {"road", "path", "track", "trail", "river", "stream", "sea", "ocean", "coast"}
)

Point = tuple[int, int]


def _in_span(point: Point) -> Point:
    x, y = point
    if not (0 <= x <= MAP_SPAN and 0 <= y <= MAP_SPAN):
        raise ValueError(f"map point {point} is outside 0..{MAP_SPAN}")
    return point


class MapPin(BaseModel):
    """Where one world location is drawn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="", max_length=32)
    point: Point

    @model_validator(mode="after")
    def _point(self) -> MapPin:
        _in_span(self.point)
        return self


class MapRoad(BaseModel):
    """One drawn connection between two pinned locations, both ways."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    a: str = Field(min_length=1, max_length=64)
    b: str = Field(min_length=1, max_length=64)
    by: str = Field(default="road", max_length=16)
    #: Bends between the two places, ends excluded.
    points: list[Point] = Field(default_factory=list, max_length=16)
    phases: int = Field(default=1, ge=1, le=999)

    @model_validator(mode="after")
    def _ends(self) -> MapRoad:
        if self.a == self.b:
            raise ValueError("a road joins two different places")
        for point in self.points:
            _in_span(point)
        return self


class TravelScale(BaseModel):
    """The player's anchor: the shortest and the longest road, in phases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shortest_phases: int = Field(default=1, ge=1, le=999)
    longest_phases: int = Field(default=10, ge=1, le=999)

    @model_validator(mode="after")
    def _ordered(self) -> TravelScale:
        if self.longest_phases < self.shortest_phases:
            raise ValueError("the longest road cannot be quicker than the shortest")
        return self


#: Terrain on a world map, one letter a cell.
TERRAIN_KINDS: dict[str, str] = {
    "w": "water",
    "p": "plains",
    "f": "forest",
    "h": "hills",
    "m": "mountains",
    "s": "marsh",
    "d": "desert",
    "i": "snow",
    "t": "town",
}
#: How much harder than open plains a stretch of road through it is.
TERRAIN_COST: dict[str, float] = {
    "w": 1.0,
    "p": 1.0,
    "t": 1.0,
    "f": 1.4,
    "d": 1.5,
    "h": 1.6,
    "s": 2.0,
    "i": 2.0,
    "m": 2.6,
}
#: Colours for drawing the grid (shared with the client legend).
TERRAIN_COLOURS: dict[str, str] = {
    "w": "#3b82c4",
    "p": "#b6d36b",
    "f": "#2f7d3a",
    "h": "#b8935a",
    "m": "#7a6a5a",
    "s": "#5f8f7a",
    "d": "#e3c77a",
    "i": "#eef3f7",
    "t": "#c0392b",
}
MAX_TERRAIN_SIDE = 48


class TerrainGrid(BaseModel):
    """What covers the map, cell by cell: rows of letters, top row first."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cols: int = Field(ge=2, le=MAX_TERRAIN_SIDE)
    rows: int = Field(ge=2, le=MAX_TERRAIN_SIDE)
    cells: str = Field(min_length=4, max_length=MAX_TERRAIN_SIDE * MAX_TERRAIN_SIDE)

    @model_validator(mode="after")
    def _shape(self) -> TerrainGrid:
        if len(self.cells) != self.cols * self.rows:
            raise ValueError("the terrain grid has the wrong number of cells")
        unknown = set(self.cells) - set(TERRAIN_KINDS)
        if unknown:
            raise ValueError(f"unknown terrain {sorted(unknown)}")
        return self

    def at(self, x: float, y: float) -> str:
        """The letter under a point given as fractions of the map's sides."""
        col = min(self.cols - 1, max(0, int(x * self.cols)))
        row = min(self.rows - 1, max(0, int(y * self.rows)))
        return self.cells[row * self.cols + col]


class WorldMap(BaseModel):
    """A world preset's map: the picture, its pins and its timed roads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str = Field(min_length=1, max_length=128)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    pins: list[MapPin] = Field(default_factory=list, max_length=64)
    roads: list[MapRoad] = Field(default_factory=list, max_length=256)
    scale: TravelScale = Field(default_factory=TravelScale)
    #: What covers the map; roads through hard country take longer.
    terrain: TerrainGrid | None = None

    @model_validator(mode="after")
    def _known_ends(self) -> WorldMap:
        keys = [pin.key for pin in self.pins]
        if len(set(keys)) != len(keys):
            raise ValueError("a place is pinned twice")
        pinned = set(keys)
        seen: set[frozenset[str]] = set()
        for road in self.roads:
            if road.a not in pinned or road.b not in pinned:
                raise ValueError(f"road {road.a} - {road.b} ends at an unpinned place")
            pair = frozenset((road.a, road.b))
            if pair in seen:
                raise ValueError(f"road {road.a} - {road.b} is drawn twice")
            seen.add(pair)
        return self

    def road_between(self, a: str, b: str) -> MapRoad | None:
        for road in self.roads:
            if {road.a, road.b} == {a, b}:
                return road
        return None

    def phases_between(self, a: str, b: str) -> int | None:
        road = self.road_between(a, b)
        return road.phases if road is not None else None


#: Spots a place's own map may hold.
MAX_SPOTS = 32


class PlaceSpot(BaseModel):
    """One spot inside a place, where a person could be found."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="", max_length=32)
    point: Point

    @model_validator(mode="after")
    def _point(self) -> PlaceSpot:
        _in_span(self.point)
        return self


class PlaceMap(BaseModel):
    """A place's own map: a closer picture and the spots on it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str = Field(min_length=1, max_length=128)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    spots: list[PlaceSpot] = Field(default_factory=list, max_length=MAX_SPOTS)

    @model_validator(mode="after")
    def _distinct(self) -> PlaceMap:
        keys = [spot.key for spot in self.spots]
        if len(set(keys)) != len(keys):
            raise ValueError("two spots share a key")
        return self


#: Stamina a phase on the road costs, by how it is travelled: on board a
#: ship or a riverboat one mostly sits; a mountain pass is hard going.
STAMINA_PER_PHASE = {"sea": 1, "river": 1, "road": 2, "bridge": 2, "path": 3, "pass": 5}
#: No road costs more: a rested traveller (stamina 80 at the start) can
#: always set off, and arrives tired rather than never.
MAX_ROAD_STAMINA = 40


def road_stamina(phases: int, by: str) -> int:
    """Stamina a whole road costs, paid on setting off (rest gives 10 a phase)."""
    rate = STAMINA_PER_PHASE.get(by, STAMINA_PER_PHASE["road"])
    return min(MAX_ROAD_STAMINA, max(1, phases) * rate)


def road_length(line: list[Point], width: int, height: int) -> float:
    """Drawn length of a polyline, in map units of the image's longer side.

    Map points are fractions of each side, so a wide map's x steps are
    longer than its y steps; scaling by the aspect keeps lengths true.
    """
    longer = max(width, height)
    sx, sy = width / longer, height / longer
    return sum(
        math.hypot((x2 - x1) * sx, (y2 - y1) * sy)
        for (x1, y1), (x2, y2) in zip(line, line[1:], strict=False)
    )


#: Road stretches are walked in steps this long (map units) when weighed by terrain.
_TERRAIN_STEP = MAP_SPAN / 100


def effort_length(
    line: list[Point], width: int, height: int, terrain: TerrainGrid | None, by: str = "road"
) -> float:
    """A road's length weighed by what it crosses: plains count once, a
    mountain stretch 2.6 times. Without terrain (or on water) it is the
    drawn length."""
    if terrain is None or by in ("sea", "river"):
        return road_length(line, width, height)
    longer = max(width, height)
    sx, sy = width / longer, height / longer
    total = 0.0
    for (x1, y1), (x2, y2) in zip(line, line[1:], strict=False):
        length = math.hypot((x2 - x1) * sx, (y2 - y1) * sy)
        steps = max(1, math.ceil(length / _TERRAIN_STEP))
        for n in range(steps):
            t = (n + 0.5) / steps
            x = (x1 + (x2 - x1) * t) / MAP_SPAN
            y = (y1 + (y2 - y1) * t) / MAP_SPAN
            total += length / steps * TERRAIN_COST[terrain.at(x, y)]
    return total


def travel_phases(lengths: list[float], scale: TravelScale) -> list[int]:
    """Phases per road: the shortest road takes the shortest time, and so on.

    Linear between the two anchors, rounded, never under one phase. Equal
    lengths (or a single road) all take the shortest time.
    """
    if not lengths:
        return []
    low, high = min(lengths), max(lengths)
    span = high - low
    out: list[int] = []
    for length in lengths:
        share = (length - low) / span if span > 0 else 0.0
        phases = scale.shortest_phases + share * (scale.longest_phases - scale.shortest_phases)
        # Half rounds up, as the client's Math.round does.
        out.append(max(1, math.floor(phases + 0.5)))
    return out


def timed_roads(
    roads: list[MapRoad],
    pins: list[MapPin],
    width: int,
    height: int,
    scale: TravelScale,
    terrain: TerrainGrid | None = None,
) -> list[MapRoad]:
    """The same roads with phases set from their length (weighed by the
    terrain they cross, when the map has one) and the scale."""
    where = {pin.key: pin.point for pin in pins}
    lengths = [
        effort_length([where[road.a], *road.points, where[road.b]], width, height, terrain, road.by)
        for road in roads
    ]
    return [
        road.model_copy(update={"phases": phases})
        for road, phases in zip(roads, travel_phases(lengths, scale), strict=True)
    ]


def spot_named(text: str, spots: list[tuple[str, str]]) -> str | None:
    """The spot (key) a scene's prose says it happens at, or None.

    Spots are (key, name) pairs. A name counts when written as a whole
    phrase; a one-word name ("Mill", "Well") only when capitalised as on
    the map or after "the", so "as well" or "mill about" never place
    anyone. The spot named most wins; a tie goes to the first named.
    """
    best: tuple[int, int, str] | None = None
    for key, name in spots:
        core = re.sub(r"^the\s+", "", name.strip(), flags=re.IGNORECASE)
        if not core:
            continue
        escaped = re.escape(core)
        if " " in core:
            pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
        else:
            pattern = re.compile(rf"(?:\b{escaped}\b|(?i:\bthe\s+{escaped}\b))")
        hits = [m.start() for m in pattern.finditer(text)]
        if not hits:
            continue
        rank = (len(hits), -hits[0], key)
        if best is None or rank[:2] > best[:2]:
            best = rank
    return best[2] if best else None
