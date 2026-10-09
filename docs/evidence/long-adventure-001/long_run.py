"""A long combat adventure, played live (long-adventure-001).

Wren (a human fighter) invites Ash, then follows trouble for 26 turns: talk,
travel, two stretches where goblins are sought and fought, rests and a
night or two. Nothing is forced beyond what a player would write; whether a
fight comes is the storyteller's. After every turn it records the party,
the foes, the rolls, the prose and the time; at the end it sums what long
play looks like.

  python long_run.py <api-base> <api-key> <db-url> <runs> <out.json>
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

# (kind, words): say = to Ash, do = an interact attempt, go = travel, rest, wait
PLAN: list[tuple[str, str]] = [
    ("say", "Ash, the roads are getting dangerous. Will you join me as my companion?"),
    ("do", "I look around the Hearth and listen for news of trouble."),
    ("do", "I ask the people here whether anyone has been attacked on the roads."),
    ("go", "Market"),
    ("do", "I ask the traders about the raiders troubling their carts."),
    ("do", "I go looking for the goblins that raid the carts near the market."),
    ("do", "If goblins are here, I draw my sword and attack the nearest one."),
    ("do", "I attack the nearest enemy."),
    ("do", "I keep fighting beside Ash."),
    ("rest", ""),
    ("say", "Ash, are you hurt? We did well."),
    ("go", "Hearth"),
    ("do", "I share a meal by the fire and tend to my wounds."),
    ("rest", ""),
    ("do", "I ask around about where the raiders make their camp."),
    ("do", "I set out with Ash to find the goblin camp."),
    ("do", "I attack the first goblin I see."),
    ("say", "Ash, take the biggest one!"),
    ("do", "I attack the nearest enemy."),
    ("do", "I fight on until they are beaten."),
    ("do", "I search the area for anything the raiders left behind."),
    ("rest", ""),
    ("go", "Market"),
    ("do", "I tell the traders the raiders are dealt with."),
    ("wait", ""),
    ("do", "I look around for new trouble."),
]

c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=900)


def create(title: str) -> tuple[str, str, str, dict[str, str]]:
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
        "story": {"title": title}, "ai": {"art_source": "curated"}},
        "current_step": "review"}).json()
    made = c.post("/stories", json={"draft_id": draft["id"], "expected_draft_version": 1},
                  headers={"Idempotency-Key": str(uuid.uuid4())}).json()
    world, me = made["world_id"], made["character_id"]
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    cast_view = c.get("/world/presentation", params={"world_id": world}, headers=P).json()["cast"]
    ash = next(x["character_id"] for x in cast_view if x["name"] == "Ash")
    places = {p["name"]: p["id"] for p in
              c.get("/stage2/map", params={"world_id": world}, headers=P).json()["places"]}
    return world, me, ash, places


async def stored(world: str) -> tuple[list[dict[str, Any]], float, list[tuple[int, str, str]]]:
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
            "JOIN phase_run pr ON pr.id = i.phase_run_id WHERE i.world_id = $1 "
            "AND i.intent::text NOT LIKE '%' || $2 || '%' ORDER BY 1", uuid.UUID(world), NIL)
    finally:
        await conn.close()
    log = []
    for row in rows:
        s = json.loads(row["summary"]) if isinstance(row["summary"], str) else row["summary"]
        log.append({"turn": row["absolute_index"], "summary": {k: v for k, v in s.items() if k != "rolls"},
                    "rolls": json.loads(s.get("rolls") or "[]")})
    acts = []
    for r in intents:
        a = json.loads(r[2])["action"]
        acts.append((r[0], r[1], (a.get("attempt") or a.get("topic") or "")[:120]))
    return log, round(float(spend), 5), acts


def play(run: int) -> dict[str, Any]:
    world, me, ash, places = create(f"Long adventure {run}")
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    turns: list[dict[str, Any]] = []
    for index, (kind, words) in enumerate(PLAN, start=1):
        if kind == "say":
            intent = {"family": "communicate", "target_character_id": ash, "topic": words}
        elif kind == "do":
            intent = {"family": "interact", "attempt": words}
        elif kind == "go":
            intent = {"family": "move", "destination_location_id": places[words]}
        elif kind == "rest":
            intent = {"family": "rest"}
        else:
            intent = {"family": "wait"}
        started = time.time()
        r = c.post("/stage1/advance", json={"world_id": world, "absolute_index": index,
                   "player_intents": {me: {**intent, "character_id": me, "snapshot_id": NIL}}},
                   headers=P)
        party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
        view = c.get("/world/presentation", params={"world_id": world}, headers=P).json()
        turns.append({
            "turn": index, "kind": kind, "words": words, "status": r.status_code,
            "error": None if r.status_code == 200 else r.text[:300],
            "seconds": round(time.time() - started, 1),
            "day": view.get("day"), "phase": view.get("phase"),
            "party": [{k: m.get(k) for k in ("name", "character_class", "level", "xp", "hp_current",
                                             "hp_max", "conditions")} for m in party["members"]],
            "foes": [(f["name"], f["hp_current"]) for f in party["foes"]],
            "places": {x["name"]: x.get("location_id") for x in view["cast"]},
            "rumours": [x.get("title") for x in view.get("rumours", [])],
            "settled": [x.get("title") for x in view.get("settled", [])],
        })
        print(run, index, kind, r.status_code, turns[-1]["seconds"], "s", flush=True)
        if r.status_code != 200:
            break
    time.sleep(8)
    chron = c.get("/world/chronicle", params={"world_id": world, "after": 0, "limit": 100},
                  headers=P).json()
    entries = chron["entries"]
    while chron.get("has_more"):
        chron = c.get("/world/chronicle", params={"world_id": world,
                      "after": chron["next_after"], "limit": 100}, headers=P).json()
        entries += chron["entries"]
    log, spend, acts = asyncio.run(stored(world))
    for t in turns:
        t["prose"] = " ".join(e["text"] for e in entries if e["absolute_index"] == t["turn"]
                              and e.get("text") and not e.get("combat"))[:1500]
        t["rolls"] = [r["text"] for f in log if f["turn"] == t["turn"] for r in f["rolls"]]
        t["fight"] = [f["summary"] for f in log if f["turn"] == t["turn"]]
        t["ash_chose"] = [a for a in acts if a[0] == t["turn"]]
    return {"run": run, "world_id": world, "turns": turns, "spend_usd": spend}


results = []
for run in range(1, RUNS + 1):
    results.append(play(run))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    print("story", run, "spend", results[-1]["spend_usd"], flush=True)
