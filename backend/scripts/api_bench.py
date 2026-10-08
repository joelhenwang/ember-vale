"""Read-path latency benchmark: the requests the player and library screens make.

Times each request N times and prints p50 / p95 / max latency and the
response size. Read-only: it never advances, paints or writes, so it
costs nothing.

Two modes:

- against a running API (default ``--base http://localhost:8101``); the
  bearer key comes from WORLDSIM_SECURITY__API_KEY (export that single
  variable; never source the whole .env);
- ``--inprocess``: builds the app in this process against
  WORLDSIM_DATABASE__URL (or ``--db``) and also counts, per request, the
  SQL statements run and the pool checkouts (one per unit of work).
  Background loops do not start.

    python scripts/api_bench.py --story <world_id> [--n 30] [--inprocess] [--json out.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class Result:
    name: str
    ms: list[float] = field(default_factory=list)
    size: int = 0
    status: int = 0
    queries: int = -1
    checkouts: int = -1
    gzip_kb: float = -1.0

    def row(self) -> dict[str, object]:
        ordered = sorted(self.ms)
        p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
        return {
            "name": self.name,
            "status": self.status,
            "p50_ms": round(statistics.median(ordered), 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(ordered[-1], 1),
            "kb": round(self.size / 1024, 1),
            "queries": self.queries,
            "checkouts": self.checkouts,
        }


Plan = list[tuple[str, str, dict[str, Any], dict[str, str]]]


async def build_plan(client: httpx.AsyncClient, world: str) -> Plan:
    grant = (await client.get("/stage2/roles", params={"world_id": world})).json() or {}
    me = grant.get("character_id")
    role = {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(me)} if me else {}
    chronicle = (
        await client.get(
            "/world/chronicle", params={"world_id": world, "after": 0, "limit": 100}, headers=role
        )
    ).json()
    entries = chronicle.get("entries", []) if isinstance(chronicle, dict) else []
    scenes = [e["scene_id"] for e in entries if e.get("scene_id")][-1:]
    plan: Plan = [
        ("stories list", "/stories", {}, {}),
        ("library presets", "/library/presets", {}, {}),
        ("story detail", f"/stories/{world}", {}, {}),
        ("presentation", "/world/presentation", {"world_id": world}, role),
        (
            "chronicle (100)",
            "/world/chronicle",
            {"world_id": world, "after": 0, "limit": 100},
            role,
        ),
        ("map", "/stage2/map", {"world_id": world}, role),
        ("items", "/stage2/items", {"world_id": world}, role),
        ("autoplay", f"/stories/{world}/autoplay", {}, role),
        ("settings providers", "/settings/providers", {}, {}),
        ("story drafts", "/story-drafts", {}, {}),
    ]
    if me:
        plan += [
            ("character", f"/stage1/characters/{me}", {"world_id": world}, role),
            ("suggestions", "/stage1/suggestions", {"world_id": world, "character_id": me}, role),
        ]
    for scene in scenes:
        plan.append(
            ("scene narration", f"/stage1/scenes/{scene}/narration", {"world_id": world}, role)
        )
    return plan


async def run(args: argparse.Namespace) -> list[Result]:
    counter = {"queries": 0, "checkouts": 0}
    if args.inprocess:
        from sqlalchemy import event

        from worldsim.infrastructure.settings import Settings
        from worldsim.interfaces.http.app import create_app

        if args.db:
            os.environ["WORLDSIM_DATABASE__URL"] = args.db
        os.environ.pop("WORLDSIM_SECURITY__API_KEY", None)
        app = create_app(Settings())
        engine = app.state.app_state.engine.sync_engine

        def _count(*_a: object, **_k: object) -> None:
            counter["queries"] += 1

        def _checkout(*_a: object, **_k: object) -> None:
            counter["checkouts"] += 1

        event.listen(engine, "before_cursor_execute", _count)
        event.listen(engine.pool, "checkout", _checkout)
        transport: httpx.AsyncBaseTransport = httpx.ASGITransport(app=app)
        base, headers = "http://bench/api/v1", {}
    else:
        key = os.environ.get("WORLDSIM_SECURITY__API_KEY", "")
        transport = httpx.AsyncHTTPTransport()
        base = args.base.rstrip("/") + "/api/v1"
        headers = {"Authorization": f"Bearer {key}"}

    async with httpx.AsyncClient(
        transport=transport, base_url=base, headers=headers, timeout=60
    ) as client:
        plan = await build_plan(client, args.story)
        results: list[Result] = []
        for name, path, params, extra in plan:
            r = Result(name)
            await client.get(path, params=params, headers=extra)  # warm
            for i in range(args.n):
                counter["queries"] = counter["checkouts"] = 0
                t = time.perf_counter()
                resp = await client.get(path, params=params, headers=extra)
                r.ms.append((time.perf_counter() - t) * 1000)
                if i == 0 and args.inprocess:
                    r.queries, r.checkouts = counter["queries"], counter["checkouts"]
                r.size = len(resp.content)
                r.status = resp.status_code
            results.append(r)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8101")
    parser.add_argument("--story", required=True)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--inprocess", action="store_true")
    parser.add_argument("--db", help="database URL for --inprocess (default: env)")
    parser.add_argument("--json")
    args = parser.parse_args()

    rows = [r.row() for r in asyncio.run(run(args))]
    width = max(len(str(row["name"])) for row in rows)
    print(f"{'endpoint':<{width}}  status   p50ms   p95ms   maxms      KB  queries  uow")
    for row in rows:
        print(
            f"{row['name']!s:<{width}}  {row['status']!s:>6} {row['p50_ms']!s:>7} "
            f"{row['p95_ms']!s:>7} {row['max_ms']!s:>7} {row['kb']!s:>7} "
            f"{row['queries']!s:>8} {row['checkouts']!s:>4}"
        )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"story": args.story, "n": args.n, "rows": rows}, f, indent=2)


if __name__ == "__main__":
    main()
