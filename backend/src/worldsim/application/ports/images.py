"""Image generation port: one prompt in, one stored-ready image out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    #: One of the provider's aspect ratios ("1:1", "16:9", "3:2", ...).
    ratio: str
    #: A style LoRA id, when the style pack is painted rather than pixel art.
    style: str | None = None
    #: A pixel-art grid ("32", "64", "128"), for pixel style packs.
    pixel: str | None = None
    #: Same seed and fields give the same image.
    seed: int | None = None
    #: The model weights; shared by every client of the service.
    checkpoint: str | None = None
    #: draft (~768 px), fast (default) or full (~35% slower).
    mode: str = "fast"
    #: The detail LoRA and its strength (1.0 is free; other values cost time).
    detail: bool = True
    detail_scale: float = 1.0
    #: The 4-step Turbo LoRA; off defaults to 8 steps.
    turbo: bool = True
    steps: int | None = None
    style_scale: float = 1.0


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime: str
    width: int
    height: int
    seed: int | None = None
    #: Seconds the service spent, when it reports them.
    seconds: float | None = None


class ImageGenerationError(Exception):
    """The provider could not make the image (unreachable, rejected, loading)."""


class ImageGenerator(Protocol):
    async def generate(self, request: ImageRequest) -> GeneratedImage: ...
