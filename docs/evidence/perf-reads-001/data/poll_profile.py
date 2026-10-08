"""Profile the reads a Watch tick makes (presentation, autoplay, chronicle) in-process.

    WORLDSIM_DATABASE__URL=... python poll_profile.py <world_id> [n]
"""

from __future__ import annotations

import asyncio
import cProfile
import io
import os
import pstats
import sys
import time

import httpx

from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


async def main(story: str, n: int) -> None:
    os.environ.pop("WORLDSIM_SECURITY__API_KEY", None)
    os.environ["WORLDSIM_AUTOPLAY__ENABLED"] = "false"
    app = create_app(Settings())
    role = {"X-Worldsim-Role": "watcher"}
    reads = [
        ("/world/presentation", {"world_id": story}),
        (f"/stories/{story}/autoplay", {}),
        ("/world/chronicle", {"world_id": story, "after": 10**9, "limit": 100}),
    ]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://p/api/v1") as c:
            tags: dict[str, str] = {}

            async def tick() -> None:
                for path, params in reads:
                    h = dict(role)
                    if path in tags:
                        h["If-None-Match"] = tags[path]
                    r = await c.get(path, params=params, headers=h)
                    tags[path] = r.headers.get("etag", tags.get(path, ""))

            for _ in range(20):
                await tick()
            per: dict[str, list[float]] = {p: [] for p, _ in reads}
            for _ in range(n):
                for path, params in reads:
                    h = dict(role)
                    h["If-None-Match"] = tags.get(path, "")
                    t = time.perf_counter()
                    await c.get(path, params=params, headers=h)
                    per[path].append((time.perf_counter() - t) * 1000)
            for path, xs in per.items():
                xs.sort()
                print(f"{path:30} p50 {xs[len(xs) // 2]:6.1f} ms")
            prof = cProfile.Profile()
            prof.enable()
            for _ in range(n):
                await tick()
            prof.disable()
    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("tottime").print_stats(25)
    print(buf.getvalue()[:6000])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 100))
