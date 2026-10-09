"""Live check: does a companion join, and does a companion fight? (companions-002)

A fighter (Wren) asks Ash, who stands beside them at the Hearth, to join
the party; then a fight comes. Reads the party after every turn and the
stored fight events. If the storyteller never recruits Ash, the story ends
there (that is the finding).

  python companion_check.py <api-base> <api-key> <db-url> <runs> <out.json>
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

BASE, KEY, DB, RUNS, OUT = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
NIL = "00000000-0000-0000-0000-000000000000"
WORLD = "20000000-0000-4000-8000-000000000001"
WREN = "20000000-0000-4000-8000-000000000101"
ASH = "20000000-0000-4000-8000-000000000102"

c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=900)

ASKS = [
    "Ash, the roads are getting dangerous. Will you join me as my companion and fight at my side?",
    "I offer Ash my hand: travel with me, share the road and the fights to come.",
]
FIGHT = [
    "Three goblins burst in through the Hearth's back door. I draw my longsword and attack the "
    "first goblin.",
    "I attack the goblin again.",
    "I strike at the second goblin.",
    "I fight on beside Ash.",
]
#: Said to Ash on the second fight turn instead of attacking: an order.
ORDER = "Ash, take the third goblin!"
#: After the fight: the hero walks to the market; does Ash come along?
WALK = "MARKET"


def create(title: str) -> tuple[str, str, str]:
    cast = [
        {"instance_key": "wren", "preset_id": WREN, "preset_revision": 1, "name": "Wren",
         "location_key": "hearth"},
        {"instance_key": "ash", "preset_id": ASH, "preset_revision": 1, "name": "Ash",
         "location_key": "hearth"},
    ]
    draft = c.post(
        "/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": WORLD, "preset_revision": 2},
                "cast": cast,
                "mode": {
                    "role": "player",
                    "controlled_cast_key": "wren",
                    "adventure": {"race": "human", "character_class": "fighter"},
                },
                "story": {"title": title},
                "ai": {"art_source": "curated"},
            },
            "current_step": "review",
        },
    ).json()
    made = c.post(
        "/stories",
        json={"draft_id": draft["id"], "expected_draft_version": 1},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    ).json()
    world, me = made["world_id"], made["character_id"]
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    cast_view = c.get("/world/presentation", params={"world_id": world}, headers=P).json()["cast"]
    ash = next(x["character_id"] for x in cast_view if x["name"] == "Ash")
    return world, me, ash


async def db_rows(world: str) -> tuple[list[dict[str, Any]], float]:
    conn = await asyncpg.connect(DB)
    try:
        rows = await conn.fetch(
            "SELECT absolute_index, summary FROM world_event WHERE world_id = $1 "
            "AND summary ? 'rolls' ORDER BY sequence",
            uuid.UUID(world),
        )
        spend = await conn.fetchval(
            "SELECT coalesce(sum(prompt_cost_usd + completion_cost_usd), 0) FROM model_cost "
            "WHERE world_id = $1",
            uuid.UUID(world),
        )
    finally:
        await conn.close()
    out = []
    for row in rows:
        summary = json.loads(row["summary"]) if isinstance(row["summary"], str) else row["summary"]
        out.append({"turn": row["absolute_index"], "deeds": int(summary.get("deeds", "0")),
                    "unresolved": int(summary.get("unresolved", "0")),
                    "rolls": json.loads(summary.get("rolls") or "[]")})
    return out, round(float(spend), 5)


def play(run: int) -> dict[str, Any]:
    world, me, ash = create(f"Companion check {run}")
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    turns: list[dict[str, Any]] = []
    index = 0

    def advance(intent: dict[str, Any], words: str) -> None:
        nonlocal index
        index += 1
        started = time.time()
        r = c.post(
            "/stage1/advance",
            json={"world_id": world, "absolute_index": index, "player_intents": {me: intent}},
            headers=P,
        )
        time.sleep(4)
        party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
        turns.append({
            "turn": index, "words": words, "status": r.status_code,
            "seconds": round(time.time() - started, 1),
            "party": [(m["name"], m["character_class"], m["hp_current"], m["hp_max"])
                      for m in party["members"]],
            "foes": [(f["name"], f["hp_current"]) for f in party["foes"]],
        })

    for words in ASKS:
        advance({"family": "communicate", "character_id": me, "snapshot_id": NIL,
                 "target_character_id": ash, "topic": words}, words)
        if len(turns[-1]["party"]) > 1:
            break
    joined = len(turns[-1]["party"]) > 1
    if joined:
        for n, words in enumerate(FIGHT):
            if n == 1:
                advance({"family": "communicate", "character_id": me, "snapshot_id": NIL,
                         "target_character_id": ash, "topic": ORDER}, ORDER)
                continue
            advance({"family": "interact", "character_id": me, "snapshot_id": NIL,
                     "attempt": words}, words)
        market = next(p["id"] for p in c.get("/stage2/map", params={"world_id": world},
                                             headers=P).json()["places"] if p["name"] == "Market")
        advance({"family": "move", "character_id": me, "snapshot_id": NIL,
                 "destination_location_id": market}, WALK)
    time.sleep(6)
    log, spend = asyncio.run(db_rows(world))
    chron = c.get("/world/chronicle", params={"world_id": world, "after": 0, "limit": 100},
                  headers=P).json()
    for turn in turns:
        rolls = [r for f in log if f["turn"] == turn["turn"] for r in f["rolls"]]
        turn["roll_lines"] = [r["text"] for r in rolls]
        turn["companion_rolls"] = len([r for r in rolls if r.get("actor") not in (None, "Wren")
                                       and r["kind"] in ("attack", "cast") and not r.get("actor_foe")])
        turn["hero_rolls"] = len([r for r in rolls if r.get("actor") == "Wren"
                                  and r["kind"] in ("attack", "cast")])
        turn["unresolved"] = sum(f["unresolved"] for f in log if f["turn"] == turn["turn"])
        turn["places"] = {
            x["name"]: x.get("location_id")
            for x in c.get("/world/presentation", params={"world_id": world}, headers=P).json()["cast"]
        } if turn["words"] == WALK else None
        turn["prose"] = " ".join(
            e["text"] for e in chron["entries"]
            if e["absolute_index"] == turn["turn"] and e.get("text") and not e.get("combat")
        )[:900]
    return {"run": run, "world_id": world, "joined": joined, "turns": turns, "spend_usd": spend}


results = [play(run) for run in range(1, RUNS + 1)]
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(results, fh, indent=1)
fight_turns = [t for r in results for t in r["turns"] if t["words"] in FIGHT or t["words"] == ORDER]
print(json.dumps({
    "stories": len(results),
    "joined": sum(r["joined"] for r in results),
    "fight_turns": len(fight_turns),
    "companion_acted": sum(1 for t in fight_turns if t["companion_rolls"]),
    "hero_acted": sum(1 for t in fight_turns if t["hero_rolls"]),
    "spend_usd": round(sum(r["spend_usd"] for r in results), 4),
}, indent=1))
