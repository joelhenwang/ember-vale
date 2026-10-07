"""Replay recorded narrator requests under different narrator system prompts.

Each fixture entry is a narrator user prompt as the app sent it (from
model_call). Every prompt version renders its system prompt the way the
app does and asks the live model, so versions differ only in the system
prompt. Scores per answer: does it parse and pass the app's own beat
validator, does it name a listed spot (when the prompt lists spots), how
much stock wording it repeats from the fact records, and its length.

    uv run python scripts/narrator_prompt_eval.py --live \\
        --fixture ../docs/evidence/narrator-v4-001/fixture.json \\
        --versions narrator.v3,narrator.v4 --out ../docs/evidence/narrator-v4-001/runs/run-1

Needs WORLDSIM_PROVIDER__VENICE_API_KEY (and _BASE_URL, _MODEL) for
--provider venice, or WORLDSIM_PROVIDER__OPENROUTER_* for openrouter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import SecretStr, TypeAdapter, ValidationError

from worldsim.application.graphs.narrate import (
    beats_valid,
    drop_recap_only,
    render_system_prompt,
    repair_instruction,
    schema_denial,
    soften_dialogue,
)
from worldsim.application.ports.model_gateway import CompletionRequest, unfence_json
from worldsim.domain.geography import spot_named
from worldsim.domain.narration import BeatProposal
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.profiles import (
    OPENROUTER_CHAT_PROFILE,
    VENICE_CHAT_PROFILE,
)
from worldsim.infrastructure.model_gateway.venice import VeniceGateway

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
#: Fact-record wording a reader should never see verbatim.
STOCK = (
    "attempts to communicate",
    "attempt to communicate",
    "speaks to",
    "brings up",
    "bringing up",
    "the topic",
    "decides to",
    "perhaps",
    "the scene",
    "attempts to",
)
MAX_TOKENS = 1536
_BEATS = TypeAdapter(list[BeatProposal])


def facts_of(prompt: str) -> dict[str, str]:
    """Visible fact key -> its line, from the rendered user prompt."""
    return {m.group(1): m.group(2) for m in re.finditer(r'^- key "([^"]+)": (.*)$', prompt, re.M)}


def audience_of(prompt: str) -> frozenset[str]:
    m = re.search(r"^Audience: (.*)$", prompt, re.M)
    return frozenset(p.strip() for p in m.group(1).split(",")) if m else frozenset()


def budget_of(prompt: str) -> int:
    m = re.search(r"^Beat budget: (\d+)", prompt, re.M)
    return int(m.group(1)) if m else 8


def spots_of(prompt: str) -> list[tuple[str, str]]:
    m = re.search(r"Spots in this place: (.*?)\. (?:If|Set) the scene", prompt)
    if not m:
        return []
    names = [re.sub(r"\s*\([^)]*\)$", "", part.strip()) for part in m.group(1).split(";")]
    return [(name, name) for name in names if name]


def check(prompt: str, raw: str, finish: str | None) -> tuple[list[BeatProposal], str | None]:
    """The app's own acceptance: parse, drop recap-only beats, soften
    ineligible dialogue, then the beat validator (narrate.py decide)."""
    try:
        proposals = _BEATS.validate_json(unfence_json(raw))
    except ValidationError as exc:
        return [], schema_denial(exc.error_count(), finish)
    facts = facts_of(prompt)
    speech = frozenset(k for k, line in facts.items() if "dialogue-eligible" in line)
    speakers: dict[str, str] = {}
    names: dict[str, str] = {}
    utterances: dict[str, str] = {}
    for key, line in facts.items():
        if m := re.search(r"\(speaker ([^,]+), id: ([0-9a-f-]+)\)", line):
            names[key], speakers[key] = m.group(1), m.group(2)
        if key in speech and (q := re.search(r'"(.*)"', line)):
            utterances[key] = q.group(1)
    proposals = soften_dialogue(drop_recap_only(proposals), speech, utterances, names)
    denial = beats_valid(
        proposals,
        visible_keys=frozenset(facts),
        audience_ids=audience_of(prompt),
        beats_budget=budget_of(prompt),
        fact_speakers=speakers,
        speech_keys=speech,
        fact_utterances=utterances,
    )
    return proposals, denial


def score(prompt: str, proposals: list[BeatProposal], denial: str | None) -> dict[str, Any]:
    text = " ".join(p.text for p in proposals)
    lowered = text.lower()
    spots = spots_of(prompt)
    return {
        "valid": denial is None,
        "denial": denial,
        "text": text,
        "beats": len(proposals),
        "words": len(text.split()),
        "stock": sum(lowered.count(s) for s in STOCK),
        "spot": spot_named(text, spots) if spots else None,
        "has_spots": bool(spots),
    }


async def run(
    args: argparse.Namespace, fixture: list[dict[str, Any]], systems: dict[str, str]
) -> dict[str, list[dict[str, Any]]]:
    venice = args.provider == "venice"
    prefix = "WORLDSIM_PROVIDER__VENICE" if venice else "WORLDSIM_PROVIDER__OPENROUTER"
    base = (VENICE_CHAT_PROFILE if venice else OPENROUTER_CHAT_PROFILE).model_copy(
        update={"model_id": args.model or os.environ[f"{prefix}_MODEL"]}
    )
    adapter = VeniceGateway if venice else OpenRouterGateway
    gateway = adapter(
        base,
        api_key=SecretStr(os.environ[f"{prefix}_API_KEY"]),
        base_url=os.environ[f"{prefix}_BASE_URL"],
        reasoning=args.reasoning,
        timeout_s=180.0,
    )
    results: dict[str, list[dict[str, Any]]] = {}
    gate = asyncio.Semaphore(args.parallel)
    for version, system in systems.items():

        async def one(i: int, entry: dict[str, Any], system: str = system) -> dict[str, Any]:
            async with gate:
                prompt = entry["prompt"]
                tokens = [0, 0]
                raws: list[str] = []
                denials: list[str] = []
                proposals: list[BeatProposal] = []
                denial: str | None = None
                # The first answer and, like the app, one repair.
                for attempt in range(2):
                    repair = "" if attempt == 0 else repair_instruction(denials[-1])
                    asked = f"{prompt}\n\n{repair}" if repair else prompt
                    try:
                        result = await gateway.complete(
                            CompletionRequest(prompt=asked, system=system, max_tokens=MAX_TOKENS)
                        )
                    except Exception as exc:
                        return {"i": i, "error": f"{type(exc).__name__}: {exc}"[:300]}
                    tokens[0] += result.prompt_tokens
                    tokens[1] += result.completion_tokens
                    raws.append(result.text)
                    proposals, denial = check(prompt, result.text, result.finish_reason)
                    if denial is None:
                        break
                    denials.append(denial)
                return {
                    "i": i,
                    "prompt_tokens": tokens[0],
                    "completion_tokens": tokens[1],
                    "repaired": len(raws) > 1 and denial is None,
                    "first_denial": denials[0] if denials else None,
                    "raw": raws,
                    **score(prompt, proposals, denial),
                }

        rows = await asyncio.gather(*(one(i, e) for i, e in enumerate(fixture)))
        results[version] = [{"model": base.model_id, **row} for row in rows]
        ok = [r for r in rows if "error" not in r]
        valid = [r for r in ok if r.get("valid")]
        with_spots = [r for r in valid if r.get("has_spots")]
        print(
            f"{version}: {len(valid)}/{len(rows)} valid "
            f"({sum(1 for r in valid if r.get('repaired'))} after repair), "
            f"spot named {sum(1 for r in with_spots if r.get('spot'))}/{len(with_spots)}, "
            f"stock phrases {sum(r.get('stock', 0) for r in valid)}, "
            f"words/answer {sum(r.get('words', 0) for r in valid) / max(1, len(valid)):.0f}, "
            f"tokens in/out {sum(r.get('prompt_tokens', 0) for r in ok)}/"
            f"{sum(r.get('completion_tokens', 0) for r in ok)}"
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="required: this spends money")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--versions", default="narrator.v3,narrator.v4")
    parser.add_argument("--provider", choices=("venice", "openrouter"), default="venice")
    parser.add_argument("--model", default=None)
    parser.add_argument("--reasoning", default="off", help="as the app sends it (off)")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if not args.live:
        sys.exit("refusing to call a paid model without --live")
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    systems = {
        version: render_system_prompt((PROMPTS / f"{version}.md").read_text(encoding="utf-8"))
        for version in args.versions.split(",")
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=False)  # evidence is never overwritten
    for version, rows in asyncio.run(run(args, fixture, systems)).items():
        (out_dir / f"{version}.json").write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
