"""Background work for the local models: recall vectors and place mentions.

Runs beside the beat loop, never inside it, so a slow or stopped local
service costs a story nothing; rows simply wait for their vector, and
recall by relevance treats an unindexed row as it always did.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from worldsim.application.ports.local_models import LocalModels, LocalModelsUnavailable
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.rules.mentions import MENTION_LABELS, MENTION_MODEL

_log = logging.getLogger(__name__)

#: How long to wait before asking a failing service again.
RETRY_AFTER_S = 60.0


class RecallIndexer:
    def __init__(
        self,
        factory: Callable[[], UnitOfWork],
        models: LocalModels,
        *,
        batch: int = 32,
        poll_seconds: float = 5.0,
    ) -> None:
        self._factory = factory
        self._models = models
        self._batch = batch
        self._poll_seconds = poll_seconds
        #: Learned from the service's first answer; vectors are filed under it.
        self._model: str | None = None
        self._stopping = asyncio.Event()

    async def _model_name(self) -> str:
        if self._model is None:
            self._model = (await self._models.embed(["probe"], "query")).model
        return self._model

    async def run_once(self) -> int:
        """Embed one batch of unindexed rows; how many were stored."""
        model = await self._model_name()
        async with self._factory() as uow:
            sources = await uow.recall.unindexed(model, self._batch)
        if not sources:
            # Ask again next pass: a restarted service may file under a new model.
            self._model = None
            return 0
        found = await self._models.embed([s.text for s in sources], "document")
        if found.model != model:
            # The service switched models under us: start over under the new name.
            self._model = None
            return 0
        async with self._factory() as uow:
            await uow.recall.store(model, sources, found.vectors)
            await uow.commit()
        return len(sources)

    async def run_forever(self) -> None:
        await _loop(self.run_once, self._stopping, self._poll_seconds, "recall indexer")

    async def stop(self) -> None:
        self._stopping.set()


class MentionReader:
    """Reads new lines with GLiNER and caches the place spans it finds.

    The director looks these up instead of waiting ~160 ms a line; a line
    not read yet falls back to the noun list, so nothing ever blocks.
    """

    def __init__(
        self,
        factory: Callable[[], UnitOfWork],
        models: LocalModels,
        *,
        batch: int = 8,
        poll_seconds: float = 5.0,
    ) -> None:
        self._factory = factory
        self._models = models
        self._batch = batch
        self._poll_seconds = poll_seconds
        self._stopping = asyncio.Event()

    async def run_once(self) -> int:
        """Read one batch of new lines; how many were cached."""
        async with self._factory() as uow:
            lines = await uow.mentions.unread(MENTION_MODEL, self._batch)
        if not lines:
            return 0
        found = await self._models.extract(lines, MENTION_LABELS)
        places = [[span.text for span in spans if span.label == "place"] for spans in found]
        async with self._factory() as uow:
            await uow.mentions.store(MENTION_MODEL, lines, places)
            await uow.commit()
        return len(lines)

    async def run_forever(self) -> None:
        await _loop(self.run_once, self._stopping, self._poll_seconds, "mention reader")

    async def stop(self) -> None:
        self._stopping.set()


async def _loop(
    work: Callable[[], Awaitable[int]], stopping: asyncio.Event, poll_seconds: float, name: str
) -> None:
    while not stopping.is_set():
        wait = poll_seconds
        try:
            done = await work()
            if done:
                _log.info("%s handled %d rows", name, done)
                wait = 0.0
        except LocalModelsUnavailable as exc:
            _log.info("%s waiting: %s", name, exc)
            wait = RETRY_AFTER_S
        except Exception:  # keep the loop alive; the next pass retries
            _log.exception("%s pass failed", name)
            wait = RETRY_AFTER_S
        try:
            await asyncio.wait_for(stopping.wait(), timeout=wait or 0.01)
        except TimeoutError:
            pass
