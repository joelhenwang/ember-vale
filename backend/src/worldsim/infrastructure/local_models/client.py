"""HTTP client for the local model service (see local-models/ at the repo root)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from worldsim.application.ports.local_models import (
    Embeddings,
    EmbedKind,
    LocalModelsUnavailable,
    Span,
)
from worldsim.infrastructure.http_pool import pooled_client

#: After a failure, calls fail fast for this long instead of each one
#: waiting out a timeout against a service that is off.
BACKOFF_S = 30.0


class _EmbedReply(BaseModel):
    vectors: list[list[float]]
    model: str


class _SpanReply(BaseModel):
    text: str
    start: int
    end: int
    confidence: float


class _ExtractReply(BaseModel):
    results: list[dict[str, list[_SpanReply]]]


class LocalModelsClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout_s
        self._clock = clock
        #: Per endpoint, so extraction being off never blocks embeddings.
        self._down_until: dict[str, float] = {}

    async def _post(self, path: str, body: dict[str, Any], limit_s: float) -> bytes:
        if self._clock() < self._down_until.get(path, 0.0):
            raise LocalModelsUnavailable(f"{path}: backing off after a failure")
        try:
            return await self._send(path, body, limit_s)
        except LocalModelsUnavailable:
            self._down_until[path] = self._clock() + BACKOFF_S
            raise

    async def _send(self, path: str, body: dict[str, Any], limit_s: float) -> bytes:
        try:
            if self._transport is None:
                response = await pooled_client().post(
                    f"{self._base_url}{path}", json=body, timeout=limit_s
                )
            else:  # tests stand in a transport
                async with httpx.AsyncClient(timeout=limit_s, transport=self._transport) as client:
                    response = await client.post(f"{self._base_url}{path}", json=body)
        except httpx.HTTPError as exc:
            raise LocalModelsUnavailable(f"{path}: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise LocalModelsUnavailable(f"{path}: HTTP {response.status_code}")
        return response.content

    async def embed(self, texts: list[str], kind: EmbedKind) -> Embeddings:
        # Indexing batches get longer than a single query.
        limit = self._timeout if len(texts) <= 4 else max(self._timeout, 30.0)
        raw = await self._post("/embed", {"texts": texts, "kind": kind}, limit)
        try:
            reply = _EmbedReply.model_validate_json(raw)
        except ValidationError as exc:
            raise LocalModelsUnavailable("/embed: unexpected reply") from exc
        if len(reply.vectors) != len(texts):
            raise LocalModelsUnavailable("/embed: wrong number of vectors")
        return Embeddings(vectors=reply.vectors, model=reply.model)

    async def extract(
        self, texts: list[str], labels: dict[str, str], threshold: float = 0.5
    ) -> list[list[Span]]:
        limit = max(self._timeout, 1.0 * len(texts))
        raw = await self._post(
            "/extract", {"texts": texts, "labels": labels, "threshold": threshold}, limit
        )
        try:
            reply = _ExtractReply.model_validate_json(raw)
        except ValidationError as exc:
            raise LocalModelsUnavailable("/extract: unexpected reply") from exc
        if len(reply.results) != len(texts):
            raise LocalModelsUnavailable("/extract: wrong number of results")
        return [
            sorted(
                (
                    Span(label, s.text, s.start, s.end, s.confidence)
                    for label, spans in found.items()
                    for s in spans
                ),
                key=lambda span: span.start,
            )
            for found in reply.results
        ]
