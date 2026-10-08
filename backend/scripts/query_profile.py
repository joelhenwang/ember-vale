"""Time each SQL statement one request runs, slowest first.

    python scripts/query_profile.py --db <url> --path /world/presentation \\
        --param world_id=<id> [--header X-Worldsim-Role=player ...] [--repeat 5]

Builds the app in-process (no background loops) and prints, for the last
of --repeat runs, each statement's time and the first line of its SQL.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from typing import Any

import httpx
from sqlalchemy import event


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    os.environ["WORLDSIM_DATABASE__URL"] = args.db
    os.environ.pop("WORLDSIM_SECURITY__API_KEY", None)

    from worldsim.infrastructure.settings import Settings
    from worldsim.interfaces.http.app import create_app

    app = create_app(Settings())
    engine = app.state.app_state.engine.sync_engine
    timings: list[tuple[float, str]] = []

    def before(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        conn.info["t0"] = time.perf_counter()

    def after(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        timings.append(((time.perf_counter() - conn.info["t0"]) * 1000, statement))

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)
    params = dict(p.split("=", 1) for p in args.param)
    headers = dict(h.split("=", 1) for h in args.header)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://bench/api/v1"
    ) as client:
        for _ in range(args.repeat):
            timings.clear()
            t = time.perf_counter()
            resp = await client.get(args.path, params=params, headers=headers)
            total = (time.perf_counter() - t) * 1000
    print(f"{resp.status_code}  total {total:.1f} ms  sql {sum(t for t, _ in timings):.1f} ms")
    for ms, sql in sorted(timings, reverse=True)[:15]:
        print(f"{ms:7.1f} ms  {' '.join(sql.split())[:150]}")


if __name__ == "__main__":
    asyncio.run(main())
