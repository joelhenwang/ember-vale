"""OpenRouter adapter over plain HTTPS (owned by S0-MODEL-001).

No provider SDK is used: one httpx client talks to the OpenAI-compatible
endpoints, and every failure maps to the normalized gateway taxonomy.
"""

from __future__ import annotations

import os
import time
from typing import Any, cast

import httpx
from pydantic import SecretStr

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelMalformedError,
    ModelProfile,
    ModelRateLimitedError,
    ModelRefusalError,
    ModelTimeoutError,
    ModelUnavailableError,
    ProbeResult,
)

DIAG_BODY_MAX = 4096


def _body_capture_enabled() -> bool:
    """Bounded full-body capture: local DB only, off by default."""
    return os.environ.get("WORLDSIM_MODEL_DIAG_BODY") == "1"


def _retry_after_s(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class OpenRouterGateway:
    def __init__(
        self,
        profile: ModelProfile,
        *,
        api_key: SecretStr,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_s: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.profile = profile
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._owned_client = client is None

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=self._timeout_s)

    async def _close_owned(self, client: httpx.AsyncClient) -> None:
        if self._owned_client:
            await client.aclose()

    def _body(self, request: CompletionRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, Any] = {
            "model": self.profile.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.top_k is not None:
            body["top_k"] = request.top_k
        return body

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        client = self._client_or_create()
        started = time.monotonic()
        try:
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=self._body(request),
                    headers=self._auth_headers(),
                )
            except httpx.TimeoutException as exc:
                raise ModelTimeoutError("openrouter request timed out") from exc
            except httpx.HTTPError as exc:
                raise ModelUnavailableError(f"openrouter transport failed: {exc}") from exc
            latency_ms = max(0, int((time.monotonic() - started) * 1000))
            return self._read_completion(response, latency_ms)
        finally:
            await self._close_owned(client)

    @staticmethod
    def _usage_of(payload: dict[str, Any]) -> dict[str, int]:
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        details = usage.get("completion_tokens_details")
        reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else 0
        return {
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "reasoning_tokens": int(reasoning or 0),
        }

    @staticmethod
    def _payload_or_none(response: httpx.Response) -> dict[str, Any] | None:
        """Best-effort envelope for HTTP failures; never raises."""
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _diag(
        response: httpx.Response,
        payload: dict[str, Any] | None,
        content: Any,
        raw_body: str | None = None,
    ) -> dict[str, Any]:
        """Provider-boundary facts. No headers, no credentials, no prompts."""
        choices = payload.get("choices") if isinstance(payload, dict) else None
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        diag: dict[str, Any] = {
            "http_status": response.status_code,
            "response_id": payload.get("id") if isinstance(payload, dict) else None,
            "model": payload.get("model") if isinstance(payload, dict) else None,
            "finish_reason": first.get("finish_reason") if isinstance(first, dict) else None,
            "usage": OpenRouterGateway._usage_of(payload) if isinstance(payload, dict) else None,
            "choices_count": len(choices) if isinstance(choices, list) else None,
            "content_type": type(content).__name__,
            "content_length": len(content) if isinstance(content, str) else None,
        }
        if raw_body is not None:
            diag["raw_body"] = raw_body
        error = payload.get("error") if isinstance(payload, dict) else None
        if error is not None:
            if isinstance(error, (str, int, float)):
                diag["provider_error"] = error
            else:
                diag["provider_error"] = str(error)[:500]
        refusal = message.get("refusal") if isinstance(message, dict) else None
        if refusal is not None:
            diag["refusal"] = str(refusal)[:500]
        return diag

    @staticmethod
    def _captured_body(response: httpx.Response) -> str | None:
        if not _body_capture_enabled():
            return None
        try:
            return response.text[:DIAG_BODY_MAX]
        except Exception:
            return None

    def _read_completion(self, response: httpx.Response, latency_ms: int) -> CompletionResult:
        if response.status_code == 429:
            raise ModelRateLimitedError(
                "openrouter rate limited",
                retry_after_s=_retry_after_s(response),
                detail=self._diag(
                    response,
                    self._payload_or_none(response),
                    None,
                    self._captured_body(response),
                ),
            )
        if response.status_code >= 400:
            raise ModelUnavailableError(
                f"openrouter rejected the request: HTTP {response.status_code}",
                detail=self._diag(
                    response,
                    self._payload_or_none(response),
                    None,
                    self._captured_body(response),
                ),
            )
        try:
            raw: Any = response.json()
        except ValueError as exc:
            raise ModelMalformedError(
                "openrouter returned invalid JSON",
                detail=self._diag(response, None, None, raw_body=self._captured_body(response)),
            ) from exc
        if not isinstance(raw, dict):
            raise ModelMalformedError(
                "openrouter returned a non-object payload",
                detail=self._diag(response, None, None, raw_body=self._captured_body(response)),
            )
        payload = cast("dict[str, Any]", raw)
        choices_raw = payload.get("choices")
        if not isinstance(choices_raw, list) or not choices_raw:
            raise ModelMalformedError(
                "openrouter response has no choices",
                detail=self._diag(response, payload, None, raw_body=self._captured_body(response)),
            )
        choices = cast("list[Any]", choices_raw)
        choice_raw = choices[0]
        if not isinstance(choice_raw, dict):
            raise ModelMalformedError(
                "openrouter response has no choices",
                detail=self._diag(response, payload, None, raw_body=self._captured_body(response)),
            )
        choice = cast("dict[str, Any]", choice_raw)
        if choice.get("finish_reason") == "content_filter":
            raise ModelRefusalError(
                "openrouter refused the prompt",
                detail=self._diag(response, payload, None),
            )
        message_raw = choice.get("message")
        if not isinstance(message_raw, dict):
            raise ModelMalformedError(
                "openrouter response has no message",
                detail=self._diag(response, payload, None, raw_body=self._captured_body(response)),
            )
        message = cast("dict[str, Any]", message_raw)
        text = message.get("content")
        if not isinstance(text, str) or not text:
            raise ModelMalformedError(
                "openrouter response has no message text",
                detail=self._diag(
                    response, payload, text, self._captured_body(response)
                ),
            )
        usage = self._usage_of(payload)
        model_raw = payload.get("model")
        model = model_raw if isinstance(model_raw, str) and model_raw else self.profile.model_id
        return CompletionResult(
            text=text,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            model=model,
            profile_version=self.profile.version,
            latency_ms=latency_ms,
            reasoning_tokens=usage["reasoning_tokens"],
            finish_reason=choice.get("finish_reason")
            if isinstance(choice.get("finish_reason"), str)
            else None,
            response_id=payload.get("id")
            if isinstance(payload.get("id"), str)
            else None,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        client = self._client_or_create()
        try:
            try:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    json={"model": self.profile.model_id, "input": request.texts},
                    headers=self._auth_headers(),
                )
            except httpx.TimeoutException as exc:
                raise ModelTimeoutError("openrouter request timed out") from exc
            except httpx.HTTPError as exc:
                raise ModelUnavailableError(f"openrouter transport failed: {exc}") from exc
            return self._read_embeddings(response)
        finally:
            await self._close_owned(client)

    def _read_embeddings(self, response: httpx.Response) -> EmbeddingResult:
        if response.status_code == 429:
            raise ModelRateLimitedError(
                "openrouter rate limited", retry_after_s=_retry_after_s(response)
            )
        if response.status_code >= 400:
            raise ModelUnavailableError(
                f"openrouter rejected the request: HTTP {response.status_code}",
                detail=self._diag(
                    response,
                    self._payload_or_none(response),
                    None,
                    self._captured_body(response),
                ),
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelMalformedError("openrouter returned invalid JSON") from exc
        try:
            vectors = [item["embedding"] for item in payload["data"]]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelMalformedError("openrouter embedding response has no data") from exc
        if not vectors or any(not isinstance(row, list) or not row for row in vectors):
            raise ModelMalformedError("openrouter embedding response has empty vectors")
        return EmbeddingResult(
            vectors=vectors,
            model=payload.get("model", self.profile.model_id),
            profile_version=self.profile.version,
            dimension=len(vectors[0]),
        )

    async def probe(self) -> ProbeResult:
        client = self._client_or_create()
        started = time.monotonic()
        try:
            try:
                response = await client.get(
                    f"{self._base_url}/models", headers=self._auth_headers()
                )
            except httpx.HTTPError as exc:
                return ProbeResult(
                    ok=False,
                    profile=f"{self.profile.name}@{self.profile.version}",
                    latency_ms=0,
                    detail=f"probe transport failed: {exc}",
                )
            latency_ms = max(0, int((time.monotonic() - started) * 1000))
            if response.status_code != 200:
                return ProbeResult(
                    ok=False,
                    profile=f"{self.profile.name}@{self.profile.version}",
                    latency_ms=latency_ms,
                    detail=f"probe HTTP {response.status_code}",
                )
            try:
                count = len(response.json().get("data", []))
            except ValueError:
                count = 0
            return ProbeResult(
                ok=True,
                profile=f"{self.profile.name}@{self.profile.version}",
                latency_ms=latency_ms,
                detail=f"{count} models listed",
            )
        finally:
            await self._close_owned(client)
