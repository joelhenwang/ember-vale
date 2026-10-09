"""One short live check: does a real narrator, given dnd-rules.v2, write
tags the engine can roll? Creates a combat story (Wren, human fighter),
plays three turns of a goblin fight through the API and prints what the
engine rolled. Usage: python live_check.py <api-base> <api-key>"""

from __future__ import annotations

import json
import sys
import time
import uuid

import httpx

BASE, KEY = sys.argv[1], sys.argv[2]
NIL = "00000000-0000-0000-0000-000000000000"
H = {"Authorization": f"Bearer {KEY}"}
WORLD = "20000000-0000-4000-8000-000000000001"
WREN = "20000000-0000-4000-8000-000000000101"
ASH = "20000000-0000-4000-8000-000000000102"

c = httpx.Client(base_url=f"{BASE}/api/v1", headers=H, timeout=600)
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
                "adventure": {"race": "human", "character_class": "fighter"},
            },
            "story": {"title": "Live goblin check"},
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
attempts = [
    "A goblin raider bursts in through the Hearth's back door, knife out. I draw my "
    "longsword and attack it.",
    "I keep swinging my longsword at the goblin.",
    "I strike at the goblin again with my longsword, aiming to finish it.",
]
out = []
for i, attempt in enumerate(attempts, start=1):
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
                    "attempt": attempt,
                }
            },
        },
        headers=P,
    )
    out.append({"turn": i, "status": r.status_code, "seconds": round(time.time() - started, 1)})
time.sleep(3)
chron = c.get(
    "/world/chronicle", params={"world_id": world, "after": 0, "limit": 100}, headers=P
).json()
told = [e for e in chron["entries"] if me in (e.get("participant_ids") or []) and e.get("text")]
rolls = [r["text"] for e in chron["entries"] if e.get("combat") for r in e["combat"]["rolls"]]
party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
print(
    json.dumps(
        {
            "world_id": world,
            "turns": out,
            "scenes": [e["text"][:400] for e in told],
            "tags_in_prose": any("[" in (e["text"] or "") for e in told),
            "rolls": rolls,
            "party": [(m["name"], m["hp_current"], m["hp_max"]) for m in party["members"]],
            "foes": [(f["name"], f["hp_current"], f["hp_max"]) for f in party["foes"]],
        },
        indent=1,
    )
)
