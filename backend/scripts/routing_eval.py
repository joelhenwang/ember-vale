"""Latency by OpenRouter routing: replay stored decision prompts under each sort.

Takes recent real character-decision prompts from the dev database and
sends each one under every routing choice in turn (interleaved, so time
of day hits all alike), with no hedging or retries, then prints latency
percentiles and how often each choice was slowest. Costs real money
(about $0.0006 a call with DeepSeek V4 Flash); needs ``--live``.

    uv run python scripts/routing_eval.py --live --prompts 20 --sorts throughput,latency,none
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load_env() -> None:
    for raw in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip().replace("\r", "")
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key.startswith("WORLDSIM_PROVIDER__") or key == "WORLDSIM_DATABASE__URL":
                os.environ[key] = value.replace("@db:5432", "@localhost:5433")


async def main(count: int, sorts: list[str]) -> None:
    from sqlalchemy import text

    from worldsim.application.graphs.character import load_character_prompt, render_system_prompt
    from worldsim.application.ports.model_gateway import CompletionRequest, ModelGatewayError
    from worldsim.infrastructure.db.engine import create_engine
    from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
    from worldsim.infrastructure.model_gateway.selection import gateways_for_settings
    from worldsim.infrastructure.settings import Settings

    settings = Settings()
    engine = create_engine(settings)
    async with engine.connect() as conn:
        prompts = [
            str(row[0])
            for row in await conn.execute(
                text(
                    "SELECT request->>'prompt' FROM model_call WHERE role = 'character_decision' "
                    "AND status = 'succeeded' ORDER BY created_at DESC LIMIT :n"
                ),
                {"n": count},
            )
        ]
    await engine.dispose()
    system = render_system_prompt(load_character_prompt())
    gateways, _profiles = gateways_for_settings(settings)
    base = gateways["character"]
    while not isinstance(base, OpenRouterGateway):  # unwrap hedge/retry/trace layers
        inner = getattr(base, "_inner", None) or getattr(base, "_gateway", None)
        if inner is None:
            raise SystemExit(f"cannot find the OpenRouter adapter inside {type(base).__name__}")
        base = inner
    times: dict[str, list[float]] = {s: [] for s in sorts}
    slowest: dict[str, int] = dict.fromkeys(sorts, 0)
    for number, prompt in enumerate(prompts, 1):
        row: dict[str, float] = {}
        for sort in sorts:
            base.sort = None if sort == "none" else sort
            started = time.perf_counter()
            try:
                await base.complete(
                    CompletionRequest(prompt=prompt, system=system, max_tokens=400, json_mode=True)
                )
            except ModelGatewayError as exc:
                print(f"  {sort}: failed ({type(exc).__name__})")
                continue
            row[sort] = time.perf_counter() - started
            times[sort].append(row[sort])
        if row:
            slowest[max(row, key=lambda k: row[k])] += 1
        print(f"{number:2d} " + "  ".join(f"{s} {row.get(s, float('nan')):5.1f}s" for s in sorts))
    print()
    for sort in sorts:
        got = sorted(times[sort])
        if not got:
            continue
        p90 = got[min(len(got) - 1, int(len(got) * 0.9))]
        print(
            f"{sort:10s} n={len(got):2d}  p50 {statistics.median(got):4.1f}s  p90 {p90:4.1f}s  "
            f"max {got[-1]:4.1f}s  slowest {slowest[sort]}x"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--live", action="store_true", help="required: spends real credit")
    parser.add_argument("--prompts", type=int, default=20)
    parser.add_argument("--sorts", default="throughput,latency,none")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("pass --live to spend real credit")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    load_env()
    asyncio.run(main(args.prompts, args.sorts.split(",")))
