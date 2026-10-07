"""Can a vision model read a world map's terrain as a coarse grid?

Asks each model for one letter per grid cell (water, plains, forest, hills,
mountains, marsh, desert, snow, town) on each map, saves the raw answer and
draws the grid over the map so a person can judge it at a glance.

    uv run python scripts/terrain_eval.py --dir ../docs/evidence/terrain-001 \\
        --maps ../docs/evidence/map-detect-001/maps --model openai/gpt-6-luna

Needs WORLDSIM_PROVIDER__OPENROUTER_API_KEY (read from the environment,
never printed). Runs go to <dir>/runs/<model>.json, overlays to
<dir>/overlays/<model>/<map>.png. Never overwrites an existing run.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw

from worldsim.domain.geography import TERRAIN_COLOURS
from worldsim.infrastructure.geography.openrouter import TERRAIN_PROMPT, parse_terrain

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


def _data_url(path: Path) -> str:
    with Image.open(path) as source:
        picture = source.convert("RGB")
    picture.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    picture.save(out, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def ask(key: str, model: str, image: Path, cols: int, rows: int) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": 40000,
        "temperature": 0,
        "usage": {"include": True},
        "reasoning": {"effort": "low"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_url(image)}},
                    {"type": "text", "text": TERRAIN_PROMPT.format(cols=cols, rows=rows)},
                ],
            }
        ],
    }
    started = time.monotonic()
    reply = httpx.post(
        OPENROUTER, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=600
    )
    seconds = round(time.monotonic() - started, 1)
    reply.raise_for_status()
    payload = reply.json()
    text = str(payload["choices"][0]["message"]["content"] or "")
    cost = float((payload.get("usage") or {}).get("cost") or 0)
    return {"text": text, "seconds": seconds, "cost_usd": cost}


def overlay(image: Path, cells: str, cols: int, rows: int, out: Path) -> None:
    with Image.open(image) as source:
        picture = source.convert("RGBA")
    picture.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", picture.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    w, h = picture.size
    for r in range(rows):
        for c in range(cols):
            letter = cells[r * cols + c]
            colour = TERRAIN_COLOURS.get(letter, "#ff00ff")
            red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
            box = (c * w / cols, r * h / rows, (c + 1) * w / cols, (r + 1) * h / rows)
            draw.rectangle(box, fill=(red, green, blue, 110), outline=(0, 0, 0, 40))
            draw.text((box[0] + 3, box[1] + 2), letter, fill=(0, 0, 0, 200))
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(picture, layer).convert("RGB").save(out, quality=88)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--maps", type=Path, required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--cols", type=int, default=24)
    parser.add_argument("--rows", type=int, default=16)
    args = parser.parse_args()
    key = os.environ.get("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", "").strip()
    if not key:
        print("set WORLDSIM_PROVIDER__OPENROUTER_API_KEY", file=sys.stderr)
        return 2
    maps = sorted(args.maps.glob("*.png")) + sorted(args.maps.glob("*.jpg"))
    for model in args.model:
        slug = model.replace("/", "_")
        run_path = args.dir / "runs" / f"{slug}.json"
        if run_path.exists():
            print(f"{run_path} exists: never overwritten", file=sys.stderr)
            continue
        results: list[dict[str, Any]] = []
        for image in maps:
            answer = ask(key, model, image, args.cols, args.rows)
            grid = parse_terrain(answer["text"], args.cols, args.rows)
            answer.update({"map": image.name, "cells": grid.cells if grid else None})
            if grid:
                overlay(
                    image,
                    grid.cells,
                    args.cols,
                    args.rows,
                    args.dir / "overlays" / slug / image.name,
                )
            counts = {k: grid.cells.count(k) for k in TERRAIN_COLOURS} if grid else {}
            print(model, image.name, answer["seconds"], "s", f"${answer['cost_usd']:.4f}", counts)
            results.append(answer)
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(
            json.dumps(
                {"model": model, "cols": args.cols, "rows": args.rows, "maps": results}, indent=2
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
