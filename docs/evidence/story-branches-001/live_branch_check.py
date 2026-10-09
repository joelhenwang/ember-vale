"""Live check on the dev API after the merge: play two turns on an existing
combat story, branch from the first kept one, and compare the branch with
the source at that turn (party health, foes, turn, events), then take one
turn on the branch. Usage: python live_branch_check.py <api-base> <api-key> <world_id>"""

from __future__ import annotations

import json
import sys
import time
import uuid

import httpx

BASE, KEY, WORLD = sys.argv[1], sys.argv[2], sys.argv[3]
NIL = "00000000-0000-0000-0000-000000000000"
c = httpx.Client(base_url=f"{BASE}/api/v1", headers={"Authorization": f"Bearer {KEY}"}, timeout=600)


def me_of(world: str) -> str:
    return c.get("/stage2/roles", params={"world_id": world}).json()["character_id"]


def turn(world: str, me: str, index: int, attempt: str) -> int:
    r = c.post(
        "/stage1/advance",
        json={
            "world_id": world,
            "absolute_index": index,
            "player_intents": {
                me: {"family": "interact", "character_id": me, "snapshot_id": NIL, "attempt": attempt}
            },
        },
        headers={"X-Worldsim-Role": "player", "X-Worldsim-Character": me},
    )
    return r.status_code


def look(world: str, me: str) -> dict[str, object]:
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
    view = c.get("/world/presentation", params={"world_id": world}, headers=P).json()
    chron = c.get("/world/chronicle", params={"world_id": world, "after": 0, "limit": 1}, headers=P).json()
    return {
        "turn": view["absolute_index"],
        "events": chron["watermark"],
        "party": [(m["name"], m["hp_current"], m["hp_max"]) for m in party["members"]],
        "foes": [(f["name"], f["hp_current"], f["hp_max"]) for f in party["foes"]],
    }


me = me_of(WORLD)
start = look(WORLD, me)["turn"]
assert isinstance(start, int)
out: dict[str, object] = {"source_before": look(WORLD, me)}
codes = [
    turn(WORLD, me, start + 1, "I strike at the goblin again with my longsword."),
]
time.sleep(4)
out["source_after_kept_turn"] = look(WORLD, me)
codes.append(turn(WORLD, me, start + 2, "I look around the kitchen for the missing flour."))
time.sleep(4)
out["source_now"] = look(WORLD, me)
points = c.get(f"/stories/{WORLD}/branch-points").json()
out["branch_points"] = points
made = c.post(
    f"/stories/{WORLD}/branch",
    json={"absolute_index": start + 1},
    headers={"Idempotency-Key": str(uuid.uuid4())},
)
out["branch_status"] = made.status_code
branch = made.json()
out["branch"] = branch
bworld = branch.get("world_id") or branch.get("story_id")
bme = me_of(bworld)
out["branch_at_start"] = look(bworld, bme)
codes.append(turn(bworld, bme, start + 2, "I step outside into the morning air."))
time.sleep(4)
out["branch_after_turn"] = look(bworld, bme)
out["source_untouched"] = look(WORLD, me) == out["source_now"]
out["turn_codes"] = codes
print(json.dumps(out, indent=1, default=str))
