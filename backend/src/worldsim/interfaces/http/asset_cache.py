"""HTTP caching for stored pictures.

An asset's bytes never change under its id (a new painting is a new
asset), so a browser may keep them for a year and revalidate by ETag.
"private": what a viewer may see depends on their role, so shared caches
must not keep it. Permission checks still run before a 304 is answered.
"""

from __future__ import annotations

import asyncio
import io

from fastapi import Request, Response
from PIL import Image

from worldsim.domain.assets import AssetRecord
from worldsim.infrastructure.storage.local import LocalStorage

IMMUTABLE = "private, max-age=31536000, immutable"

#: Widths a picture may be asked for (``?w=``); a request snaps up to the
#: next one, so a handful of variants serve every card, token and banner.
WIDTHS = (96, 160, 240, 320, 480, 640, 960, 1280)
VARIANTS = "generated/.variants"


def snap_width(asset: AssetRecord, wanted: int | None) -> int | None:
    """The variant width to serve, or None for the original bytes."""
    if wanted is None or wanted <= 0:
        return None
    width = next((w for w in WIDTHS if w >= wanted), None)
    if width is None or (asset.width and width >= asset.width):
        return None  # the original is already no wider
    return width


def etag_for(asset: AssetRecord, width: int | None = None) -> str:
    return f'"{asset.id.hex}-w{width}"' if width else f'"{asset.id.hex}"'


def _resized(data: bytes, width: int) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        picture = source.convert("RGBA" if source.mode in ("RGBA", "LA", "P") else "RGB")
    # thumbnail keeps the aspect ratio; the height bound never binds
    picture.thumbnail((width, 100_000), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    picture.save(out, format="WEBP", quality=84, method=4)
    return out.getvalue()


async def picture_bytes(
    storage: LocalStorage, asset: AssetRecord, width: int | None
) -> tuple[bytes, str]:
    """(bytes, mime): the original, or a WebP no wider than ``width``.

    Variants are made once, on first request, and kept beside the
    generated art; the original is never touched.
    """
    if width is None:
        return await storage.read(asset.content_ref), asset.mime
    ref = f"{VARIANTS}/{asset.id.hex}-w{width}.webp"
    try:
        return await storage.read(ref), "image/webp"
    except (FileNotFoundError, OSError):
        pass
    original = await storage.read(asset.content_ref)
    try:
        data = await asyncio.to_thread(_resized, original, width)
    except (OSError, ValueError):
        return original, asset.mime  # unreadable as a picture: serve as stored
    await storage.write(ref, data, "image/webp")
    return data, "image/webp"


def not_modified(request: Request, asset: AssetRecord, width: int | None = None) -> Response | None:
    """A 304 when the browser already holds these bytes, else None."""
    tag = etag_for(asset, width)
    sent = request.headers.get("if-none-match", "")
    tags = {t.strip().removeprefix("W/") for t in sent.split(",") if t.strip()}
    if tag in tags or "*" in tags:
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": IMMUTABLE})
    return None


def asset_response(
    asset: AssetRecord, data: bytes, mime: str | None = None, width: int | None = None
) -> Response:
    return Response(
        content=data,
        media_type=mime or asset.mime,
        headers={"ETag": etag_for(asset, width), "Cache-Control": IMMUTABLE},
    )
