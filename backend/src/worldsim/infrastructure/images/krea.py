"""Krea 2 Studio image service over plain HTTP (no authentication; Tailscale only).

One GPU makes one image at a time; a default image takes ~11-12 s and a
busy queue adds every earlier request's time, so the timeout is long.
The client never switches checkpoints: that changes the model for every
other user of the service. See krea2-studio docs/API.md.
"""

from __future__ import annotations

from typing import Any

import httpx

from worldsim.application.ports.images import (
    GeneratedImage,
    ImageGenerationError,
    ImageRequest,
)


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

    def _body(self, request: ImageRequest) -> dict[str, Any]:
        body: dict[str, Any] = {"prompt": request.prompt, "ratio": request.ratio}
        if request.style:
            body["style"] = request.style
        if request.pixel:
            body["pixel"] = request.pixel
        if request.seed is not None:
            body["seed"] = request.seed
        return body

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        client = self._client or httpx.AsyncClient(timeout=self._timeout_s)
        try:
            try:
                response = await client.post(f"{self._base_url}/generate", json=self._body(request))
            except httpx.TimeoutException as exc:
                raise ImageGenerationError("krea request timed out") from exc
            except httpx.HTTPError as exc:
                raise ImageGenerationError(f"krea unreachable: {exc}") from exc
        finally:
            if self._client is None:
                await client.aclose()
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
        )


def _size(header: str) -> tuple[int, int]:
    """X-Size is "WxH"; unknown sizes fall back to the 1:1 default."""
    try:
        width, height = (int(part) for part in header.lower().split("x"))
    except ValueError:
        return 1024, 1024
    return max(1, width), max(1, height)
