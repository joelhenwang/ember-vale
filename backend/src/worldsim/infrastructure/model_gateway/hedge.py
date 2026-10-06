"""Hedged completions: a slow call gets a twin, and the first answer wins.

Live calls usually answer in 2-7 s, but now and then one takes 20 s or
more (provider-side), and a turn waits for its slowest call. After
``after_s`` without an answer a second identical request starts; the
first to succeed is used and the other is cancelled. Only slow calls
pay for a duplicate. Failures are not hedged around: if a call fails
before the hedge starts, the error propagates for the retry layer.
"""

from __future__ import annotations

import asyncio
import contextlib

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelGateway,
    ModelProfile,
    ProbeResult,
)

#: Default wait before a twin request starts (live calls: p50 ~3 s, p90 ~7 s).
HEDGE_AFTER_S = 10.0


class HedgedGateway:
    def __init__(self, inner: ModelGateway, *, after_s: float = HEDGE_AFTER_S) -> None:
        self.profile: ModelProfile = inner.profile
        self._inner = inner
        self._after_s = after_s
        #: How many twins were started (for tests and diagnostics).
        self.hedges = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        first = asyncio.ensure_future(self._inner.complete(request))
        done, _ = await asyncio.wait({first}, timeout=self._after_s)
        if done:
            return first.result()
        self.hedges += 1
        second = asyncio.ensure_future(self._inner.complete(request))
        pending = {first, second}
        error: BaseException | None = None
        try:
            while pending:
                finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in finished:
                    if task.exception() is None:
                        return task.result()
                    error = task.exception()
            assert error is not None
            raise error
        finally:
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return await self._inner.embed(request)

    async def probe(self) -> ProbeResult:
        return await self._inner.probe()
