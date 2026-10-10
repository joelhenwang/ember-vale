"""Shops, second round, live (shops-002): in the shops-001 story at the
Market, Wren is given a scimitar (test data), sells it, walks to the
Hearth, rents a room and wakes rested.

  python live_run.py <api-base> <api-key> <db-url> <world_id> <first_index> <out.json>
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

BASE, KEY, DB, WORLD_ID, FIRST, OUT = sys.argv[1:7]
NIL = "00000000-0000-0000-0000-000000000000"
c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=900)


async def db(query: str, *args: Any) -> list[Any]:
    conn = await asyncpg.connect(DB)
    try:
        return list(await conn.fetch(query, *args))
    finally:
        await conn.close()


def main() -> None:
    w = uuid.UUID(WORLD_ID)
    me = str(asyncio.run(db("SELECT character_id FROM dnd_party_member WHERE world_id = $1", w))[0][0])
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    if not asyncio.run(db("SELECT 1 FROM item_instance WHERE world_id = $1 AND owner_id = $2 "
                          "AND item_key = 'scimitar'", w, uuid.UUID(me))):
        asyncio.run(db("INSERT INTO item_instance (id, world_id, item_key, owner_id, quantity, "
                       "version, name) VALUES ($1, $2, 'scimitar', $3, 1, 0, 'scimitar')",
                       uuid.uuid4(), w, uuid.UUID(me)))
    places = {p["name"]: p["id"] for p in
              c.get("/stage2/map", params={"world_id": WORLD_ID}, headers=P).json()["places"]}
    plan: list[dict[str, Any]] = [
        {"family": "interact", "attempt": "I sell the scimitar to the trader"},
        {"family": "move", "destination_location_id": places["Hearth"]},
        {"family": "interact", "attempt": "I rent a room for the night"},
    ]
    turns = []
    for offset, intent in enumerate(plan):
        index = int(FIRST) + offset
        shop = c.get("/stage1/shop", params={"world_id": WORLD_ID}, headers=P).json()
        r = c.post("/stage1/advance", json={"world_id": WORLD_ID, "absolute_index": index,
                   "player_intents": {me: {**intent, "character_id": me, "snapshot_id": NIL}}},
                   headers=P)
        time.sleep(8)
        party = c.get("/stage1/party", params={"world_id": WORLD_ID}, headers=P).json()
        held = asyncio.run(db("SELECT coalesce(name, item_key) AS n, quantity AS q FROM item_instance "
                              "WHERE world_id = $1 AND owner_id = $2 ORDER BY 1", w, uuid.UUID(me)))
        stamina = asyncio.run(db("SELECT stamina FROM character_state WHERE character_id = $1",
                                 uuid.UUID(me)))[0][0]
        rows = asyncio.run(db("SELECT summary FROM world_event WHERE world_id = $1 AND "
                              "absolute_index = $2 AND summary ? 'rolls'", w, index))
        rolls = [x["text"] for row in rows for x in json.loads(
            json.loads(row["summary"])["rolls"] if isinstance(row["summary"], str) else row["summary"]["rolls"])]
        turns.append({"turn": index, "intent": intent.get("attempt") or "go to Hearth",
                      "status": r.status_code, "buys_before": shop.get("buys"),
                      "purse_before": shop.get("purse"), "held_after": [(h["n"], h["q"]) for h in held],
                      "hp_after": [(m["name"], m["hp_current"], m["hp_max"]) for m in party["members"]],
                      "stamina_after": stamina, "rolls": rolls})
        print(turns[-1], flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"world_id": WORLD_ID, "turns": turns}, fh, indent=1, default=str)


main()
