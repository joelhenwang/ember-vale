"""Offline LLM usage report from the traces already in the database.

Reads model_call / model_cost / phase_run (read-only, free) and prints:
  1. per role and model: calls, failures, tokens, cached share, latency,
     finish_reason=length, likely hedged calls, cost;
  2. cost and model latency per beat;
  3. prompt-token growth with story length (beat index buckets);
  4. image jobs: status, attempts, kinds.

    python scripts/llm_usage_report.py [--since 2026-10-01] [--json out.json]

Needs WORLDSIM_DATABASE__URL (export that single variable).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg

#: Per-role hedge waits (selection.hedge_after defaults): a call slower than
#: this probably had a twin, which is billed but not traced.
HEDGE_S = {
    "character_decision": 4,
    "reaction": 4,
    "director": 5,
    "resolver": 7,
    "narrator": 7,
    "daily_summary": 10,
}

#: The prompt versions in use now (application/graphs/*.py); --current limits
#: the report to them so old experiments do not blur today's numbers.
CURRENT = (
    "character_decision.v7",
    "reaction.v4",
    "resolver.v4",
    "narrator.v4",
    "director.v12",
    "summary.v1",
    "digest.v1",
)

ROLE_MODEL = """
select c.role, coalesce(nullif(m.model, ''), c.result->>'model', '?') as model,
       count(*) as calls,
       count(*) filter (where c.status = 'failed') as failed,
       round(avg(c.prompt_tokens)) as prompt_avg,
       percentile_cont(0.95) within group (order by c.prompt_tokens) as prompt_p95,
       round(avg(c.completion_tokens)) as completion_avg,
       -- only calls that recorded a cache figure (traces before 2026-10-06 did not)
       round(100.0 * sum((c.result->>'cached_tokens')::int)
             filter (where c.result ? 'cached_tokens')
             / nullif(sum(c.prompt_tokens) filter (where c.result ? 'cached_tokens'), 0), 1)
         as cached_pct,
       percentile_cont(0.5) within group (order by c.latency_ms) as lat_p50,
       percentile_cont(0.95) within group (order by c.latency_ms) as lat_p95,
       count(*) filter (where c.result->>'finish_reason' = 'length') as hit_cap,
       round(sum(coalesce(m.prompt_cost_usd, 0) + coalesce(m.completion_cost_usd, 0))::numeric, 4)
         as usd
from model_call c left join model_cost m on m.call_id = c.id
where c.created_at >= $1 and (c.request->>'prompt_version') = any($2::text[])
group by 1, 2 order by usd desc nulls last, calls desc
"""

HEDGED = """
select role, count(*) filter (where latency_ms > $2 * 1000) as slow, count(*) as calls
from model_call where created_at >= $1 and role = $3 and status = 'succeeded'
  and (request->>'prompt_version') = any($4::text[])
group by role
"""

PER_BEAT = """
with beat as (
  select c.phase_run_id, count(*) calls,
         sum(coalesce(m.prompt_cost_usd, 0) + coalesce(m.completion_cost_usd, 0)) usd,
         sum(c.prompt_tokens) ptok, max(c.latency_ms) slowest
  from model_call c left join model_cost m on m.call_id = c.id
  where c.created_at >= $1 and c.phase_run_id is not null
    and (c.request->>'prompt_version') = any($2::text[])
  group by 1)
select count(*) beats, round(avg(calls), 1) calls_avg,
       round(avg(usd)::numeric, 5) usd_avg,
       round((percentile_cont(0.95) within group (order by usd))::numeric, 5) usd_p95,
       round(avg(ptok)) prompt_tokens_avg,
       percentile_cont(0.5) within group (order by slowest) slowest_call_p50
from beat
"""

GROWTH = """
select c.role, (p.absolute_index / 10) * 10 as bucket, count(*) calls,
       round(avg(c.prompt_tokens)) prompt_avg, max(c.prompt_tokens) prompt_max
from model_call c join phase_run p on p.id = c.phase_run_id
where c.created_at >= $1 and (c.request->>'prompt_version') = any($2::text[])
group by 1, 2 order by 1, 2
"""

REPEATS = """
select role, count(*) filter (where n > 1) as groups_repeated, count(*) as groups,
       sum(n - 1) as extra_calls
from (select role, phase_run_id, actor_id, count(*) n from model_call
      where created_at >= $1 and phase_run_id is not null
        and (request->>'prompt_version') = any($2::text[])
      group by 1, 2, 3) g
group by role order by extra_calls desc
"""

FINISH = """
select role, coalesce(result->>'finish_reason', '?') finish, count(*) n,
       round(avg(completion_tokens)) completion_avg, max(completion_tokens) completion_max,
       (request->>'max_tokens') max_tokens
from model_call where created_at >= $1 and (request->>'prompt_version') = any($2::text[])
group by 1, 2, 6 order by 1, 3 desc
"""

IMAGES = """
select kind, status, count(*) n, round(avg(attempt_count), 2) attempts_avg,
       max(attempt_count) attempts_max
from image_job group by 1, 2 order by 1, 2
"""

IMAGE_ASSETS = """
select kind, mime, count(*) n, round(avg(width)) w_avg, round(avg(height)) h_avg
from asset_record group by 1, 2 order by n desc
"""


def table(title: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n== {title}")
    if not rows:
        print("(none)")
        return
    cols = list(rows[0])
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))


async def report() -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2000-01-01")
    parser.add_argument("--json")
    parser.add_argument(
        "--current", action="store_true", help="only the prompt versions in use now"
    )
    args = parser.parse_args()
    url = os.environ["WORLDSIM_DATABASE__URL"].replace("postgresql+asyncpg", "postgresql")
    versions = list(CURRENT) if args.current else None
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
    conn = await asyncpg.connect(url)
    all_versions = [
        r[0] for r in await conn.fetch("select distinct request->>'prompt_version' from model_call")
    ]
    vs = versions or all_versions
    try:
        out: dict[str, list[dict[str, Any]]] = {}
        out["by_role_model"] = [dict(r) for r in await conn.fetch(ROLE_MODEL, since, vs)]
        hedged = []
        for role, wait in HEDGE_S.items():
            for r in await conn.fetch(HEDGED, since, wait, role, vs):
                d = dict(r)
                d["hedge_after_s"] = wait
                d["slow_pct"] = round(100 * d["slow"] / d["calls"], 1) if d["calls"] else 0
                hedged.append(d)
        out["likely_hedged"] = hedged
        out["per_beat"] = [dict(r) for r in await conn.fetch(PER_BEAT, since, vs)]
        out["growth"] = [dict(r) for r in await conn.fetch(GROWTH, since, vs)]
        out["repeats"] = [dict(r) for r in await conn.fetch(REPEATS, since, vs)]
        out["finish"] = [dict(r) for r in await conn.fetch(FINISH, since, vs)]
        out["image_jobs"] = [dict(r) for r in await conn.fetch(IMAGES)]
        out["assets"] = [dict(r) for r in await conn.fetch(IMAGE_ASSETS)]
    finally:
        await conn.close()
    return out, args.json


def main() -> None:
    out, json_path = asyncio.run(report())
    for name, rows in out.items():
        table(name, rows)
    if json_path:
        Path(json_path).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
