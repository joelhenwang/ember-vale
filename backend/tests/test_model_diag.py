"""Provider-boundary diagnostics tests (owned by live-generation followup).

Malformed must record *which* shape failed (not just the category):
HTTP status, response id, finish reason, usage incl. reasoning, choices
count, and content length. Retry attempts are recorded per attempt so
aggregate token totals stay separable from single responses.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from test_stage1_api import ApiClient

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    ModelMalformedError,
    ModelRateLimitedError,
)
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.profiles import (
    FAKE_TEST_PROFILE,
    OPENROUTER_CHAT_PROFILE,
)
from worldsim.infrastructure.model_gateway.retry import RetryingGateway
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_ID = UUID("10000000-0000-4000-8000-000000000001")


def _gateway(payload: Any, status: int = 200) -> OpenRouterGateway:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    return OpenRouterGateway(
        OPENROUTER_CHAT_PROFILE,
        api_key=SecretStr("test-key"),
        client=client,
    )


def _request() -> CompletionRequest:
    return CompletionRequest(prompt="hello", max_tokens=16)


def test_malformed_records_empty_choices_shape() -> None:
    gateway = _gateway({"id": "resp-1", "model": "m", "choices": [], "usage": {}})
    with pytest.raises(ModelMalformedError) as caught:
        asyncio.run(gateway.complete(_request()))
    assert caught.value.detail is not None
    assert caught.value.detail["http_status"] == 200
    assert caught.value.detail["response_id"] == "resp-1"
    assert caught.value.detail["choices_count"] == 0


def test_malformed_records_empty_text_length() -> None:
    gateway = _gateway(
        {
            "id": "resp-2",
            "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
    )
    with pytest.raises(ModelMalformedError) as caught:
        asyncio.run(gateway.complete(_request()))
    assert caught.value.detail is not None
    assert caught.value.detail["finish_reason"] == "stop"
    assert caught.value.detail["content_length"] == 0
    assert caught.value.detail["usage"]["completion_tokens"] == 3


def test_success_carries_reasoning_and_envelope() -> None:
    gateway = _gateway(
        {
            "id": "resp-3",
            "model": "deepseek/x",
            "choices": [
                {"finish_reason": "stop", "message": {"content": '{"a": 1}'}}
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 100,
                "completion_tokens_details": {"reasoning_tokens": 90},
            },
        }
    )
    result = asyncio.run(gateway.complete(_request()))
    assert result.reasoning_tokens == 90
    assert result.finish_reason == "stop"
    assert result.response_id == "resp-3"


class _Scripted:
    def __init__(self, profile: Any, behaviors: list[Any]) -> None:
        self.profile = profile
        self._behaviors = behaviors
        self.calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        behavior = self._behaviors[min(self.calls - 1, len(self._behaviors) - 1)]
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    async def embed(self, request: Any) -> Any:
        raise AssertionError("unused")

    async def probe(self) -> Any:
        raise AssertionError("unused")


def _ok() -> CompletionResult:
    return CompletionResult(
        text='{"ok": true}',
        prompt_tokens=10,
        completion_tokens=5,
        model="m",
        profile_version="v",
        latency_ms=1,
    )


async def _noop(delay: float) -> None:
    return None


def test_retry_records_attempts_on_success() -> None:
    inner = _Scripted(
        FAKE_TEST_PROFILE,
        [ModelRateLimitedError("slow", detail={"http_status": 429}), _ok()],
    )
    gateway = RetryingGateway(inner, sleep=_noop)
    result = asyncio.run(gateway.complete(_request()))
    assert len(result.attempts) == 1
    assert result.attempts[0]["attempt"] == 1
    assert result.attempts[0]["error"] == "ModelRateLimitedError"
    assert result.attempts[0]["http_status"] == 429


def test_retry_attaches_attempts_on_exhaustion() -> None:
    inner = _Scripted(
        FAKE_TEST_PROFILE, [ModelRateLimitedError("slow", detail={"http_status": 429})]
    )
    gateway = RetryingGateway(inner, max_attempts=2, sleep=_noop)
    with pytest.raises(ModelRateLimitedError) as caught:
        asyncio.run(gateway.complete(_request()))
    attempts = (caught.value.detail or {}).get("attempts", [])
    assert [a["attempt"] for a in attempts] == [1, 2]


@pytest.fixture
def failing_app(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)

    def _route(request: Any) -> Any:
        raise ModelMalformedError(
            "probe failure",
            detail={"http_status": 200, "choices_count": 0, "content_length": None},
        )

    gateway.route = _route
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw)


def test_failed_call_persists_diagnostics(failing_app: ApiClient) -> None:
    headers = {"X-Worldsim-Role": "watcher"}
    failing_app.post("/api/v1/world/seed", headers=headers)
    response = failing_app.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(WORLD_ID), "absolute_index": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    async def _read() -> list[Any]:
        engine = create_engine(Settings())
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT error_code, result FROM model_call "
                            "WHERE status = 'failed' LIMIT 5"
                        )
                    )
                ).all()
                return [dict(row._mapping) for row in rows]
        finally:
            await engine.dispose()

    rows = asyncio.run(_read())
    assert rows, "expected failed model_call rows"
    assert rows[0]["result"]["http_status"] == 200
    assert rows[0]["result"]["choices_count"] == 0


def test_body_capture_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORLDSIM_MODEL_DIAG_BODY", raising=False)
    gateway = _gateway(
        {"id": "r-off", "choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
    )
    with pytest.raises(ModelMalformedError) as caught:
        asyncio.run(gateway.complete(_request()))
    assert caught.value.detail is not None
    assert caught.value.detail["content_length"] == 0
    assert "raw_body" not in caught.value.detail


def test_body_capture_on_for_null_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_MODEL_DIAG_BODY", "1")
    gateway = _gateway(
        {"id": "r-on", "choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
    )
    with pytest.raises(ModelMalformedError) as caught:
        asyncio.run(gateway.complete(_request()))
    assert caught.value.detail is not None
    assert "raw_body" in caught.value.detail
    assert json.loads(caught.value.detail["raw_body"])["id"] == "r-on"


def test_body_capture_bounded_for_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_MODEL_DIAG_BODY", "1")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="{" + "x" * 9000)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    gateway = OpenRouterGateway(
        OPENROUTER_CHAT_PROFILE, api_key=SecretStr("test-key"), client=client
    )
    with pytest.raises(ModelMalformedError) as caught:
        asyncio.run(gateway.complete(_request()))
    assert caught.value.detail is not None
    assert len(caught.value.detail["raw_body"]) == 4096


def test_rate_limit_extracts_provider_error_envelope() -> None:
    gateway = _gateway(
        {"error": {"message": "pool throttled", "code": 429}},
        status=429,
    )
    with pytest.raises(ModelRateLimitedError) as caught:
        asyncio.run(gateway.complete(_request()))
    assert caught.value.detail is not None
    assert caught.value.detail["http_status"] == 429
    assert "pool throttled" in str(caught.value.detail.get("provider_error"))


def test_non_string_content_keeps_type() -> None:
    gateway = _gateway(
        {"choices": [{"finish_reason": "stop", "message": {"content": ["a", "b"]}}]},
    )
    with pytest.raises(ModelMalformedError) as caught:
        asyncio.run(gateway.complete(_request()))
    assert caught.value.detail is not None
    assert caught.value.detail["content_type"] == "list"
    assert caught.value.detail["content_length"] is None
