"""Serve the worktree's API with a scripted storyteller (fake gateway) for the
combat-depth screenshots: every character waits, and the hero's scene at the
Hearth is narrated with combat tags, one script per turn.

Turn 1 brings two goblins (each its own health), the hero strikes Goblin 2,
Goblin 1 strikes back, and three cures spend a level-1 cleric's two slots
(the third fails: no slot left). Later turns keep swinging at "the goblin"
(the first one still standing) until both are down.

Usage: python scripted_storyteller.py <port> [hero name]
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import uvicorn

from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

HERO = sys.argv[2] if len(sys.argv) > 2 else "Wren"

FIGHTS = [
    (
        "Smoke drifts low across the Hearth as the fire gutters.\n"
        "ENCOUNTER[2x goblin]: Two goblins scramble in over the back step, blades out.\n"
        f"ATTACK[mace at Goblin 2]: {HERO} swings at the nearer, smaller one.\n"
        f"ATTACK[mace at the second goblin]: {HERO} swings again.\n"
        f"ATTACK[Goblin 1 at {HERO}]: The other darts in low with its scimitar.\n"
        f"CAST[cure wounds on {HERO}]: {HERO} whispers a prayer over the cut.\n"
        f"CAST[cure wounds on {HERO}]: And again, steadier.\n"
        f"CAST[cure wounds on {HERO}]: {HERO} reaches for the prayer a third time.\n"
        "The kettle rattles on its hook."
    ),
    (
        f"ATTACK[mace at the goblin]: {HERO} presses the goblins back toward the door.\n"
        f"ATTACK[mace at the goblin]: The mace comes round again.\n"
        f"ATTACK[mace at the goblin]: And again.\n"
        f"ATTACK[goblin at {HERO}]: A goblin lunges at {HERO}'s side.\n"
        "Embers skitter across the floorboards."
    ),
]
turn = {"n": 0, "seen": set[str]()}


def route(request: Any) -> str | None:
    system, prompt = request.system or "", request.prompt
    if "You narrate" in system:
        if "D&D PARTY" not in prompt or "takes place at Hearth" not in prompt:
            return None
        event = re.search(r"Event ([0-9a-f-]{36})", prompt)
        key = event.group(1) if event else prompt[:80]
        if key not in turn["seen"]:
            turn["seen"].add(key)
            turn["n"] += 1
        text = FIGHTS[min(turn["n"], len(FIGHTS)) - 1]
        return json.dumps([{"text": text, "cited_fact_keys": [f"dnd-sheet:{HERO.lower()}"]}])
    if "You resolve" in system:
        return json.dumps({"outcome": "success", "effects": [], "rationale": "So it goes."})
    return None


gateway = FakeGateway(profile=FAKE_TEST_PROFILE, default_text="{}")
gateway.route = route
uvicorn.run(
    create_app(Settings(), gateway_factory=lambda: gateway),
    host="127.0.0.1",
    port=int(sys.argv[1]),
    access_log=False,
)
