"""Re-encode stored map pictures (PNG/JPEG) as WebP, at most 2560 px.

New uploads are already kept as WebP (routes/world_maps.MAP_MAX_SIDE);
this converts what was stored before. The original file is kept next to
the new one (nothing is deleted), and only the asset record's content
reference, mime and size change, so the picture keeps its id. Aspect
ratios are preserved, and map readings are stored in 0-1000 coordinates,
so pins and roads stay where they were.

Run where the assets live. For the compose API container (Git Bash needs
MSYS_NO_PATHCONV=1 so the /app path is not rewritten):

    MSYS_NO_PATHCONV=1 docker compose exec -T \\
        -e MAPS_TO_WEBP_ROOT=/app/content/assets api \\
        python - < backend/scripts/maps_to_webp.py

Add ``-e MAPS_TO_WEBP_APPLY=1`` to write; by default it only reports.
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

from PIL import Image
from sqlalchemy import text

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.settings import Settings

MAX_SIDE = 2560


def assets_root() -> Path:
    """Where the API serves from: <repo>/content/assets (/app/content/assets in the image)."""
    return Path(os.environ.get("MAPS_TO_WEBP_ROOT", "../content/assets"))


async def main(root: Path) -> None:
    apply = os.environ.get("MAPS_TO_WEBP_APPLY") == "1"
    settings = Settings()
    engine = create_engine(settings)
    before = after = 0
    try:
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, content_ref FROM asset_record WHERE kind = 'map' "
                        "AND mime IN ('image/png', 'image/jpeg') "
                        "AND content_ref LIKE 'generated/%'"
                    )
                )
            ).all()
            for asset_id, ref in rows:
                source = root / ref
                if not source.exists():
                    print(f"missing  {ref}")
                    continue
                with Image.open(source) as picture:
                    rgb = picture.convert("RGB")
                rgb.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                rgb.save(out, format="WEBP", quality=90, method=5)
                new_ref = str(Path(ref).with_suffix(".webp")).replace("\\", "/")
                size = source.stat().st_size
                before += size
                after += len(out.getvalue())
                print(f"{size // 1024:>6} KB -> {len(out.getvalue()) // 1024:>5} KB  {ref}")
                if not apply:
                    continue
                (root / new_ref).write_bytes(out.getvalue())
                await conn.execute(
                    text(
                        "UPDATE asset_record SET content_ref = :ref, mime = 'image/webp', "
                        "width = :w, height = :h WHERE id = :id"
                    ),
                    {"ref": new_ref, "w": rgb.width, "h": rgb.height, "id": asset_id},
                )
    finally:
        await engine.dispose()
    verb = "converted" if apply else "would convert"
    print(f"{verb} {len(rows)} maps: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")


if __name__ == "__main__":
    asyncio.run(main(assets_root()))
