"""Map reading port: a world map picture in, its places and roads out
(or, for a closer picture of one place, the spots inside it)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
    async def places(self, image: bytes, mime: str) -> Reading[ReadPlace]: ...

    #: Spots inside one place, from a closer picture of it.
    async def spots(self, image: bytes, mime: str) -> Reading[ReadPlace]: ...

    async def roads(
        self, image: bytes, mime: str, places: list[ReadPlace]
    ) -> Reading[ReadRoad]: ...
