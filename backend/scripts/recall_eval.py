"""Recall eval: replay real decisions whose observation budget overflowed.

For each sampled decision it compares what recency kept with what
relevance would keep under the same budget, against a focus built the
way the orchestrator builds it (the character and their latest lines).
Prints the similarity spread (to set RELEVANCE_LOW/HIGH), how much the
kept set changes, and a few swaps to read by eye.

    uv run python scripts/recall_eval.py --url http://localhost:8102 --samples 40

Needs WORLDSIM_DATABASE__URL (dev database) and the local model service.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import statistics

import httpx
from sqlalchemy import text

from worldsim.domain.memory import DEFAULT_RELEVANCE_WEIGHT, relevance
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.settings import Settings

CUT_DECISIONS = """
SELECT cm.id, cm.sources
FROM context_manifest cm
WHERE cm.role = 'character_decision'
  AND EXISTS (SELECT 1 FROM jsonb_array_elements(cm.sources) s
              WHERE s->>'reason' = 'section budget exhausted' AND s->>'kind' = 'observations')
"""


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def _mean_sim(sims: dict[str, float], kept: set[str]) -> float:
    return statistics.mean(sims.get(i, 0.0) for i in kept) if kept else 0.0


async def main(url: str, samples: int, seed: int) -> None:
    engine = create_engine(Settings())
    rng = random.Random(seed)
    spread: list[float] = []
    changed: list[float] = []
    gains: list[float] = []
    shown = 0
    async with engine.connect() as conn, httpx.AsyncClient(timeout=30) as http:
        health = (await http.get(f"{url}/health")).json()
        model = health["embed"]["model"]
        rows = (await conn.execute(text(CUT_DECISIONS))).all()
        rng.shuffle(rows)
        for row in rows[:samples]:
            obs = [s for s in row.sources if s["kind"] == "observations"]
            owner = next((s.get("owner_id") for s in obs if s.get("owner_id")), None)
            if owner is None:
                continue
            ids = [s["source_id"] for s in obs]
            found = (
                await conn.execute(
                    text(
                        "SELECT source_id, created_phase_index, text FROM recall_vector "
                        "WHERE model = :m AND source_id = ANY(:ids)"
                    ),
                    {"m": model, "ids": ids},
                )
            ).all()
            lines = {f.source_id: (f.created_phase_index, f.text) for f in found}
            if len(lines) < len(ids) * 0.9:
                continue  # not indexed yet
            latest = sorted(lines.items(), key=lambda kv: kv[1][0])[-3:]
            name = (
                await conn.execute(text("SELECT name FROM character WHERE id = :id"), {"id": owner})
            ).scalar_one()
            focus = f"{name}. " + " ".join(t for _sid, (_p, t) in latest)
            query = (
                await http.post(f"{url}/embed", json={"texts": [focus], "kind": "query"})
            ).json()["vectors"][0]
            sims = {
                r.source_id: float(r.similarity)
                for r in (
                    await conn.execute(
                        text(
                            "SELECT source_id, 1 - (embedding <=> CAST(:q AS vector)) "
                            "AS similarity FROM recall_vector "
                            "WHERE model = :m AND source_id = ANY(:ids)"
                        ),
                        {"q": _vector(query), "m": model, "ids": ids},
                    )
                ).all()
            }
            sims = {k: v for k, v in sims.items() if math.isfinite(v)}
            spread.extend(sims.values())
            kept_before = {s["source_id"] for s in obs if s["reason"] == "permitted"}
            budget = len(kept_before)
            rescored = sorted(
                obs,
                key=lambda s: (
                    -(
                        float(s["score"])
                        + DEFAULT_RELEVANCE_WEIGHT * relevance(sims.get(s["source_id"], 0.0))
                    )
                ),
            )
            kept_after = {s["source_id"] for s in rescored[:budget]}
            changed.append(len(kept_after - kept_before) / max(1, budget))

            gains.append(_mean_sim(sims, kept_after) - _mean_sim(sims, kept_before))
            if shown < 4 and kept_after != kept_before:
                shown += 1
                print(f"\n=== {name}: kept {budget} of {len(obs)} ===")
                print(f"focus: {focus[:220]}")
                for sid in list(kept_after - kept_before)[:3]:
                    print(f"  + {sims.get(sid, 0):.2f} {lines[sid][1][:110]}")
                for sid in list(kept_before - kept_after)[:3]:
                    print(f"  - {sims.get(sid, 0):.2f} {lines[sid][1][:110]}")
    await engine.dispose()
    if not spread:
        print("nothing to evaluate (index still filling?)")
        return
    q = statistics.quantiles(spread, n=20)
    print(f"\ndecisions evaluated: {len(changed)}")
    print(
        f"similarity to focus: p10 {q[1]:.2f}  p50 {q[9]:.2f}  p90 {q[17]:.2f}  "
        f"max {max(spread):.2f}"
    )
    print(f"share of the kept set that changes: mean {statistics.mean(changed):.0%}")
    print(f"mean similarity of the kept set: +{statistics.mean(gains):.3f} with relevance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="http://localhost:8102")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    asyncio.run(main(args.url, args.samples, args.seed))
