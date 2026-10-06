"""Venice as a provider: selection, request body, response, pins, audit rows."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.settings import AdapterKind, ProviderConnection, ProviderProfileRevision
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.profiles import VENICE_CHAT_PROFILE
from worldsim.infrastructure.model_gateway.retry import RetryingGateway
from worldsim.infrastructure.model_gateway.selection import gateway_for_pin, gateways_for_settings
from worldsim.infrastructure.model_gateway.venice import VeniceGateway
from worldsim.infrastructure.ops.logging import secret_values
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _request() -> CompletionRequest:
    return CompletionRequest(prompt="hello", system="You decide", max_tokens=16, json_mode=True)


def _venice_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_PROVIDER__ACTIVE_PROFILE", "venice")
    monkeypatch.setenv("WORLDSIM_PROVIDER__VENICE_API_KEY", "venice-test-key")


def test_selection_wires_venice(monkeypatch: pytest.MonkeyPatch) -> None:
    _venice_env(monkeypatch)
    monkeypatch.setenv("WORLDSIM_PROVIDER__ROLE_MODELS__NARRATOR", "venice-uncensored-role-play")
    gateways, profiles = gateways_for_settings(Settings())
    narrator = gateways["narrator"]
    assert isinstance(narrator, RetryingGateway)
    assert isinstance(
        narrator._inner._inner,  # pyright: ignore[reportAttributeAccessIssue]
        VeniceGateway,
    )  # retry -> hedge -> adapter
    assert profiles["character"].adapter == "venice"
    assert profiles["character"].model_id == "venice-uncensored-1-2"
    assert profiles["narrator"].model_id == "venice-uncensored-role-play"


def test_venice_without_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_PROVIDER__ACTIVE_PROFILE", "venice")
    monkeypatch.delenv("WORLDSIM_PROVIDER__VENICE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="venice profile selected without credentials"):
        Settings()


def test_venice_key_is_masked_in_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    _venice_env(monkeypatch)
    assert "venice-test-key" in secret_values(Settings())


def test_body_drops_venice_system_prompt_and_openrouter_reasoning() -> None:
    def body(level: str | None) -> dict[str, Any]:
        gateway = VeniceGateway(VENICE_CHAT_PROFILE, api_key=SecretStr("k"), reasoning=level)
        return gateway._body(_request())

    plain = body(None)
    assert plain["venice_parameters"] == {"include_venice_system_prompt": False}
    assert plain["response_format"] == {"type": "json_object"}
    assert "reasoning" not in plain
    off = body("off")
    assert "reasoning" not in off
    assert off["venice_parameters"]["disable_thinking"] is True
    assert "reasoning" not in body("low")


def test_venice_response_is_read() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content)})
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "venice-uncensored-1-2",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"action": "wait"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 47, "completion_tokens": 9, "total_tokens": 56},
                "cost": {"usd": 4.09e-05, "diem": 0},
                "venice_parameters": {"include_venice_system_prompt": False},
            },
        )

    async def run() -> Any:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = VeniceGateway(
                VENICE_CHAT_PROFILE,
                api_key=SecretStr("k"),
                base_url="https://api.venice.ai/api/v1",
                client=client,
            )
            return await gateway.complete(_request())

    result = asyncio.run(run())
    assert result.text == '{"action": "wait"}'
    assert (result.prompt_tokens, result.completion_tokens) == (47, 9)
    assert seen[0]["url"] == "https://api.venice.ai/api/v1/chat/completions"
    assert seen[0]["body"]["model"] == "venice-uncensored-1-2"


def test_pinned_venice_connection_builds_a_venice_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_VENICE_KEY", "venice-pin-key")
    connection = ProviderConnection(
        id=uuid4(),
        adapter=AdapterKind.VENICE,
        name="Venice",
        endpoint="https://api.venice.ai/api/v1",
        credential_env="MY_VENICE_KEY",
    )
    pin = ProviderProfileRevision(
        id=uuid4(), connection_id=connection.id, revision=1, model_id="venice-uncensored-1-2"
    )
    gateway = gateway_for_pin("narrator", pin, connection)
    assert isinstance(gateway, RetryingGateway)
    assert isinstance(gateway._inner._inner, VeniceGateway)  # pyright: ignore[reportAttributeAccessIssue]
    assert gateway.profile.adapter == "venice"
    assert gateway.profile.model_id == "venice-uncensored-1-2"


def test_venice_profile_rows_are_allowed(migrated_db: None) -> None:
    async def run() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.traces.ensure_profile(
                    VENICE_CHAT_PROFILE.name,
                    VENICE_CHAT_PROFILE.version,
                    VENICE_CHAT_PROFILE.adapter,
                    VENICE_CHAT_PROFILE.model_id,
                    VENICE_CHAT_PROFILE.max_context_tokens,
                    list(VENICE_CHAT_PROFILE.capabilities),
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())
