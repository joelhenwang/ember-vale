"""Map reading port: a world map picture in, its places and roads out
(or, for a closer picture of one place, the spots inside it)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from worldsim.domain.geography import TerrainGrid


@dataclass(frozen=True)
class ReadPlace:
    name: str
    kind: str
    #: [x, y] from 0 to 1000 across the image's width and height.
    point: tuple[int, int]


@dataclass(frozen=True)
class ReadRoad:
    #: Indexes into the places the roads were traced between.
    a: int
    b: int
    by: str
    #: Bends between the two places, ends excluded.
    points: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Reading[T]:
    found: tuple[T, ...]
    model: str
    seconds: float
    cost_usd: float


class MapReadingError(Exception):
    """The reader could not answer (service down, unreadable answer)."""


class MapReader(Protocol):
    #: known: the world's own place names, so unlabelled drawings can be matched to them.
    async def places(
        self, image: bytes, mime: str, known: tuple[str, ...] = ()
    ) -> Reading[ReadPlace]: ...

    #: The box around a character's face: (left, top, right, bottom) 0..1000.
    async def face(self, image: bytes, mime: str) -> Reading[tuple[int, int, int, int]]: ...

    #: What covers the map, as a grid of terrain letters.
    async def terrain(
        self, image: bytes, mime: str, cols: int, rows: int
    ) -> Reading[TerrainGrid]: ...

    #: Spots inside one place, from a closer picture of it.
    async def spots(self, image: bytes, mime: str) -> Reading[ReadPlace]: ...

    async def roads(
        self, image: bytes, mime: str, places: list[ReadPlace]
    ) -> Reading[ReadRoad]: ...
