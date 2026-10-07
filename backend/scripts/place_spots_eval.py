"""Read the spots on place pictures with one or more spot prompts.

    uv run python scripts/place_spots_eval.py --live --out runs/run-1 \\
        --prompt-file old=spots-v1.txt village.png tidemark.jpg

Without --prompt-file the shipped SPOTS_PROMPT runs as "current". Needs
WORLDSIM_PROVIDER__OPENROUTER_API_KEY; the places model is GPT-6 Luna.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from worldsim.infrastructure.geography.openrouter import (
    SPOTS_PROMPT,
    OpenRouterMapReader,
    parse_places,
)

MODEL = "openai/gpt-6-luna"
POSITION_WORDS = (
    "left",
    "right",
    "upper",
    "lower",
    "foreground",
    "background",
    "center",
    "centre",
    "corner",
    "near the",
    "bottom",
    "top",
)


async def read(reader: OpenRouterMapReader, picture: bytes, prompt: str) -> dict[str, object]:
    text, seconds, cost = await reader._ask(MODEL, picture, prompt)  # pyright: ignore[reportPrivateUsage]
    spots = parse_places(text)
    names = [s.name for s in spots]
    return {
        "seconds": seconds,
        "cost_usd": cost,
        "count": len(spots),
        "positional_names": sum(any(w in n.lower() for w in POSITION_WORDS) for n in names),
        "houses": sum(1 for s in spots if s.kind == "house"),
        "spots": [{"name": s.name, "kind": s.kind, "point": list(s.point)} for s in spots],
    }


async def run(prompts: dict[str, str], pictures: list[Path]) -> dict[str, dict[str, object]]:
    reader = OpenRouterMapReader(
        os.environ["WORLDSIM_PROVIDER__OPENROUTER_API_KEY"],
        "https://openrouter.ai/api/v1",
        MODEL,
        "unused",
    )
    jobs = {
        (label, path.stem): read(reader, path.read_bytes(), prompt)
        for label, prompt in prompts.items()
        for path in pictures
    }
    results = await asyncio.gather(*jobs.values())
    out: dict[str, dict[str, object]] = {}
    for (label, stem), result in zip(jobs, results, strict=True):
        out.setdefault(label, {})[stem] = result
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="required: this spends money")
    parser.add_argument("--out", required=True)
    parser.add_argument("--prompt-file", action="append", default=[], help="label=path")
    parser.add_argument("pictures", nargs="+")
    args = parser.parse_args()
    if not args.live:
        sys.exit("refusing to call a paid model without --live")
    prompts = {"current": SPOTS_PROMPT}
    for item in args.prompt_file:
        label, _, path = item.partition("=")
        prompts[label] = Path(path).read_text(encoding="utf-8")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)  # evidence is never overwritten
    results = asyncio.run(run(prompts, [Path(p) for p in args.pictures]))
    for label, by_picture in results.items():
        (out / f"{label}.json").write_text(
            json.dumps(by_picture, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        for stem, r in by_picture.items():
            print(
                f"{label:8} {stem:10} {r['count']:>3} spots, {r['houses']:>2} houses, "
                f"{r['positional_names']:>2} positional names, ${r['cost_usd']:.4f}"
            )


if __name__ == "__main__":
    main()
