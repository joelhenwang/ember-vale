"""Store generated art at the size the game shows it.

The image service returns ~1.5 MB PNGs at 1024 px; a map token is 46 px
and a portrait card 86 px. WebP at 512 px (portraits) or 1280 px wide
(backgrounds, maps) keeps them sharp at a few dozen kilobytes.
"""

from __future__ import annotations

import io

from PIL import Image

from worldsim.application.ports.images import GeneratedImage
from worldsim.domain.assets import AssetKind

#: Longest side kept per kind.
MAX_SIDE: dict[AssetKind, int] = {
    AssetKind.PORTRAIT: 512,
    AssetKind.BACKGROUND: 1280,
    AssetKind.MAP: 1600,
    AssetKind.SCENE: 1280,
}


def shrink(image: GeneratedImage, kind: AssetKind) -> GeneratedImage:
    """WebP no larger than the kind needs; unreadable bytes pass through."""
    try:
        with Image.open(io.BytesIO(image.data)) as source:
            picture = source.convert("RGB")
    except (OSError, ValueError):
        return image
    picture.thumbnail((MAX_SIDE[kind], MAX_SIDE[kind]), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    picture.save(out, format="WEBP", quality=86, method=5)
    return GeneratedImage(
        data=out.getvalue(),
        mime="image/webp",
        width=picture.width,
        height=picture.height,
        seed=image.seed,
    )
