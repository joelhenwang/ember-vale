"""Krea 2 Studio image service over plain HTTP (no authentication; Tailscale only).

One GPU makes one image at a time; a default image takes ~11-12 s and a
busy queue adds every earlier request's time, so the timeout is long.
The checkpoint is shared by every client of the service: it is sent only
as the operator chose it in image preferences. See krea2-studio docs/API.md.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from PIL import Image

from worldsim.application.ports.images import (
    CharacterCard,
    GeneratedImage,
    ImageGenerationError,
    ImageRequest,
)
from worldsim.domain.jsonvalues import json_list, json_object
from worldsim.infrastructure.http_pool import pooled_client

#: Catalog reads are quick; a service this slow to list is not usable.
CATALOG_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class KreaStyle:
    id: str
    label: str


@dataclass(frozen=True)
class KreaCatalog:
    """What the service reports: whether it is up, and what it can draw with."""

    reachable: bool
    loaded: bool = False
    checkpoint: str | None = None
    queued: int = 0
    checkpoints: list[str] = field(default_factory=lambda: [])
    styles: list[KreaStyle] = field(default_factory=lambda: [])
    error: str | None = None


class KreaImageGenerator:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 180.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client

    @staticmethod
    def body(request: ImageRequest) -> dict[str, Any]:
        """The /generate fields; service defaults are left out."""
        body: dict[str, Any] = {
            "prompt": request.prompt,
            "ratio": request.ratio,
            "mode": request.mode,
            "turbo": request.turbo,
        }
        if request.checkpoint:
            body["checkpoint"] = request.checkpoint
        if request.style:
            body["style"] = request.style
            if request.style_scale != 1.0:
                body["style_scale"] = request.style_scale
        if request.pixel:
            body["pixel"] = request.pixel
        if request.seed is not None:
            body["seed"] = request.seed
        if not request.detail or request.detail_scale == 0:
            body["detail"] = False
        elif request.detail_scale != 1.0:
            body["detail_scale"] = request.detail_scale
        if request.steps is not None:
            body["steps"] = request.steps
        if request.characters:
            body["characters"] = list(request.characters)
        if request.references:
            body["references"] = list(request.references)
        return body

    async def ensure_character(self, card: CharacterCard) -> None:
        """Register a character once; an id the service already has is kept.

        Ids carry the portrait's version, so a redrawn portrait registers
        anew instead of reusing an old face.
        """
        client = self._client or pooled_client()
        try:
            known = await client.get(
                f"{self._base_url}/v1/characters/{card.id}", timeout=self._timeout_s
            )
            if known.status_code == 200:
                return
            created = await client.post(
                f"{self._base_url}/v1/characters",
                json={
                    "id": card.id,
                    "name": card.name,
                    "description": card.description,
                    "images": [base64.b64encode(_png(card.image)).decode()],
                },
                timeout=self._timeout_s,
            )
        except httpx.HTTPError as exc:
            raise ImageGenerationError(f"krea unreachable: {exc}") from exc
        if created.status_code == 400 and "already exists" in created.text:
            return  # registered by a concurrent job
        if created.status_code != 200:
            raise ImageGenerationError(
                f"krea character HTTP {created.status_code}: {created.text[:300]}"
            )

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        client = self._client or pooled_client()
        try:
            response = await client.post(
                f"{self._base_url}/generate", json=self.body(request), timeout=self._timeout_s
            )
        except httpx.TimeoutException as exc:
            raise ImageGenerationError("krea request timed out") from exc
        except httpx.HTTPError as exc:
            raise ImageGenerationError(f"krea unreachable: {exc}") from exc
        if response.status_code != 200:
            raise ImageGenerationError(f"krea HTTP {response.status_code}: {response.text[:300]}")
        width, height = _size(response.headers.get("x-size", ""))
        seed_raw = response.headers.get("x-seed")
        return GeneratedImage(
            data=response.content,
            mime=response.headers.get("content-type", "image/png").split(";")[0],
            width=width,
            height=height,
            seed=int(seed_raw) if seed_raw and seed_raw.isdigit() else None,
            seconds=_total_seconds(response.headers.get("x-timings", "")),
        )

    async def catalog(self) -> KreaCatalog:
        """Health, checkpoints and styles, read concurrently with a short timeout."""
        client = self._client or pooled_client()
        replies = await asyncio.gather(
            *(
                client.get(f"{self._base_url}{path}", timeout=CATALOG_TIMEOUT_S)
                for path in ("/health", "/v1/checkpoints", "/v1/styles")
            ),
            return_exceptions=True,
        )
        health, checkpoints, styles = (_json_of(reply) for reply in replies)
        if health is None:
            first = replies[0]
            why = str(first) or type(first).__name__ if isinstance(first, BaseException) else ""
            return KreaCatalog(reachable=False, error=f"unreachable {why}".strip()[:300])
        return KreaCatalog(
            reachable=True,
            loaded=bool(health.get("loaded")),
            checkpoint=_text(health.get("checkpoint")) or _text((checkpoints or {}).get("current")),
            queued=_int(health.get("queued")),
            checkpoints=[
                item_id
                for item in _items(checkpoints)
                if (item_id := _text(item.get("id"))) and item.get("valid", True)
            ],
            styles=[
                KreaStyle(id=item_id, label=_text(item.get("label")) or item_id)
                for item in _items(styles)
                if (item_id := _text(item.get("id")))
            ],
            error=_text(health.get("error")),
        )


def _json_of(reply: httpx.Response | BaseException) -> dict[str, Any] | None:
    if isinstance(reply, BaseException) or reply.status_code != 200:
        return None
    try:
        return json_object(reply.json())
    except ValueError:
        return None


def _items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = json_list((payload or {}).get("data")) or []
    return [item for raw in items if (item := json_object(raw)) is not None]


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _total_seconds(header: str) -> float | None:
    try:
        timings = json_object(json.loads(header))
    except ValueError:
        return None
    total = (timings or {}).get("total_s")
    return float(total) if isinstance(total, (int, float)) else None


def _png(data: bytes) -> bytes:
    """Stored portraits are WebP; the service is sent PNG, which it always reads."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            out = io.BytesIO()
            source.convert("RGB").save(out, format="PNG")
            return out.getvalue()
    except (OSError, ValueError):
        return data


def _size(header: str) -> tuple[int, int]:
    """X-Size is "WxH"; unknown sizes fall back to the 1:1 default."""
    try:
        width, height = (int(part) for part in header.lower().split("x"))
    except ValueError:
        return 1024, 1024
    return max(1, width), max(1, height)
