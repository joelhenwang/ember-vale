"""A short live adventure for combat-depth-003: ability checks outside fights,
gold coins from the fallen, and a level-4 ability improvement.

Wren (a human fighter) starts as test data at 2,690 experience, just short of
level 4 (2,700), so the first fight's experience brings the three levels and
the ability choice at once. The plan climbs, looks for trouble, fights,
searches the fallen, picks up what lies there and pays Ash.

  python live_run.py <api-base> <api-key> <db-url> <out.json>
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

BASE, KEY, DB, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
NIL = "00000000-0000-0000-0000-000000000000"
WORLD = "20000000-0000-4000-8000-000000000001"
WREN = "20000000-0000-4000-8000-000000000101"
ASH = "20000000-0000-4000-8000-000000000102"

PLAN: list[tuple[str, str]] = [
    ("do", "I climb the steep wall of the old granary to look out over the vale."),
    ("do", "I search the hearth's woodpile for anything hidden there."),
    ("do", "I go looking for the goblins that raid the carts near the hearth."),
    ("do", "If goblins are here, I draw my sword and attack the nearest one."),
    ("do", "I attack the nearest enemy."),
    ("do", "I attack the nearest enemy."),
    ("do", "I fight on until they are beaten."),
    ("take", ""),
    ("take", ""),
    ("pay", "I pay Ash 2 gold coins for watching my back."),
]

c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=900)


async def db(query: str, *args: Any) -> list[Any]:
    conn = await asyncpg.connect(DB)
    try:
        return list(await conn.fetch(query, *args))
    finally:
        await conn.close()


def create() -> tuple[str, str, str]:
    cast = [
        {"instance_key": "wren", "preset_id": WREN, "preset_revision": 1, "name": "Wren",
         "location_key": "hearth"},
        {"instance_key": "ash", "preset_id": ASH, "preset_revision": 1, "name": "Ash",
         "location_key": "hearth"},
    ]
    draft = c.post("/story-drafts", json={"payload": {
        "world": {"preset_id": WORLD, "preset_revision": 2}, "cast": cast,
        "mode": {"role": "player", "controlled_cast_key": "wren",
                 "adventure": {"race": "human", "character_class": "fighter"}},
        "story": {"title": "Checks, coins and a fourth level"}, "ai": {"art_source": "curated"}},
        "current_step": "review"}).json()
    made = c.post("/stories", json={"draft_id": draft["id"], "expected_draft_version": 1},
                  headers={"Idempotency-Key": str(uuid.uuid4())}).json()
    world, me = made["world_id"], made["character_id"]
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    cast_view = c.get("/world/presentation", params={"world_id": world}, headers=P).json()["cast"]
    ash = next(x["character_id"] for x in cast_view if x["name"] == "Ash")
    # Test data: just short of level 4.
    asyncio.run(db(
        "UPDATE dnd_party_member SET sheet = jsonb_set(sheet, '{xp}', '2690') "
        "WHERE world_id = $1 AND character_id = $2", uuid.UUID(world), uuid.UUID(me)))
    return world, me, ash


def lying(world: str, me: str) -> list[dict[str, Any]]:
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    cast = c.get("/world/presentation", params={"world_id": world}, headers=P).json()["cast"]
    here = next(x["location_id"] for x in cast if x["character_id"] == me)
    rows = asyncio.run(db(
        "SELECT i.id, coalesce(i.name, i.item_key) AS name, i.quantity FROM item_instance i "
        "WHERE i.world_id = $1 AND i.owner_id IS NULL AND i.location_id = $2 "
        "ORDER BY i.item_key DESC",
        uuid.UUID(world), uuid.UUID(here)))
    return [dict(r) for r in rows]


def held(world: str) -> list[tuple[str, str, int]]:
    rows = asyncio.run(db(
        "SELECT c.name AS who, coalesce(i.name, i.item_key) AS name, i.quantity FROM item_instance i "
        "JOIN character c ON c.id = i.owner_id WHERE i.world_id = $1 ORDER BY 1, 2",
        uuid.UUID(world)))
    return [(r["who"], r["name"], r["quantity"]) for r in rows]


def main() -> None:
    world, me, ash = create()
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    turns: list[dict[str, Any]] = []
    for index, (kind, words) in enumerate(PLAN, start=1):
        if kind == "do":
            intent: dict[str, Any] = {"family": "interact", "attempt": words}
        elif kind == "pay":
            intent = {"family": "interact", "attempt": words, "target_character_id": ash}
        else:
            ground = lying(world, me)
            if not ground:
                intent, words = {"family": "wait"}, "(nothing lying here)"
            else:
                intent = {"family": "take", "item_instance_id": str(ground[0]["id"])}
                words = f"take {ground[0]['quantity']} {ground[0]['name']}"
        started = time.time()
        r = c.post("/stage1/advance", json={"world_id": world, "absolute_index": index,
                   "player_intents": {me: {**intent, "character_id": me, "snapshot_id": NIL}}},
                   headers=P)
        party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
        turns.append({
            "turn": index, "kind": kind, "words": words, "status": r.status_code,
            "error": None if r.status_code == 200 else r.text[:300],
            "seconds": round(time.time() - started, 1),
            "party": [{k: m.get(k) for k in ("name", "level", "xp", "hp_current", "hp_max",
                                             "choices", "abilities")} for m in party["members"]],
            "foes": [(f["name"], f["hp_current"]) for f in party["foes"]],
            "held": held(world),
        })
        print(index, kind, r.status_code, turns[-1]["seconds"], "s", flush=True)
        if r.status_code != 200:
            break
    time.sleep(10)
    rows = asyncio.run(db(
        "SELECT absolute_index, summary FROM world_event WHERE world_id = $1 "
        "AND summary ? 'rolls' ORDER BY sequence", uuid.UUID(world)))
    spend = asyncio.run(db(
        "SELECT coalesce(sum(prompt_cost_usd + completion_cost_usd), 0) AS s FROM model_cost "
        "WHERE world_id = $1", uuid.UUID(world)))[0]["s"]
    chron = c.get("/world/chronicle", params={"world_id": world, "after": 0, "limit": 100},
                  headers=P).json()["entries"]
    for t in turns:
        t["rolls"] = [
            r["text"]
            for row in rows if row["absolute_index"] == t["turn"]
            for r in json.loads(json.loads(row["summary"])["rolls"]
                                if isinstance(row["summary"], str) else row["summary"]["rolls"])
        ]
        t["prose"] = " ".join(e["text"] for e in chron if e["absolute_index"] == t["turn"]
                              and e.get("text") and not e.get("combat"))[:1200]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"world_id": world, "spend_usd": float(spend), "turns": turns}, fh, indent=1)
    print("world", world, "spend", float(spend))


main()
