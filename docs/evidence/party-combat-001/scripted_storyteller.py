"""Serve the worktree's API with a scripted storyteller (fake gateway) for
the party-combat screenshots: every character waits, and the hero's scene
is narrated with combat tags, one fight script per turn."""

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
        "ENCOUNTER[orc]: An orc shoulders in through the back door, greataxe already raised.\n"
        f"ATTACK[longsword at orc]: {HERO} steps between it and the hearth and swings.\n"
        f"ATTACK[orc at {HERO}]: The orc brings its axe down.\n"
        f"ATTACK[orc at {HERO}]: It wrenches the blade free and swings again.\n"
        "The kettle rattles on its hook."
    ),
    (
        "RECRUIT[Brann]: dwarf cleric, level 1\n"
        "A broad dwarf in a soot-stained apron hefts a mace from behind the counter. "
        "\"I'm with you,\" Brann growls.\n"
        f"ATTACK[longsword at orc]: {HERO} presses forward, blade high.\n"
        "CAST[sacred flame at orc]: Brann's open palm flares with pale light.\n"
        f"ATTACK[orc at {HERO}]: The orc hisses and slashes again.\n"
        f"CAST[cure wounds on {HERO}]: Brann lays a warm hand on {HERO}'s shoulder."
    ),
    (
        f"ATTACK[longsword at orc]: {HERO} drives the last orc back toward the door.\n"
        "ATTACK[mace at orc]: Brann's mace follows close behind.\n"
        "Quiet settles over the Hearth, broken only by the crackle of the fire."
    ),
]
turn = {"n": 0, "seen": set()}


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
