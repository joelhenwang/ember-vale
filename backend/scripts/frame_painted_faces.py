"""Find the face on painted portraits that have no face frame yet.

    uv run python scripts/frame_painted_faces.py --assets ../content/assets \\
        [--world WORLD_ID] [--sheet faces.png] [--dry-run]

New portraits get their face frame when the image runner paints them; this
backfills the ones painted before. Only each character's newest portrait is
read, and imported pictures (framed by hand) are left alone. Needs
WORLDSIM_DATABASE__URL and WORLDSIM_PROVIDER__OPENROUTER_API_KEY; one read
costs about $0.0005. --sheet draws every portrait with its face circle.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from PIL import Image, ImageDraw

from worldsim.application.ports.map_reader import MapReader, Reading
from worldsim.application.stories.create import PORTRAIT_FRAMES
from worldsim.domain.assets import AssetKind, AssetRecord
from worldsim.domain.framing import Frame
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.geography.openrouter import OpenRouterMapReader
from worldsim.infrastructure.images.runner import frame_face
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.storage.local import LocalStorage

TILE = 256


class _Costed:
    """The reader, adding up what it costs."""

    def __init__(self, reader: MapReader) -> None:
        self._reader = reader
        self.cost = 0.0
        self.seconds: list[float] = []

    async def face(self, image: bytes, mime: str) -> Reading[tuple[int, int, int, int]]:
        reading = await self._reader.face(image, mime)
        self.cost += reading.cost_usd
        self.seconds.append(reading.seconds)
        return reading


def _tile(data: bytes, face: Frame | None) -> Image.Image:
    with Image.open(io.BytesIO(data)) as source:
        picture = source.convert("RGB").resize((TILE, TILE))
    if face is not None:
        left, top, right, bottom = face.pixels(TILE, TILE)
        ImageDraw.Draw(picture).ellipse((left, top, right, bottom), outline=(255, 64, 64), width=3)
    return picture


async def run(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings()
    key = settings.provider.openrouter_api_key
    if key is None:
        sys.exit("WORLDSIM_PROVIDER__OPENROUTER_API_KEY is not set")
    reader = _Costed(
        OpenRouterMapReader(
            key.get_secret_value().strip(),
            settings.provider.openrouter_base_url,
            settings.maps.places_model,
            settings.maps.roads_model,
            reasoning=settings.maps.reasoning,
            max_tokens=settings.maps.max_tokens,
            timeout_s=settings.maps.timeout_s,
        )
    )
    storage = LocalStorage(Path(args.assets))
    engine = create_engine(settings)
    factory = lambda: create_unit_of_work(engine)  # noqa: E731
    report: list[dict[str, Any]] = []
    tiles: list[Image.Image] = []
    try:
        async with factory() as uow:
            worlds = (
                [UUID(args.world)] if args.world else [w.id for w in await uow.worlds.list_worlds()]
            )
        for world_id in worlds:
            async with factory() as uow:
                assets = await uow.assets.list_ready_for_world(world_id, AssetKind.PORTRAIT.value)
                framed = (await uow.worlds.get_config(world_id)).get(PORTRAIT_FRAMES)
            newest: dict[UUID, AssetRecord] = {}
            for asset in assets:
                if asset.subject_id is None or not asset.content_ref.startswith("generated/"):
                    continue
                held = newest.get(asset.subject_id)
                if held is None or asset.subject_visual_version > held.subject_visual_version:
                    newest[asset.subject_id] = asset
            entries = cast("dict[str, Any]", framed) if isinstance(framed, dict) else {}
            for character_id, asset in newest.items():
                entry = entries.get(str(character_id))
                if isinstance(entry, dict) and entry.get("asset_id") == str(asset.id):
                    continue  # framed already
                try:
                    data = await storage.read(asset.content_ref)
                except (OSError, FileNotFoundError):
                    report.append({"asset_id": str(asset.id), "missing": asset.content_ref})
                    continue
                if args.dry_run:
                    report.append({"asset_id": str(asset.id), "would_read": asset.content_ref})
                    continue
                face = await frame_face(factory, reader, asset, data)
                report.append(
                    {
                        "world_id": str(world_id),
                        "character_id": str(character_id),
                        "asset_id": str(asset.id),
                        "face": None if face is None else [face.x, face.y, face.w, face.h],
                    }
                )
                tiles.append(_tile(data, face))
    finally:
        await engine.dispose()
    if args.sheet and tiles:
        columns = min(6, len(tiles))
        rows = -(-len(tiles) // columns)
        sheet = Image.new("RGB", (columns * TILE, rows * TILE), (24, 24, 24))
        for n, tile in enumerate(tiles):
            sheet.paste(tile, ((n % columns) * TILE, (n // columns) * TILE))
        sheet.save(args.sheet)
    return {
        "model": settings.maps.places_model,
        "read": len(reader.seconds),
        "found": sum(1 for r in report if r.get("face")),
        "cost_usd": round(reader.cost, 5),
        "seconds_each": round(sum(reader.seconds) / len(reader.seconds), 1)
        if reader.seconds
        else 0,
        "portraits": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", required=True, help="the content/assets folder")
    parser.add_argument("--world")
    parser.add_argument("--sheet", help="save a contact sheet with the face circles")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
