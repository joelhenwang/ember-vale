"""Can a vision model trace which places on a painted map connect?

Given a map and its places (name, kind, where drawn), each model lists
the direct connections it sees drawn (road, path, sea route, bridge,
pass) with points along each route. Scored against hand-traced ground
truth (docs/evidence/map-routes-NNN/truth.json): clear connections
found, wrong ones claimed; faint ones count either way.

    uv run python scripts/map_routes_eval.py run --dir ../docs/evidence/map-routes-001 \\
        --model google/gemini-3.8-flash
    uv run python scripts/map_routes_eval.py score --dir ../docs/evidence/map-routes-001

Needs WORLDSIM_PROVIDER__OPENROUTER_API_KEY in the environment (never printed).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
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
DEFAULT_MAX_TOKENS = 40000

PROMPT = """These are the places on this fantasy map, with where each is drawn
([x, y] from 0 to 1000 across the image's width and height; [0, 0] is the top-left corner):
{places}

List every direct connection a traveller could use between two of these places, as drawn on
the map: roads, paths and tracks, bridges, sea or river routes drawn as lines, mountain passes.
"Direct" means the route goes from one place to the other without passing through a third
listed place; if it does, list the two shorter legs instead. Only include connections you can
see drawn; leave a place unconnected if no drawn route reaches it.

For each connection give:
- "from" and "to": the place numbers
- "by": one of road, path, sea, river, bridge, pass
- "points": 3 to 8 [x, y] points along the drawn route, from the first place to the second

Answer with JSON only:
{{"connections": [{{"from": 1, "to": 2, "by": "road", "points": [[x, y], [x, y], [x, y]]}}]}}"""


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


def _place_list(places: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{n}. {p['name']} ({p['kind']}) at [{round(p['x'] * 10)}, {round(p['y'] * 10)}]"
        for n, p in enumerate(places, start=1)
    )


def _parse(text: str, places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    data = json.loads(text[text.find("{") : text.rfind("}") + 1])
    found = []
    for raw in data.get("connections", []):
        try:
            a, b = int(raw["from"]), int(raw["to"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (1 <= a <= len(places) and 1 <= b <= len(places)) or a == b:
            continue
        points = [
            [float(p[0]) / 10, float(p[1]) / 10]
            for p in raw.get("points") or []
            if isinstance(p, list) and len(p) == 2
        ]
        found.append(
            {
                "a": places[a - 1]["name"],
                "b": places[b - 1]["name"],
                "by": str(raw.get("by", "")),
                "points": points,
            }
        )
    return found


def run(
    directory: Path, models: list[str], reasoning: str | None = None, max_tokens: int = 0
) -> None:
    truth = json.loads((directory / "truth.json").read_text(encoding="utf-8"))
    maps_dir = (directory / truth["maps_dir"]).resolve()
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
        for name, spec in truth["maps"].items():
            prompt = PROMPT.format(places=_place_list(spec["places"]))
            image = {
                "type": "image_url",
                "image_url": {"url": _image_url(maps_dir / f"{name}.png")},
            }
            body = {
                "model": model,
                "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
                "temperature": 0,
                "usage": {"include": True},
                **({"reasoning": {"effort": reasoning}} if reasoning else {}),
                "messages": [
                    {"role": "user", "content": [image, {"type": "text", "text": prompt}]}
                ],
            }
            started = time.monotonic()
            reply = httpx.post(
                OPENROUTER, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=400
            )
            seconds = round(time.monotonic() - started, 1)
            payload = reply.json()
            text, found, error = "", [], None
            try:
                text = payload["choices"][0]["message"]["content"] or ""
                found = _parse(text, spec["places"])
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                error = f"{type(exc).__name__}: {exc}; {str(payload)[:300]}"
            cost = float((payload.get("usage") or {}).get("cost") or 0)
            total += cost
            results["maps"][name] = {
                "seconds": seconds,
                "cost_usd": cost,
                "raw": text,
                "connections": found,
                "error": error,
            }
            note = f" ERROR {error}" if error else ""
            print(f"{model} {name}: {len(found)} connections, {seconds}s, ${cost:.4f}{note}")
        results["cost_usd"] = round(total, 4)
        target.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{model}: ${total:.4f} -> {target.name}")


def _pair(a: str, b: str) -> frozenset[str]:
    return frozenset((a, b))


def _groups(entries: list[str]) -> list[set[frozenset[str]]]:
    return [{_pair(*pair.split("|")) for pair in entry.split(" / ")} for entry in entries]


def score_map(spec: dict[str, Any], found: list[dict[str, Any]]) -> dict[str, Any]:
    required = _groups(spec["edges"]["required"])
    optional = {pair for group in _groups(spec["edges"]["optional"]) for pair in group}
    predicted = {_pair(c["a"], c["b"]) for c in found}
    met = [bool(group & predicted) for group in required]
    in_required = {pair for group in required for pair in group}
    wrong = sorted(" - ".join(sorted(pair)) for pair in predicted - in_required - optional)
    right = len(predicted & in_required)
    judged = right + len(wrong)
    return {
        "found": sum(met),
        "required": len(required),
        "missed": [spec["edges"]["required"][i] for i, ok in enumerate(met) if not ok],
        "wrong": wrong,
        "precision": round(right / judged, 2) if judged else None,
        "claimed": len(predicted),
    }


def _font(size: int) -> Any:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def overlay(
    maps_dir: Path, name: str, spec: dict[str, Any], found: list[dict[str, Any]], out: Path
) -> None:
    """Routes as the model traced them: blue right, grey faint (optional), red wrong."""
    with Image.open(maps_dir / f"{name}.png") as source:
        image = source.convert("RGB")
    W, H = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    places = {p["name"]: p for p in spec["places"]}
    required = {pair for group in _groups(spec["edges"]["required"]) for pair in group}
    optional = {pair for group in _groups(spec["edges"]["optional"]) for pair in group}
    for c in found:
        pair = _pair(c["a"], c["b"])
        color = (
            (30, 130, 255, 235)
            if pair in required
            else (150, 150, 150, 200)
            if pair in optional
            else (240, 45, 55, 235)
        )
        ends = [
            [places[c["a"]]["x"], places[c["a"]]["y"]],
            [places[c["b"]]["x"], places[c["b"]]["y"]],
        ]
        line = [ends[0], *c["points"], ends[1]] if c["points"] else ends
        draw.line([(x / 100 * W, y / 100 * H) for x, y in line], fill=color, width=6, joint="curve")
    font = _font(15)
    for p in spec["places"]:
        x, y = p["x"] / 100 * W, p["y"] / 100 * H
        draw.ellipse(
            [x - 9, y - 9, x + 9, y + 9], fill=(255, 220, 60, 255), outline=(0, 0, 0, 255), width=2
        )
        draw.text(
            (x + 11, y - 9),
            p["name"],
            fill=(255, 255, 255),
            font=font,
            stroke_width=3,
            stroke_fill=(0, 0, 0),
        )
    image.save(out, format="JPEG", quality=85)


def score(directory: Path) -> None:
    truth = json.loads((directory / "truth.json").read_text(encoding="utf-8"))
    maps_dir = (directory / truth["maps_dir"]).resolve()
    overlays = directory / "overlays"
    overlays.mkdir(exist_ok=True)
    summary: dict[str, Any] = {}
    for run_file in sorted((directory / "runs").glob("*.json")):
        results = json.loads(run_file.read_text(encoding="utf-8"))
        per_map = {}
        for name, spec in truth["maps"].items():
            found = results["maps"].get(name, {}).get("connections", [])
            per_map[name] = score_map(spec, found)
            overlay(maps_dir, name, spec, found, overlays / f"{name}__{run_file.stem}.jpg")
        summary[results["model"]] = {"cost_usd": results.get("cost_usd"), "maps": per_map}
        got = sum(m["found"] for m in per_map.values())
        need = sum(m["required"] for m in per_map.values())
        wrong = sum(len(m["wrong"]) for m in per_map.values())
        print(
            f"\n{results['model']}  (${results.get('cost_usd')})  found {got}/{need}, wrong {wrong}"
        )
        for name, m in per_map.items():
            print(
                f"  {name} found {m['found']}/{m['required']}  claimed {m['claimed']}"
                f"  wrong {len(m['wrong'])} {m['wrong'][:3]}  missed {m['missed']}"
            )
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    (directory / "scores.json").write_text(text, encoding="utf-8")


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
