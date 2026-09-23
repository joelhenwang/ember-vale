"""Bounded retry around any model gateway (owned by S3-PROV-001).

Policy, frozen here and in backend/README.md:
- Rate limits retry with the server's `retry_after_s` hint, capped;
  without a hint, exponential backoff applies.
- Timeouts and transport failures retry on a short backoff.
- Refusals and malformed responses never retry: retrying a
  deterministic rejection only burns budget.
- After exhaustion the original error propagates and the graphs
  degrade through their existing fallback paths; retry never
  invents a completion.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelGateway,
    ModelGatewayError,
    ModelProfile,
    ModelRateLimitedError,
    ModelTimeoutError,
    ModelUnavailableError,
    ProbeResult,
)

SleepFn = Callable[[float], Coroutine[Any, Any, None]]

#: Hard bounds so a slow provider cannot stall a phase indefinitely.
MAX_ATTEMPTS = 3
MAX_DELAY_S = 30.0


class RetryingGateway:
    """ModelGateway decorator adding bounded retry with injected sleep."""

    def __init__(
        self,
        inner: ModelGateway,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        base_delay_s: float = 1.0,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self.profile: ModelProfile = inner.profile
        self._inner = inner
        self._max_attempts = max(1, max_attempts)
        self._base_delay_s = max(0.0, base_delay_s)
        self._sleep = sleep

    def _delay(self, attempt: int, hint: float | None) -> float:
        if hint is not None:
            return min(max(0.0, hint), MAX_DELAY_S)
        return min(self._base_delay_s * (2.0**attempt), MAX_DELAY_S)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        last: ModelGatewayError | None = None
        hint: float | None = None
        attempts: list[dict[str, Any]] = []
        for attempt in range(self._max_attempts):
            started = time.monotonic()
            try:
                result = await self._inner.complete(request)
                return result.model_copy(update={"attempts": attempts})
            except ModelRateLimitedError as exc:
                last, hint = exc, exc.retry_after_s
            except (ModelTimeoutError, ModelUnavailableError) as exc:
                last, hint = exc, None
            latency_ms = max(0, int((time.monotonic() - started) * 1000))
            record: dict[str, Any] = {
                "attempt": attempt + 1,
                "error": type(last).__name__ if last is not None else "unknown",
                "latency_ms": latency_ms,
            }
            detail = getattr(last, "detail", None)
            if isinstance(detail, dict):
                record["http_status"] = detail.get("http_status")
                record["usage"] = detail.get("usage")
            attempts.append(record)
            if attempt >= self._max_attempts - 1:
                assert last is not None
                prior = last.detail if isinstance(last.detail, dict) else {}
                last.detail = {**prior, "attempts": attempts}
                raise last
            await self._sleep(self._delay(attempt, hint))
        assert last is not None
        raise last

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return await self._inner.embed(request)

    async def probe(self) -> ProbeResult:
        return await self._inner.probe()
