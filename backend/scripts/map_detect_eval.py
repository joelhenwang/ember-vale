"""Can a vision model find the places on a painted world map?

Asks each model for every place on each map (name, kind, a pin at the
place's drawing) and scores the pins against hand-marked ground truth
(docs/evidence/map-detect-NNN/truth.json): places found, places
invented, how far pins land, and whether the kind is right.

    uv run python scripts/map_detect_eval.py run --dir ../docs/evidence/map-detect-001 \\
        --model google/gemini-3.8-flash --model qwen/qwen3-vl-235b-a22b-instruct
    uv run python scripts/map_detect_eval.py score --dir ../docs/evidence/map-detect-001

Needs WORLDSIM_PROVIDER__OPENROUTER_API_KEY (read from the environment,
never printed). Each run is saved as runs/<model>.json, raw answer included.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
#: Output cap per answer (thinking included) unless --max-tokens says otherwise.
DEFAULT_MAX_TOKENS = 8000

PROMPT = """This is a fantasy world map. List every place a traveller could go to or through:
- settlements: city, town, village, port, camp, tribe
- sites: castle, fort, checkpoint, gate, tower, lighthouse, temple, monastery, chapel, inn,
  market, smithy, mill, farm, ruin, dungeon, cave, mine, bridge, landmark
- areas: forest, mountains, hills, swamp, lake, river, road, path, sea, island

For each place give:
- "name": the label written on the map for it, if there is one; otherwise a short description
- "kind": one word from the lists above
- "point": [x, y], the centre of the place's drawing (not of its label), as integers from 0 to
  1000 across the image's width (x) and height (y); [0, 0] is the top-left corner

Answer with JSON only: {"places": [{"name": "...", "kind": "...", "point": [x, y]}]}"""

#: Kinds that count as the same answer.
KIND_GROUPS = [
    {"city", "town", "castle", "fort", "capital"},
    {"village", "hamlet", "settlement", "town"},
    {"port", "harbour", "harbor", "town", "city", "village", "dock"},
    {"checkpoint", "gate", "fort", "tollgate", "toll"},
    {"camp", "tribe", "encampment", "settlement"},
    {"ruin", "ruins", "dungeon", "fort", "castle", "tower"},
    {"cave", "mine", "dungeon", "island"},
    {"tower", "watchtower", "lighthouse", "fort"},
    {"temple", "monastery", "chapel", "church", "ruin"},
    {"inn", "tavern", "building"},
    {"forest", "wood", "woods", "jungle"},
    {"mountains", "mountain", "hills", "range"},
    {"swamp", "marsh", "bog", "wetland"},
    {"river", "stream"},
    {"road", "path", "track", "trail"},
    {"landmark", "cairn", "monument"},
    {"market", "square"},
    {"smithy", "forge", "blacksmith"},
    {"mill", "watermill"},
    {"farm", "farmstead"},
    {"bridge"},
]
POINT_RADIUS = 6.0  # percent of map width
AREA_RADIUS = 15.0


def _key() -> str:
    key = os.environ.get("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.exit("set WORLDSIM_PROVIDER__OPENROUTER_API_KEY")
    return key


def _image_url(path: Path) -> str:
    with Image.open(path) as image:
        out = io.BytesIO()
        image.convert("RGB").save(out, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def _parse(text: str) -> list[dict[str, Any]]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start : end + 1])
    places = []
    for raw in data.get("places", []):
        point = raw.get("point") or []
        if len(point) == 2 and all(isinstance(v, (int, float)) for v in point):
            places.append(
                {
                    "name": str(raw.get("name", "")),
                    "kind": str(raw.get("kind", "")).lower(),
                    "x": float(point[0]) / 10,
                    "y": float(point[1]) / 10,
                }
            )
    return places


def run(
    directory: Path, models: list[str], reasoning: str | None = None, max_tokens: int = 0
) -> None:
    truth = json.loads((directory / "truth.json").read_text(encoding="utf-8"))
    runs = directory / "runs"
    runs.mkdir(exist_ok=True)
    key = _key()
    for model in models:
        target = runs / f"{model.replace('/', '__')}.json"
        if target.exists():
            print(f"{model}: {target.name} exists, not overwritten")
            continue
        results: dict[str, Any] = {
            "model": model,
            "reasoning": reasoning,
            "prompt": PROMPT,
            "maps": {},
        }
        total = 0.0
        for name in truth["maps"]:
            body = {
                "model": model,
                "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
                "temperature": 0,
                "usage": {"include": True},
                **({"reasoning": {"effort": reasoning}} if reasoning else {}),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": _image_url(directory / "maps" / f"{name}.png")
                                },
                            },
                            {"type": "text", "text": PROMPT},
                        ],
                    }
                ],
            }
            started = time.monotonic()
            reply = httpx.post(
                OPENROUTER, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=300
            )
            seconds = round(time.monotonic() - started, 1)
            payload = reply.json()
            text = ""
            places: list[dict[str, Any]] = []
            error = None
            try:
                text = payload["choices"][0]["message"]["content"] or ""
                places = _parse(text)
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                error = f"{type(exc).__name__}: {exc}; {str(payload)[:300]}"
            cost = float((payload.get("usage") or {}).get("cost") or 0)
            total += cost
            results["maps"][name] = {
                "seconds": seconds,
                "cost_usd": cost,
                "usage": payload.get("usage"),
                "raw": text,
                "places": places,
                "error": error,
            }
            print(
                f"{model} {name}: {len(places)} places, {seconds}s, ${cost:.4f}"
                + (f" ERROR {error}" if error else "")
            )
        results["cost_usd"] = round(total, 4)
        target.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{model}: ${total:.4f} -> {target.name}")


def _distance(a: dict[str, Any], b: dict[str, Any], aspect: float) -> float:
    """Percent of map width between two points (y scaled by the map's shape)."""
    return math.hypot(a["x"] - b["x"], (a["y"] - b["y"]) * aspect)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower().replace("the ", ""))


def _same_kind(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or any(a in group and b in group for group in KIND_GROUPS)


def score_map(
    spec: dict[str, Any], predicted: list[dict[str, Any]], aspect: float
) -> dict[str, Any]:
    truth = spec["places"]
    radius = [AREA_RADIUS if t.get("area") else POINT_RADIUS for t in truth]
    pairs: dict[int, int] = {}  # truth index -> prediction index
    used: set[int] = set()
    # 1. On labelled maps, the label names the place: pair by name first.
    if spec["labelled"]:
        for ti, t in enumerate(truth):
            for pi, p in enumerate(predicted):
                if pi not in used and _norm(t["name"]) and _norm(t["name"]) in _norm(p["name"]):
                    pairs[ti] = pi
                    used.add(pi)
                    break
    # 2. Then the nearest unused prediction within reach.
    candidates = sorted(
        (_distance(t, p, aspect), ti, pi)
        for ti, t in enumerate(truth)
        for pi, p in enumerate(predicted)
    )
    for dist, ti, pi in candidates:
        if ti in pairs or pi in used or dist > radius[ti]:
            continue
        pairs[ti] = pi
        used.add(pi)
    found, errors, kinds, named = 0, [], 0, 0
    rows = []
    for ti, t in enumerate(truth):
        pi = pairs.get(ti)
        if pi is None:
            rows.append({"truth": t["name"], "found": False})
            continue
        p = predicted[pi]
        dist = _distance(t, p, aspect)
        hit = dist <= radius[ti]
        found += hit
        if hit:
            errors.append(dist)
            kinds += _same_kind(t["kind"], p["kind"])
        if spec["labelled"]:
            named += _norm(t["name"]) in _norm(p["name"])
        rows.append(
            {
                "truth": t["name"],
                "found": hit,
                "as": p["name"],
                "kind": p["kind"],
                "off": round(dist, 1),
            }
        )
    extras = spec.get("extras", [])
    invented = []
    for pi, p in enumerate(predicted):
        if pi in used:
            continue
        near_truth = any(_distance(t, p, aspect) <= r for t, r in zip(truth, radius, strict=True))
        near_extra = any(
            _distance(e, p, aspect) <= (AREA_RADIUS if e.get("area") else POINT_RADIUS)
            for e in extras
        )
        if not near_truth and not near_extra:
            invented.append(p["name"])
    return {
        "found": found,
        "total": len(truth),
        "named": named if spec["labelled"] else None,
        "kind_right": kinds,
        "median_off": round(sorted(errors)[len(errors) // 2], 1) if errors else None,
        "invented": invented,
        "predicted": len(predicted),
        "rows": rows,
        "pairs": pairs,
    }


def _font(size: int) -> Any:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def overlay(
    directory: Path,
    name: str,
    spec: dict[str, Any],
    predicted: list[dict[str, Any]],
    scored: dict[str, Any],
    out: Path,
) -> None:
    """Green rings: truth. Dots: the model's pins; a line joins each pair."""
    with Image.open(directory / "maps" / f"{name}.png") as source:
        image = source.convert("RGB")
    W, H = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    font = _font(15)
    at = lambda p: (p["x"] / 100 * W, p["y"] / 100 * H)  # noqa: E731
    for ti, t in enumerate(spec["places"]):
        x, y = at(t)
        r = (AREA_RADIUS if t.get("area") else POINT_RADIUS) / 100 * W
        draw.ellipse([x - r, y - r, x + r, y + r], outline=(40, 220, 90, 230), width=3)
        pi = scored["pairs"].get(ti)
        if pi is not None:
            draw.line([at(t), at(predicted[pi])], fill=(255, 255, 255, 220), width=3)
    for pi, p in enumerate(predicted):
        x, y = at(p)
        matched = pi in scored["pairs"].values()
        color = (40, 140, 255, 255) if matched else (240, 50, 60, 255)
        draw.ellipse([x - 8, y - 8, x + 8, y + 8], fill=color, outline=(0, 0, 0, 255), width=2)
        draw.text(
            (x + 10, y - 9),
            p["name"][:28],
            fill=(255, 255, 255),
            font=font,
            stroke_width=3,
            stroke_fill=(0, 0, 0),
        )
    image.save(out, format="JPEG", quality=85)


def score(directory: Path) -> None:
    truth = json.loads((directory / "truth.json").read_text(encoding="utf-8"))
    overlays = directory / "overlays"
    overlays.mkdir(exist_ok=True)
    summary: dict[str, Any] = {}
    for run_file in sorted((directory / "runs").glob("*.json")):
        results = json.loads(run_file.read_text(encoding="utf-8"))
        model = results["model"]
        per_map = {}
        for name, spec in truth["maps"].items():
            with Image.open(directory / "maps" / f"{name}.png") as image:
                aspect = image.height / image.width
            predicted = results["maps"].get(name, {}).get("places", [])
            scored = score_map(spec, predicted, aspect)
            overlay(
                directory, name, spec, predicted, scored, overlays / f"{name}__{run_file.stem}.jpg"
            )
            scored.pop("pairs")
            per_map[name] = scored
        summary[model] = {"cost_usd": results.get("cost_usd"), "maps": per_map}
        found = sum(m["found"] for m in per_map.values())
        total = sum(m["total"] for m in per_map.values())
        invented = sum(len(m["invented"]) for m in per_map.values())
        print(
            f"\n{model}  (${results.get('cost_usd')})  found {found}/{total}, invented {invented}"
        )
        for name, m in per_map.items():
            label = "labelled" if truth["maps"][name]["labelled"] else "unlabelled"
            invented = m["invented"]
            print(
                f"  {name} {label:10} found {m['found']}/{m['total']}  kind {m['kind_right']}"
                f"  median off {m['median_off']}%  invented {len(invented)} {invented[:4]}"
            )
    (directory / "scores.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["run", "score"])
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--reasoning", choices=["minimal", "low", "medium", "high"])
    parser.add_argument("--max-tokens", type=int, default=0)
    args = parser.parse_args()
    if args.command == "run":
        run(args.dir, args.model, args.reasoning, args.max_tokens)
    else:
        score(args.dir)


if __name__ == "__main__":
    main()
