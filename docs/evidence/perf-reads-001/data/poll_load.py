"""Poll load test: N viewers watching one story, as the Watch screen polls while playing.

Each viewer, every ``--every`` seconds (staggered), asks for presentation,
autoplay and the chronicle after its cursor, sending If-None-Match like a
browser. Steps up N and reports p50/p95 latency, achieved requests a second
and errors per step. Read-only: it never advances the story.

    WORLDSIM_SECURITY__API_KEY=... python poll_load.py --story <world_id>
        [--steps 10,25,50,100,200] [--seconds 30] [--every 2]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time

import httpx


async def viewer(
    client: httpx.AsyncClient, story: str, every: float, stop: float, out: list[tuple[float, int]]
) -> None:
    tags: dict[str, str] = {}
    cursor = 0
    role = {"X-Worldsim-Role": "watcher"}
    await asyncio.sleep(random.uniform(0, every))
    while time.perf_counter() < stop:
        tick = time.perf_counter()
        reads = [
            ("p", "/world/presentation", {"world_id": story}),
            ("a", f"/stories/{story}/autoplay", {}),
            ("c", "/world/chronicle", {"world_id": story, "after": cursor, "limit": 100}),
        ]
        for key, path, params in reads:
            headers = dict(role)
            if key in tags:
                headers["If-None-Match"] = tags[key]
            started = time.perf_counter()
            try:
                r = await client.get(path, params=params, headers=headers)
                status = r.status_code
                if "etag" in r.headers:
                    tags[key] = r.headers["etag"]
                if key == "c" and status == 200:
                    cursor = max(cursor, int(r.json().get("next_after", cursor)))
            except httpx.HTTPError:
                status = 0
            out.append(((time.perf_counter() - started) * 1000, status))
        await asyncio.sleep(max(0.0, every - (time.perf_counter() - tick)))


async def step(base: str, key: str, story: str, n: int, seconds: float, every: float) -> dict:
    out: list[tuple[float, int]] = []
    limits = httpx.Limits(max_connections=n * 2, max_keepalive_connections=n * 2)
    async with httpx.AsyncClient(
        base_url=base + "/api/v1",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
        limits=limits,
    ) as client:
        stop = time.perf_counter() + seconds
        await asyncio.gather(*(viewer(client, story, every, stop, out) for _ in range(n)))
    ok = sorted(ms for ms, s in out if s in (200, 304))
    q = statistics.quantiles(ok, n=20) if len(ok) >= 20 else [0.0] * 19
    return {
        "viewers": n,
        "requests": len(out),
        "req_per_s": round(len(out) / seconds, 1),
        "expected_req_per_s": round(n * 3 / every, 1),
        "p50_ms": round(statistics.median(ok), 1) if ok else None,
        "p95_ms": round(q[18], 1),
        "max_ms": round(ok[-1], 1) if ok else None,
        "not_modified": sum(1 for _, s in out if s == 304),
        "errors": sum(1 for _, s in out if s not in (200, 304)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", required=True)
    parser.add_argument("--base", default="http://localhost:8101")
    parser.add_argument("--steps", default="10,25,50,100,200")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--every", type=float, default=2.0)
    parser.add_argument("--json")
    args = parser.parse_args()
    key = os.environ.get("WORLDSIM_SECURITY__API_KEY", "")
    rows = []
    for n in (int(s) for s in args.steps.split(",")):
        row = asyncio.run(step(args.base, key, args.story, n, args.seconds, args.every))
        print(json.dumps(row), flush=True)
        rows.append(row)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
