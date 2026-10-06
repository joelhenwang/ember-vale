"""Narration that finishes after a beat returns.

A beat's narration took 3.5-4.5 s of a 10-13 s turn, at the very end.
With this, the beat returns once its scenes commit; the Adventure screen
shows "still being written" for a scene until its words arrive. The next
beat in the same story first waits for these, so beats never overlap,
and it narrates any committed scene still without words (a process that
stopped mid-narration) before it starts.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any
from uuid import UUID

_log = logging.getLogger(__name__)


class BackgroundNarration:
    def __init__(self) -> None:
        self._tasks: dict[UUID, set[asyncio.Future[Any]]] = {}

    def start(self, world_id: UUID, work: Awaitable[Any]) -> None:
        """Run ``work`` for this story without waiting for it."""
        task = asyncio.ensure_future(work)
        running = self._tasks.setdefault(world_id, set())
        running.add(task)

        def _done(finished: asyncio.Future[Any]) -> None:
            running.discard(finished)
            if not finished.cancelled() and finished.exception() is not None:
                _log.error(
                    "background narration failed for %s",
                    world_id,
                    exc_info=finished.exception(),
                )

        task.add_done_callback(_done)

    async def settle(self, world_id: UUID) -> None:
        """Wait for this story's narration still running (errors already logged)."""
        running = list(self._tasks.get(world_id, ()))
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    async def drain(self) -> None:
        """Wait for every story's narration (shutdown)."""
        running = [task for tasks in self._tasks.values() for task in tasks]
        if running:
            await asyncio.gather(*running, return_exceptions=True)
