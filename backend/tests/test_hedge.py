"""Slow live calls get a twin request; the first answer wins."""

from __future__ import annotations

import asyncio

import pytest

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelProfile,
    ModelTimeoutError,
    ProbeResult,
)
from worldsim.infrastructure.model_gateway.hedge import HedgedGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE


class _Timed:
    """Answers each call after the next scripted delay (or raises)."""

    def __init__(self, delays: list[float | Exception]) -> None:
        self.profile: ModelProfile = FAKE_TEST_PROFILE
        self._delays = delays
        self.calls = 0
        self.cancelled = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        step = self._delays[self.calls]
        self.calls += 1
        call = self.calls
        if isinstance(step, Exception):
            raise step
        try:
            await asyncio.sleep(step)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return CompletionResult(
            text=f"call {call}",
            prompt_tokens=1,
            completion_tokens=1,
            model="m",
            profile_version="v",
            latency_ms=int(step * 1000),
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        raise AssertionError

    async def probe(self) -> ProbeResult:
        raise AssertionError


REQUEST = CompletionRequest(prompt="p", max_tokens=8)


def test_a_fast_call_is_never_doubled() -> None:
    inner = _Timed([0.01])
    hedged = HedgedGateway(inner, after_s=0.2)
    assert asyncio.run(hedged.complete(REQUEST)).text == "call 1"
    assert (inner.calls, hedged.hedges) == (1, 0)


def test_a_slow_call_loses_to_its_twin() -> None:
    inner = _Timed([2.0, 0.01])
    hedged = HedgedGateway(inner, after_s=0.05)
    assert asyncio.run(hedged.complete(REQUEST)).text == "call 2"
    assert (inner.calls, hedged.hedges, inner.cancelled) == (2, 1, 1)


def test_a_failing_twin_does_not_beat_a_slow_success() -> None:
    inner = _Timed([0.2, ModelTimeoutError("twin failed")])
    hedged = HedgedGateway(inner, after_s=0.05)
    assert asyncio.run(hedged.complete(REQUEST)).text == "call 1"


def test_both_failing_raises() -> None:
    inner = _Timed([ModelTimeoutError("slow fail"), ModelTimeoutError("twin fail")])
    hedged = HedgedGateway(inner, after_s=0.0001)
    with pytest.raises(ModelTimeoutError):
        asyncio.run(hedged.complete(REQUEST))


def test_a_twin_is_recorded_with_its_winner() -> None:
    fast = HedgedGateway(_Timed([0.01]), after_s=0.2)
    assert asyncio.run(fast.complete(REQUEST)).hedge is None
    twin_won = HedgedGateway(_Timed([2.0, 0.01]), after_s=0.05)
    assert asyncio.run(twin_won.complete(REQUEST)).hedge == {
        "twin_fired": True,
        "winner": "twin",
        "after_s": 0.05,
    }
    first_won = HedgedGateway(_Timed([0.2, 5.0]), after_s=0.05)
    assert asyncio.run(first_won.complete(REQUEST)).hedge == {
        "twin_fired": True,
        "winner": "first",
        "after_s": 0.05,
    }


def test_a_twin_that_also_failed_is_named_in_the_error() -> None:
    class _BothFail(_Timed):
        async def complete(self, request: CompletionRequest) -> CompletionResult:
            self.calls += 1
            await asyncio.sleep(0.05 if self.calls == 1 else 0.0)
            raise ModelTimeoutError(f"call {self.calls} failed")

    hedged = HedgedGateway(_BothFail([]), after_s=0.01)
    with pytest.raises(ModelTimeoutError) as caught:
        asyncio.run(hedged.complete(REQUEST))
    assert (caught.value.detail or {})["hedge"]["twin_fired"] is True


def test_background_summaries_are_not_hedged_and_roles_can_be_set() -> None:
    from worldsim.infrastructure.model_gateway.selection import hedge_after

    assert hedge_after("summary", None) == 0.0  # day-end summaries and digests
    assert hedge_after("character", None) == 4.0
    assert hedge_after("summary", None, {"summary": 10.0}) == 10.0
    assert hedge_after("character", 12.0, {"character": 3.0}) == 3.0  # role wins
    assert hedge_after("narrator", 12.0, {"character": 3.0}) == 12.0
