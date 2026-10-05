"""Autoplay commands and the background runner (E5 observatory).

Commands (play, pause, presence) lock the story's autoplay row, apply a
pure rule from ``worldsim.domain.autoplay`` and save. The runner polls
for due stories and advances each through the injected ``advance``
callable, which goes through the same execution gate as a manual step.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime, timedelta
from uuid import UUID

from worldsim.application.execution import LEASE_SECONDS, SlotBusy
from worldsim.application.orchestration.stage1 import Stage1PhaseReport
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.autoplay import (
    BUSY_RETRY_SECONDS,
    AutoplayState,
    AutoplayStatus,
    StopReason,
    beat_committed,
    is_due,
    observers_gone,
    pause,
    play,
    retry_later,
    seen,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.time import absolute_index, utcnow

_log = logging.getLogger("worldsim.autoplay")

Advance = Callable[[UUID, int], Awaitable[Stage1PhaseReport]]
Clock = Callable[[], datetime]


async def _mutate(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    change: Callable[[AutoplayState], AutoplayState],
) -> AutoplayState:
    async with factory() as uow:
        await uow.worlds.get(world_id)  # NOT_FOUND for unknown stories
        current = await uow.autoplay.get(world_id, for_update=True)
        saved = await uow.autoplay.save(change(current))
        await uow.commit()
        return saved


async def read_autoplay(factory: Callable[[], UnitOfWork], world_id: UUID) -> AutoplayState:
    async with factory() as uow:
        await uow.worlds.get(world_id)
        return await uow.autoplay.get(world_id)


async def start_autoplay(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    *,
    delay_seconds: int,
    beat_limit: int,
    now: datetime | None = None,
) -> AutoplayState:
    at = now or utcnow()
    return await _mutate(
        factory,
        world_id,
        lambda s: play(s, now=at, delay_seconds=delay_seconds, beat_limit=beat_limit),
    )


async def pause_autoplay(factory: Callable[[], UnitOfWork], world_id: UUID) -> AutoplayState:
    return await _mutate(factory, world_id, lambda s: pause(s, StopReason.USER))


async def report_presence(
    factory: Callable[[], UnitOfWork], world_id: UUID, now: datetime | None = None
) -> AutoplayState:
    at = now or utcnow()
    return await _mutate(factory, world_id, lambda s: seen(s, at))


class AutoplayRunner:
    """Polls for due stories and runs one beat per story at a time.

    A story being advanced is claimed by pushing ``next_due_at`` past the
    execution lease, so a second runner (another process) skips it; the
    execution gate still guarantees one beat per index either way.
    """

    def __init__(
        self,
        factory: Callable[[], UnitOfWork],
        advance: Advance,
        *,
        clock: Clock = utcnow,
        poll_seconds: float = 1.0,
    ) -> None:
        self._factory = factory
        self._advance = advance
        self._clock = clock
        self._poll_seconds = poll_seconds
        self._inflight: dict[UUID, asyncio.Task[None]] = {}
        self._stopping = asyncio.Event()

    async def tick(self) -> list[asyncio.Task[None]]:
        """Start a beat for every due story not already running here."""
        async with self._factory() as uow:
            due = await uow.autoplay.due(self._clock())
        started: list[asyncio.Task[None]] = []
        for world_id in due:
            if world_id in self._inflight:
                continue
            task = asyncio.create_task(self._run_one(world_id))
            self._inflight[world_id] = task
            task.add_done_callback(lambda _t, w=world_id: self._inflight.pop(w, None))
            started.append(task)
        return started

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.tick()
            except Exception:  # keep polling through transient DB errors
                _log.exception("autoplay tick failed")
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), self._poll_seconds)

    async def stop(self) -> None:
        """Stop polling; beats already admitted finish on their own."""
        self._stopping.set()
        for task in list(self._inflight.values()):
            with suppress(asyncio.CancelledError):
                await task

    async def _claim(self, world_id: UUID) -> int | None:
        """Lock the row, apply stop conditions, and return the index to run."""
        now = self._clock()
        async with self._factory() as uow:
            state = await uow.autoplay.get(world_id, for_update=True)
            if not is_due(state, now):
                return None
            stopped: AutoplayState | None = None
            try:
                entry = await uow.stories.get_catalog(world_id)
                if entry.archived_at is not None:
                    stopped = pause(state, StopReason.ARCHIVED)
            except DomainError as exc:
                if exc.code != ErrorCode.NOT_FOUND:
                    raise
            if stopped is None and observers_gone(state, now):
                stopped = pause(state, StopReason.NO_OBSERVERS)
            if stopped is not None:
                await uow.autoplay.save(stopped)
                await uow.commit()
                return None
            world = await uow.worlds.get(world_id)
            await uow.autoplay.save(
                state.model_copy(update={"next_due_at": now + timedelta(seconds=LEASE_SECONDS)})
            )
            await uow.commit()
            return absolute_index(world.day, world.phase) + 1

    async def _settle(
        self, world_id: UUID, outcome: Callable[[AutoplayState, datetime], AutoplayState]
    ) -> None:
        """Apply a beat's outcome unless someone paused meanwhile."""
        now = self._clock()
        async with self._factory() as uow:
            state = await uow.autoplay.get(world_id, for_update=True)
            if state.status != AutoplayStatus.PLAYING:
                return
            await uow.autoplay.save(outcome(state, now))
            await uow.commit()

    async def _run_one(self, world_id: UUID) -> None:
        index = await self._claim(world_id)
        if index is None:
            return
        try:
            report = await self._advance(world_id, index)
        except SlotBusy:
            await self._settle(world_id, lambda s, now: retry_later(s, now, BUSY_RETRY_SECONDS))
            return
        except Exception as exc:
            detail = str(exc) if isinstance(exc, DomainError) else type(exc).__name__
            _log.warning("autoplay beat %s failed for %s: %s", index, world_id, detail)
            await self._settle(
                world_id, lambda s, _now: pause(s, StopReason.ERROR, f"beat {index}: {detail}")
            )
            return
        if report.duplicate:
            # Someone else committed this index (a manual step); go again.
            await self._settle(world_id, lambda s, now: retry_later(s, now, 0))
            return
        await self._settle(world_id, beat_committed)
