"""Continue the shops story (shops-001 run 1) with 3 more coins (test data):
buy the potion of healing (6), drink it.

  python live_more.py <api-base> <api-key> <db-url> <world_id> <first_index> <out.json>
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
    asyncio.run(db("UPDATE item_instance SET quantity = quantity + 3 WHERE world_id = $1 "
                   "AND owner_id = $2 AND item_key = 'gold-coins'", w, uuid.UUID(me)))
    turns = []
    for offset, words in enumerate(["I buy a potion of healing.", "I drink the potion of healing."]):
        index = int(FIRST) + offset
        shop = c.get("/stage1/shop", params={"world_id": WORLD_ID}, headers=P).json()
        r = c.post("/stage1/advance", json={"world_id": WORLD_ID, "absolute_index": index,
                   "player_intents": {me: {"family": "interact", "attempt": words,
                                           "character_id": me, "snapshot_id": NIL}}}, headers=P)
        time.sleep(8)
        party = c.get("/stage1/party", params={"world_id": WORLD_ID}, headers=P).json()
        held = asyncio.run(db("SELECT coalesce(name, item_key) AS n, quantity AS q FROM item_instance "
                              "WHERE world_id = $1 AND owner_id = $2 ORDER BY 1", w, uuid.UUID(me)))
        rows = asyncio.run(db("SELECT summary FROM world_event WHERE world_id = $1 AND "
                              "absolute_index = $2 AND summary ? 'rolls'", w, index))
        rolls = [x["text"] for row in rows for x in json.loads(
            json.loads(row["summary"])["rolls"] if isinstance(row["summary"], str) else row["summary"]["rolls"])]
        turns.append({"turn": index, "words": words, "status": r.status_code,
                      "purse_before": shop.get("purse"), "held_after": [(h["n"], h["q"]) for h in held],
                      "hp_after": [(m["name"], m["hp_current"], m["hp_max"]) for m in party["members"]],
                      "rolls": rolls})
        print(turns[-1], flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"world_id": WORLD_ID, "turns": turns}, fh, indent=1, default=str)


main()
