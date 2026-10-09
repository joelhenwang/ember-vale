"""Live quality check of combat stories (combat-depth-002).

Plays scripted adventures with fights against a running API (the dev API
with the repo's live provider), then reads the stored fight events to
measure: does a fight start, does the hero's own attack roll on every turn
they attack (and was it the storyteller's tag or the hero's own words),
do foes strike back, do tags fail, and does the fight end.

  python combat_check.py <api-base> <api-key> <db-url> <runs> <out.json>

<db-url> is a plain postgresql:// URL of the API's database (read only).
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
DAMAGE_SPELLS = ("Fire Bolt", "Sacred Flame", "Ray of Frost", "Eldritch Blast", "Chill Touch")

# (attempt, is it an attack the hero makes)
SCENARIOS: dict[str, tuple[str, list[tuple[str, bool]]]] = {
    "fighter-goblins": (
        "fighter",
        [
            (
                "Two goblins burst in through the Hearth's back door, knives out. "
                "I draw my longsword and attack the nearest goblin.",
                True,
            ),
            ("I attack the goblin again with my longsword.", True),
            ("I go after the second goblin.", True),
            ("I strike at whichever goblin is still standing.", True),
            ("I catch my breath and look around the room.", False),
            ("If anything still threatens us, I attack it.", True),
        ],
    ),
    "wizard-wolf": (
        "wizard",
        [
            (
                "A grey wolf slinks into the Hearth, growling at me. I hurl a {spell} at the wolf.",
                True,
            ),
            ("I cast {spell} at the wolf again.", True),
            ("I back away and throw another {spell} at it.", True),
            ("I stab at the wolf with my dagger.", True),
            ("I look around the room.", False),
            ("I cast {spell} at anything still hostile.", True),
        ],
    ),
    "cleric-bandit": (
        "cleric",
        [
            (
                "A bandit kicks open the Hearth's door and swings a club at me. "
                "I raise my mace and strike the bandit.",
                True,
            ),
            ("I hit the bandit with my mace again.", True),
            ("I call down {spell} on the bandit.", True),
            ("I cast cure wounds on myself.", False),
            ("I attack the bandit.", True),
            ("I look around the room.", False),
        ],
    ),
}

c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=900)


def create(klass: str, title: str) -> tuple[str, str]:
    draft = c.post(
        "/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": WORLD, "preset_revision": 2},
                "cast": [
                    {"instance_key": "wren", "preset_id": WREN, "preset_revision": 1, "name": "Wren"},
                    {"instance_key": "ash", "preset_id": ASH, "preset_revision": 1, "name": "Ash"},
                ],
                "mode": {
                    "role": "player",
                    "controlled_cast_key": "wren",
                    "adventure": {"race": "human", "character_class": klass},
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
    return made["world_id"], made["character_id"]


async def fights(world: str) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(DB)
    try:
        rows = await conn.fetch(
            "SELECT absolute_index, summary FROM world_event WHERE world_id = $1 "
            "AND summary ? 'rolls' ORDER BY sequence",
            uuid.UUID(world),
        )
    finally:
        await conn.close()
    out = []
    for row in rows:
        summary = json.loads(row["summary"]) if isinstance(row["summary"], str) else row["summary"]
        out.append(
            {
                "turn": row["absolute_index"],
                "deeds": int(summary.get("deeds", "0")),
                "unresolved": int(summary.get("unresolved", "0")),
                "rolls": json.loads(summary.get("rolls") or "[]"),
            }
        )
    return out


async def spent(world: str) -> float:
    """What the story's model calls were billed (model_cost)."""
    conn = await asyncpg.connect(DB)
    try:
        total = await conn.fetchval(
            "SELECT coalesce(sum(prompt_cost_usd + completion_cost_usd), 0) FROM model_cost "
            "WHERE world_id = $1",
            uuid.UUID(world),
        )
    finally:
        await conn.close()
    return round(float(total), 5)


def play(name: str, klass: str, turns: list[tuple[str, bool]], run: int) -> dict[str, Any]:
    world, me = create(klass, f"Combat check {name} {run}")
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
    hero = party["members"][0]
    spell = next((s for s in DAMAGE_SPELLS if s in hero["spells"]), "a spell")
    played = []
    for i, (attempt, attacks) in enumerate(turns, start=1):
        words = attempt.format(spell=spell.lower())
        started = time.time()
        r = c.post(
            "/stage1/advance",
            json={
                "world_id": world,
                "absolute_index": i,
                "player_intents": {
                    me: {
                        "family": "interact",
                        "character_id": me,
                        "snapshot_id": NIL,
                        "attempt": words,
                    }
                },
            },
            headers=P,
        )
        played.append(
            {"turn": i, "attempt": words, "attacks": attacks, "status": r.status_code,
             "seconds": round(time.time() - started, 1)}
        )
    time.sleep(8)  # background narration and tag resolution settle
    chron = c.get(
        "/world/chronicle", params={"world_id": world, "after": 0, "limit": 100}, headers=P
    ).json()
    prose: dict[int, str] = {}
    for e in chron["entries"]:
        if e.get("text") and me in (e.get("participant_ids") or []) and not e.get("combat"):
            seen = prose.get(e["absolute_index"], "")
            prose[e["absolute_index"]] = f"{seen} {e['text']}".strip()
    log = asyncio.run(fights(world))
    after = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
    spend = asyncio.run(spent(world))
    for turn in played:
        events = [f for f in log if f["turn"] == turn["turn"]]
        rolls = [r for f in events for r in f["rolls"]]
        mine = [r for r in rolls if r.get("actor") == hero["name"] and r["kind"] in ("attack", "cast")]
        turn["hero_rolls"] = len(mine)
        turn["deeds"] = sum(f["deeds"] for f in events)
        turn["storyteller_hero_rolls"] = max(0, len(mine) - turn["deeds"])
        turn["foe_strikes"] = len([r for r in rolls if r.get("actor_foe")])
        turn["encounters"] = [r.get("target") for r in rolls if r["kind"] == "encounter"]
        turn["unresolved"] = sum(f["unresolved"] for f in events)
        turn["roll_lines"] = [r["text"] for r in rolls]
        turn["prose"] = prose.get(turn["turn"])
    return {
        "scenario": name,
        "run": run,
        "world_id": world,
        "class": klass,
        "spell": spell,
        "turns": played,
        "foes_left": [(f["name"], f["hp_current"]) for f in after["foes"]],
        "hero_after": {
            k: after["members"][0][k] for k in ("level", "xp", "hp_current", "hp_max", "choices")
        },
        "spend_usd": spend,
    }


results = []
for run in range(1, RUNS + 1):
    for name, (klass, turns) in SCENARIOS.items():
        results.append(play(name, klass, turns, run))
        print(name, run, "spend", results[-1]["spend_usd"], flush=True)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(results, fh, indent=1)
attack_turns = [t for r in results for t in r["turns"] if t["attacks"]]
summary = {
    "stories": len(results),
    "attack_turns": len(attack_turns),
    "hero_rolled": sum(1 for t in attack_turns if t["hero_rolls"]),
    "storyteller_tagged_hero": sum(1 for t in attack_turns if t["storyteller_hero_rolls"]),
    "from_deeds": sum(t["deeds"] for r in results for t in r["turns"]),
    "foe_strikes": sum(t["foe_strikes"] for r in results for t in r["turns"]),
    "unresolved": sum(t["unresolved"] for r in results for t in r["turns"]),
    "fights_started": sum(
        1 for r in results if any(t["encounters"] or t["hero_rolls"] for t in r["turns"])
    ),
    "fights_won": sum(1 for r in results if r["foes_left"] == [] and any(t["hero_rolls"] for t in r["turns"])),
    "spend_usd": round(sum(r["spend_usd"] or 0 for r in results), 4),
}
print(json.dumps(summary, indent=1))
