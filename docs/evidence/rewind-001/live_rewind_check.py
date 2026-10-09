"""Live check on the dev API after the merge: go back one turn on a story,
compare it with the state at that turn, check the path not taken and the
spend, then play on. Usage: python live_rewind_check.py <api-base> <api-key> <world_id>"""

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


def look(world: str) -> dict[str, object]:
    me = me_of(world)
    P = {"X-Worldsim-Role": "player", "X-Worldsim-Character": me}
    party = c.get("/stage1/party", params={"world_id": world}, headers=P).json()
    view = c.get("/world/presentation", params={"world_id": world}, headers=P).json()
    chron = c.get("/world/chronicle", params={"world_id": world, "after": 0, "limit": 1}, headers=P).json()
    return {
        "turn": view["absolute_index"],
        "events": chron["watermark"],
        "party": [(m["name"], m["hp_current"]) for m in party["members"]],
        "foes": [(f["name"], f["hp_current"]) for f in party["foes"]],
    }


def spend(world: str) -> object:
    stories = c.get("/stories").json()["items"]
    return next((s.get("spend_usd") for s in stories if s["story_id"] == world), None)


out: dict[str, object] = {}
points = c.get(f"/stories/{WORLD}/branch-points").json()
out["branch_points"] = points
out["before"] = look(WORLD)
target = sorted(points["turns"])[-2]
rewound = c.post(
    f"/stories/{WORLD}/rewind",
    json={"absolute_index": target},
    headers={"Idempotency-Key": str(uuid.uuid4())},
)
out["rewind_status"] = rewound.status_code
out["rewind"] = rewound.json()
out["after_rewind"] = look(WORLD)
body = rewound.json() if rewound.status_code == 200 else {}
copy_id = body.get("saved_story_id")
if copy_id:
    out["path_not_taken"] = {"title": body.get("saved_title"), **look(copy_id)}
me = me_of(WORLD)
r = c.post(
    "/stage1/advance",
    json={
        "world_id": WORLD,
        "absolute_index": target + 1,
        "player_intents": {
            me: {"family": "interact", "character_id": me, "snapshot_id": NIL,
                 "attempt": "I sheathe my sword and ask Ash about the flour instead."}
        },
    },
    headers={"X-Worldsim-Role": "player", "X-Worldsim-Character": me},
)
time.sleep(4)
out["played_on"] = {"status": r.status_code, **look(WORLD)}
print(json.dumps(out, indent=1, default=str))
