"""Play a short Adventure session against the dev API, as a player would.

Creates a story where you play Wren (Ash at the Market), then takes the
turns given (or a default mix: look, talk, walk, follow a lead) through
the same endpoints the Adventure screen uses, printing the story as it
unfolds plus rumours and renown. Live model calls cost money.

Usage (from backend/, dev API running on API_PORT):
    uv run python scripts/play_session.py --live [--turns 6]
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[2]
WORLD_PRESET = "20000000-0000-4000-8000-000000000001"
WREN_PRESET = "20000000-0000-4000-8000-000000000101"
ASH_PRESET = "20000000-0000-4000-8000-000000000102"
NIL = str(uuid.UUID(int=0))


def env(name: str, default: str = "") -> str:
    for raw in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        key, _, value = raw.strip().partition("=")
        if key == name:
            return value.strip()
    return default


def first_sentence(text: str) -> str:
    text = " ".join(text.split())
    for mark in (". ", "! ", "? "):
        if mark in text:
            return text.split(mark)[0] + mark.strip()
    return text


class Session:
    def __init__(self, base: str, key: str) -> None:
        self.http = httpx.Client(
            base_url=base, headers={"Authorization": f"Bearer {key}"}, timeout=600
        )
        self.world = ""
        self.me = ""
        self.cursor = 0

    def player(self) -> dict[str, str]:
        return {"X-Worldsim-Role": "player", "X-Worldsim-Character": self.me}

    def create(self) -> None:
        draft = self.http.post(
            "/api/v1/story-drafts",
            json={
                "payload": {
                    "world": {"preset_id": WORLD_PRESET, "preset_revision": 2},
                    "cast": [
                        {
                            "instance_key": "wren",
                            "preset_id": WREN_PRESET,
                            "preset_revision": 1,
                            "name": "Wren",
                            "location_key": "hearth",
                        },
                        {
                            "instance_key": "ash",
                            "preset_id": ASH_PRESET,
                            "preset_revision": 1,
                            "name": "Ash",
                            "location_key": "market",
                        },
                    ],
                    "mode": {"role": "player", "controlled_cast_key": "wren"},
                    "story": {"title": "Play session", "tone": "hopeful mystery"},
                    "ai": {"art_source": "curated"},
                },
                "current_step": "review",
            },
        )
        draft.raise_for_status()
        created = self.http.post(
            "/api/v1/stories",
            json={"draft_id": draft.json()["id"], "expected_draft_version": 1},
            headers={"Idempotency-Key": f"play-{uuid.uuid4().hex[:8]}"},
        )
        created.raise_for_status()
        self.world = created.json()["world_id"]
        grant = self.http.get("/api/v1/stage2/roles", params={"world_id": self.world}).json()
        self.me = grant["character_id"]

    def view(self) -> dict[str, Any]:
        return self.http.get(
            "/api/v1/world/presentation", params={"world_id": self.world}, headers=self.player()
        ).json()

    def suggestions(self) -> list[dict[str, Any]]:
        return self.http.get(
            "/api/v1/stage1/suggestions", params={"character_id": self.me}, headers=self.player()
        ).json()

    def turn(self, intent: dict[str, Any]) -> float:
        index = self.view()["absolute_index"] + 1
        started = time.monotonic()
        response = self.http.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": self.world,
                "absolute_index": index,
                "player_intents": {
                    self.me: {**intent, "character_id": self.me, "snapshot_id": NIL}
                },
            },
            headers=self.player(),
        )
        response.raise_for_status()
        return time.monotonic() - started

    def told(self) -> list[str]:
        page = self.http.get(
            "/api/v1/world/chronicle",
            params={"world_id": self.world, "after": self.cursor, "limit": 100},
            headers=self.player(),
        ).json()
        self.cursor = page["next_after"]
        lines: list[str] = []
        for entry in page.get("entries", []):
            if entry["event_type"] in ("world_seeded", "world_ticked"):
                continue
            mine = self.me in (entry.get("participant_ids") or [])
            text = entry.get("text") or entry.get("title") or ""
            lines.append(
                ("  " if mine else "  (elsewhere) ") + (text if mine else first_sentence(text))
            )
        return lines


def plan(session: Session, number: int) -> tuple[str, dict[str, Any]]:
    """The next action: what a curious new player tends to try."""
    view = session.view()
    me = next(c for c in view["cast"] if c["character_id"] == session.me)
    near = [
        c
        for c in view["cast"]
        if c["location_id"] == me["location_id"] and c["character_id"] != session.me
    ]
    offered = session.suggestions()
    rumours = view.get("rumours") or []
    if number == 0:
        return "Look around", {"family": "observe", "focus": "surroundings"}
    take = next((s for s in offered if s["family"] == "take"), None)
    if take:
        return take["title"], {"family": "take", "item_instance_id": take["item_instance_id"]}
    if near and number % 2 == 1:
        topic = (
            f'"Have you heard anything about {rumours[0]["title"]}?"'
            if rumours
            else '"Good morning! What is happening around here today?"'
        )
        return f"Say to {near[0]['name']}: {topic}", {
            "family": "communicate",
            "target_character_id": near[0]["character_id"],
            "topic": topic,
        }
    if rumours:
        return f"Look into {rumours[0]['title']}", {
            "family": "interact",
            "attempt": f"look into {rumours[0]['title']}",
        }
    move = next((s for s in offered if s["family"] == "move"), None)
    if move:
        return move["title"], {
            "family": "move",
            "destination_location_id": move["destination_location_id"],
        }
    return "Wait", {"family": "wait"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="required: spends real credit")
    parser.add_argument("--turns", type=int, default=6)
    args = parser.parse_args()
    if not args.live:
        print("refusing: pass --live (this calls the live model)", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    port = env("API_PORT", "8101")
    session = Session(f"http://localhost:{port}", env("WORLDSIM_SECURITY__API_KEY"))
    session.create()
    print(f"story {session.world} — you are Wren")
    session.told()
    for number in range(args.turns):
        label, intent = plan(session, number)
        seconds = session.turn(intent)
        view = session.view()
        print(f"\n> {label}   [{seconds:.1f} s, {view['phase']}]")
        for line in session.told():
            print(line)
        for rumour in view.get("rumours") or []:
            print(f"  ~ rumour: {rumour['title']}")
        for done in view.get("settled") or []:
            print(f"  ✓ settled: {done['title']} — {done['purpose']}")
    journey = session.view().get("journey") or {}
    print(
        f"\nrenown {journey.get('renown')} · {journey.get('title')} "
        f"(places {journey.get('places')}, people {journey.get('people')}, "
        f"deeds {journey.get('deeds')}, settled {journey.get('settled')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
