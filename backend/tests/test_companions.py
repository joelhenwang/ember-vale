"""Companions join when they say yes, and fight beside the party (companions-001)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from test_combat_depth_2 import _goblins, _rng, _wren
from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.domain.rules.dnd import HitPoints, Sheet, load_data
from worldsim.domain.rules.dnd.combat_resolve import resolve_narration_tags
from worldsim.domain.rules.dnd.deeds import Deed
from worldsim.domain.rules.dnd.invites import accepts, companion_description, is_invitation
from worldsim.infrastructure.model_gateway.fake import FakeGateway

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")


def _ash(hp: int = 12) -> Sheet:
    return Sheet(
        name="Ash",
        character_class="fighter",
        stats={"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10},
        hp=HitPoints(current=hp, max=12),
        weapons=["handaxe"],
    )


def test_an_invitation_and_a_plain_yes_are_read() -> None:
    assert is_invitation("Wren says to Ash: Will you join me as my companion?")
    assert is_invitation("Come with me, Ash, and fight at my side.")
    assert not is_invitation("Wren says to Ash: how is the flour?")
    assert accepts("Yes, I will come with you.")
    assert accepts("Count me in, Wren.")
    assert not accepts("I'll consider your offer, but I need to think on it.")
    assert not accepts("Yes, but first I must find the flour.")
    assert not accepts("No. My place is at the bakery.")
    assert companion_description("A wandering elf archer with sharp eyes", DATA) == "elf ranger"
    assert companion_description("A baker with flour on her apron", DATA) == "human fighter"


def test_a_companion_here_fights_beside_the_hero() -> None:
    report = resolve_narration_tags(
        "Steel rings.",
        [_wren(), _ash()],
        DATA,
        _rng(0.5),
        live=_goblins(7, 7),
        fighting=["goblin-1", "goblin-2"],
        deeds=[Deed(key="wren", text="I attack the second goblin")],
        chooses={"wren"},
        strike_back=True,
        present={"wren", "ash"},
    )
    swings = [
        (o.actor, o.target) for o in report.outcomes if o.kind == "attack" and not o.actor_foe
    ]
    assert ("Ash", "Goblin 1") in swings and ("Wren", "Goblin 2") in swings
    assert report.helped == 1
    # Tagged by the storyteller, away from the scene, or down: no extra blow.
    for text, present, ash in (
        ("ATTACK[handaxe at goblin]: Ash hurls the axe.", {"wren", "ash"}, _ash()),
        ("Steel rings.", {"wren"}, _ash()),
        ("Steel rings.", {"wren", "ash"}, _ash(hp=0)),
    ):
        again = resolve_narration_tags(
            text,
            [_wren(), ash],
            DATA,
            _rng(0.5),
            live=_goblins(30, 30),
            fighting=["goblin-1", "goblin-2"],
            chooses={"wren"},
            strike_back=True,
            present=present,
        )
        assert again.helped == 0, text


def test_asked_to_join_and_saying_yes_makes_a_linked_companion(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "join-story", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ash = next(c["character_id"] for c in cast if c["name"] == "Ash")
    asked: list[str] = []

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            return None
        if "You react" in system:
            if "join their party" in prompt:
                asked.append(prompt)
                return json.dumps(
                    {
                        "family": "communicate",
                        "character_id": ash,
                        "snapshot_id": ash,
                        "target_character_id": wren,
                        "topic": "Yes, I will come with you.",
                    }
                )
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You decide" in system:
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Agreed."})
        return None

    gateway.route = route
    moved = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": 1,
            "player_intents": {
                wren: {
                    "family": "communicate",
                    "character_id": wren,
                    "snapshot_id": NIL_SNAPSHOT,
                    "target_character_id": ash,
                    "topic": "Ash, will you join me as my companion on the road?",
                }
            },
        },
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert asked, "Ash was never told the invitation is a real choice"
    party = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    members = {m["name"]: m for m in party["members"]}
    assert set(members) == {"Wren", "Ash"}
    assert members["Ash"]["character_id"] == ash and members["Ash"]["level"] == 1


def test_two_fighters_with_longswords_each_swing_their_own() -> None:
    ash = _ash()
    ash.weapons = ["longsword"]
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]: Ash lunges at the first goblin.",
        [ash, _wren()],
        DATA,
        _rng(0.5),
        live=_goblins(30, 30),
        fighting=["goblin-1", "goblin-2"],
        deeds=[Deed(key="wren", text="I attack the second goblin with my longsword")],
        chooses={"wren"},
        strike_back=True,
        present={"wren", "ash"},
    )
    swings = [
        (o.actor, o.target) for o in report.outcomes if o.kind == "attack" and not o.actor_foe
    ]
    assert ("Ash", "Goblin 1") in swings and ("Wren", "Goblin 2") in swings
    assert report.deeds == 1 and report.helped == 0


def test_companions_are_beside_the_hero_only_where_the_hero_is() -> None:
    from uuid import uuid4

    from worldsim.domain.party import PartyMember, present_keys

    world = uuid4()
    wren_id, ash_id = uuid4(), uuid4()

    def member(name: str, character: UUID | None) -> PartyMember:
        return PartyMember(
            id=uuid4(),
            world_id=world,
            name=name,
            name_key=name.lower(),
            character_id=character,
            sheet=_ash(),
        )

    roster = [member("Wren", wren_id), member("Ash", ash_id), member("Lyra", None)]
    hearth = {str(wren_id): "hearth", str(ash_id): "hearth"}
    # Ash waits in a scene of their own at the same place: still beside Wren.
    assert present_keys(roster, {"wren"}, {str(wren_id)}, hearth) == {"wren", "ash", "lyra"}
    apart = {str(wren_id): "hearth", str(ash_id): "market"}
    assert present_keys(roster, {"wren"}, {str(wren_id)}, apart) == {"wren", "lyra"}
    # Ash's own scene without Wren: nobody fights beside anyone there.
    assert present_keys(roster, {"wren"}, {str(ash_id)}, hearth) == set()
