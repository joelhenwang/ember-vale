"""A watched adventure played live (watched-party-001): Wren and Ash, nobody
played, a party with fights. Does an all-AI party go looking for trouble, do
fights start and roll, do the members fight together?

  python live_run.py <api-base> <api-key> <db-url> <turns> <out.json>
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from typing import Any

import asyncpg
import httpx

BASE, KEY, DB, TURNS, OUT = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
WORLD = "20000000-0000-4000-8000-000000000001"
WREN = "20000000-0000-4000-8000-000000000101"
ASH = "20000000-0000-4000-8000-000000000102"
W = {"X-Worldsim-Role": "watcher"}
c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=900)


def create() -> str:
    cast = [
        {"instance_key": "wren", "preset_id": WREN, "preset_revision": 1, "name": "Wren",
         "location_key": "hearth"},
        {"instance_key": "ash", "preset_id": ASH, "preset_revision": 1, "name": "Ash",
         "location_key": "hearth"},
    ]
    draft = c.post("/story-drafts", json={"payload": {
        "world": {"preset_id": WORLD, "preset_revision": 2}, "cast": cast,
        "mode": {"role": "watcher", "adventure": {}},
        "story": {"title": "A watched adventure"}, "ai": {"art_source": "curated"}},
        "current_step": "review"}).json()
    made = c.post("/stories", json={"draft_id": draft["id"], "expected_draft_version": 1},
                  headers={"Idempotency-Key": str(uuid.uuid4())})
    assert made.status_code == 200, made.text
    return made.json()["world_id"]


async def stored(world: str) -> tuple[list[Any], float, list[Any]]:
    conn = await asyncpg.connect(DB)
    try:
        rows = await conn.fetch(
            "SELECT absolute_index, summary FROM world_event WHERE world_id = $1 "
            "AND summary ? 'rolls' ORDER BY sequence", uuid.UUID(world))
        spend = await conn.fetchval(
            "SELECT coalesce(sum(prompt_cost_usd + completion_cost_usd), 0) FROM model_cost "
            "WHERE world_id = $1", uuid.UUID(world))
        intents = await conn.fetch(
            "SELECT pr.absolute_index, i.family, i.intent::text FROM character_intent i "
            "JOIN phase_run pr ON pr.id = i.phase_run_id WHERE i.world_id = $1 ORDER BY 1",
            uuid.UUID(world))
    finally:
        await conn.close()
    return list(rows), float(spend), list(intents)


def main() -> None:
    world = create()
    party0 = c.get("/stage1/party", params={"world_id": world}, headers=W).json()
    print("party", [(m["name"], m.get("race"), m.get("character_class")) for m in party0["members"]])
    turns: list[dict[str, Any]] = []
    for index in range(1, TURNS + 1):
        started = time.time()
        r = c.post("/stage1/advance", json={"world_id": world, "absolute_index": index}, headers=W)
        party = c.get("/stage1/party", params={"world_id": world}, headers=W).json()
        view = c.get("/world/presentation", params={"world_id": world}, headers=W).json()
        turns.append({
            "turn": index, "status": r.status_code,
            "error": None if r.status_code == 200 else r.text[:300],
            "seconds": round(time.time() - started, 1),
            "party": [{k: m.get(k) for k in ("name", "character_class", "level", "xp",
                                             "hp_current", "hp_max", "choices")}
                      for m in party["members"]],
            "foes": [(f["name"], f["hp_current"]) for f in party["foes"]],
            "places": {x["name"]: x.get("location_id") for x in view["cast"]},
        })
        print(index, r.status_code, turns[-1]["seconds"], "s", turns[-1]["foes"], flush=True)
        if r.status_code != 200:
            break
    time.sleep(10)
    rows, spend, intents = asyncio.run(stored(world))
    chron = c.get("/world/chronicle", params={"world_id": world, "after": 0, "limit": 100},
                  headers=W).json()["entries"]
    for t in turns:
        t["rolls"] = [
            r["text"] for row in rows if row["absolute_index"] == t["turn"]
            for r in json.loads((json.loads(row["summary"]) if isinstance(row["summary"], str)
                                 else row["summary"]).get("rolls") or "[]")
        ]
        t["acts"] = [
            (fam, (json.loads(raw)["action"].get("attempt") or json.loads(raw)["action"].get("topic")
                   or "")[:120])
            for idx, fam, raw in intents if idx == t["turn"]
        ]
        t["prose"] = " ".join(e["text"] for e in chron if e["absolute_index"] == t["turn"]
                              and e.get("text") and not e.get("combat"))[:1200]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"world_id": world, "spend_usd": spend,
                   "party": party0["members"], "turns": turns}, fh, indent=1, default=str)
    print("world", world, "spend", spend)


main()
