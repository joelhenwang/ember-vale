"""World reads shared by the context builders of one phase of a beat.

Every decision and reaction built its context from ~15 queries, half of
them the same for everyone: the world's config and clock, its rumours,
places, people and who is on the road (docs/evidence/perf-beat-001).
Within a phase nothing changes those, so one read serves every builder:

- decisions: from the start of the decide gather until the director (which
  runs beside them and may add a rumour, a place or a newcomer) finishes,
  when the view is dropped and read again;
- reactions: across the scene preparations, which only read; dropped
  before the first scene commits (redone scenes read fresh).

The view is carried by a ContextVar set around those regions, so nothing
else in the beat sees it. ``VERIFY`` (tests, ``beat_bench.py
--verify-reads``) builds every context a second time from fresh reads and
fails on any difference, byte for byte.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

#: Build every shared-read context again from fresh reads and compare.
VERIFY = False


class PhaseReads:
    """Memoised loads for one phase; concurrent askers share one load."""

    def __init__(self) -> None:
        self._memo: dict[object, asyncio.Future[Any]] = {}

    async def get[T](self, key: object, load: Callable[[], Awaitable[T]]) -> T:
        found = self._memo.get(key)
        if found is None:
            found = asyncio.ensure_future(load())
            self._memo[key] = found
            try:
                return await asyncio.shield(found)
            except BaseException:
                if self._memo.get(key) is found:
                    del self._memo[key]  # a failed load is not remembered
                raise
        return await asyncio.shield(found)

    def drop(self) -> None:
        """Forget everything: the world changed (the director finished)."""
        self._memo.clear()


_ACTIVE: ContextVar[PhaseReads | None] = ContextVar("phase_reads", default=None)


def active() -> PhaseReads | None:
    return _ACTIVE.get()


@contextmanager
def sharing(reads: PhaseReads | None) -> Generator[PhaseReads | None]:
    """Share ``reads`` with every task started inside (None: read fresh)."""
    token = _ACTIVE.set(reads)
    try:
        yield reads
    finally:
        _ACTIVE.reset(token)
