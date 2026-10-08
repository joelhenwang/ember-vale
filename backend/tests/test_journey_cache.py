"""Renown counts are reused until the story moves on."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import uuid4

from worldsim.application.queries.presentation import JourneyCache
from worldsim.application.unit_of_work import UnitOfWork


class _Scenes:
    def __init__(self) -> None:
        self.calls = 0

    async def journey_counts(self, world_id: Any, character_id: Any) -> tuple[int, int, int]:
        self.calls += 1
        return (self.calls, 0, 0)


class _Uow:
    def __init__(self) -> None:
        self.scenes = _Scenes()


def test_counts_are_reused_until_a_new_event() -> None:
    cache = JourneyCache(size=2)
    raw = _Uow()
    uow = cast(UnitOfWork, raw)
    world, me = uuid4(), uuid4()

    async def run() -> None:
        assert await cache.counts(uow, world, me, 10) == (1, 0, 0)
        assert await cache.counts(uow, world, me, 10) == (1, 0, 0)
        assert raw.scenes.calls == 1
        # A scene committed: its event moves the key on.
        assert await cache.counts(uow, world, me, 11) == (2, 0, 0)
        # Old entries fall out past the size.
        await cache.counts(uow, world, uuid4(), 11)
        assert await cache.counts(uow, world, me, 10) == (4, 0, 0)

    asyncio.run(run())
