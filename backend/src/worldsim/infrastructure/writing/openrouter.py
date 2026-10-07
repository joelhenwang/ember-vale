"""Ask a text model on OpenRouter for library writing help.

Small, cheap calls: improve a player's rough overview, fill the fields
they left empty. The prompts live in application/library/writing.py.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from worldsim.application.ports.writer import WritingError, Written


class OpenRouterWriter:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        reasoning: str | None = "low",
        max_tokens: int = 12000,
        timeout_s: float = 120.0,
    ) -> None:
        self._key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._reasoning = reasoning
        self._max_tokens = max_tokens
        self._timeout = timeout_s

    async def write(self, prompt: str) -> Written:
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": 0.8,
            "usage": {"include": True},
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._reasoning:
            body["reasoning"] = {"effort": self._reasoning}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                reply = await client.post(
                    self._url, json=body, headers={"Authorization": f"Bearer {self._key}"}
                )
        except httpx.HTTPError as exc:
            raise WritingError(f"writer unreachable: {type(exc).__name__}") from exc
        seconds = round(time.monotonic() - started, 1)
        if reply.status_code != 200:
            raise WritingError(f"writer answered {reply.status_code}: {reply.text[:200]}")
        payload: dict[str, Any] = reply.json()
        usage: dict[str, Any] = payload.get("usage") or {}
        try:
            choice: dict[str, Any] = payload["choices"][0]
            text = str(choice["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise WritingError("the writer sent no answer") from exc
        if not text.strip():
            raise WritingError(f"the writer gave up ({choice.get('finish_reason')})")
        return Written(text, self._model, seconds, float(usage.get("cost") or 0))
