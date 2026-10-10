"""Shops played live (shops-001): a fighter at the Hearth (an inn) with 8 gold
coins (test data) buys a meal, then a room, then goes to the Market and buys a
potion of healing, and drinks it.

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
c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=900)


async def db(query: str, *args: Any) -> list[Any]:
    conn = await asyncpg.connect(DB)
    try:
        return list(await conn.fetch(query, *args))
    finally:
        await conn.close()


def main() -> None:
    cast = [
        {"instance_key": "wren", "preset_id": WREN, "preset_revision": 1, "name": "Wren",
         "location_key": "hearth"},
        {"instance_key": "ash", "preset_id": ASH, "preset_revision": 1, "name": "Ash",
         "location_key": "market"},
    ]
    draft = c.post("/story-drafts", json={"payload": {
        "world": {"preset_id": WORLD, "preset_revision": 2}, "cast": cast,
        "mode": {"role": "player", "controlled_cast_key": "wren",
                 "adventure": {"race": "human", "character_class": "fighter"}},
        "story": {"title": "Coins to spend"}, "ai": {"art_source": "curated"}},
        "current_step": "review"}).json()
    made = c.post("/stories", json={"draft_id": draft["id"], "expected_draft_version": 1},
                  headers={"Idempotency-Key": str(uuid.uuid4())}).json()
    world, me = made["world_id"], made["character_id"]
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    # Test data: a purse of 8 gold coins, and the hero a little hurt.
    asyncio.run(db(
        "INSERT INTO item_instance (id, world_id, item_key, owner_id, quantity, version, name) "
        "VALUES ($1, $2, 'gold-coins', $3, 8, 0, 'gold coins')",
        uuid.uuid4(), uuid.UUID(world), uuid.UUID(me)))
    asyncio.run(db(
        "UPDATE dnd_party_member SET sheet = jsonb_set(sheet, '{hp,current}', '4') "
        "WHERE world_id = $1 AND character_id = $2", uuid.UUID(world), uuid.UUID(me)))
    places = {p["name"]: p["id"] for p in
              c.get("/stage2/map", params={"world_id": world}, headers=P).json()["places"]}
    plan: list[tuple[str, str]] = [
        ("do", "I buy a hot meal from the innkeeper."),
        ("do", "I rent a room for the night."),
        ("go", "Market"),
        ("do", "I buy a potion of healing."),
        ("do", "I drink the potion of healing."),
    ]
    turns = []
    for index, (kind, words) in enumerate(plan, start=1):
        shop = c.get("/stage1/shop", params={"world_id": world}, headers=P).json()
        intent: dict[str, Any] = (
            {"family": "interact", "attempt": words} if kind == "do"
            else {"family": "move", "destination_location_id": places[words]}
        )
        started = time.time()
        r = c.post("/stage1/advance", json={"world_id": world, "absolute_index": index,
                   "player_intents": {me: {**intent, "character_id": me, "snapshot_id": NIL}}},
                   headers=P)
        time.sleep(6)
        party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
        held = asyncio.run(db(
            "SELECT coalesce(i.name, i.item_key) AS n, i.quantity AS q FROM item_instance i "
            "WHERE i.world_id = $1 AND i.owner_id = $2 ORDER BY 1", uuid.UUID(world), uuid.UUID(me)))
        turns.append({
            "turn": index, "words": words, "status": r.status_code,
            "error": None if r.status_code == 200 else r.text[:300],
            "seconds": round(time.time() - started, 1),
            "shop_before": shop,
            "held_after": [(h["n"], h["q"]) for h in held],
            "hp_after": [(m["name"], m["hp_current"], m["hp_max"]) for m in party["members"]],
        })
        print(index, words, r.status_code, turns[-1]["held_after"], turns[-1]["hp_after"], flush=True)
    rows = asyncio.run(db(
        "SELECT absolute_index, summary FROM world_event WHERE world_id = $1 AND summary ? 'rolls' "
        "ORDER BY sequence", uuid.UUID(world)))
    for t in turns:
        t["rolls"] = [
            x["text"] for row in rows if row["absolute_index"] == t["turn"]
            for x in json.loads(json.loads(row["summary"])["rolls"] if isinstance(row["summary"], str)
                                else row["summary"]["rolls"])
        ]
    spend = asyncio.run(db("SELECT coalesce(sum(prompt_cost_usd + completion_cost_usd), 0) AS s "
                           "FROM model_cost WHERE world_id = $1", uuid.UUID(world)))[0]["s"]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"world_id": world, "spend_usd": float(spend), "turns": turns}, fh, indent=1,
                  default=str)
    print("world", world, "spend", float(spend))


main()
