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

from worldsim.domain.rules.dnd import HitPoints, MonsterState, Sheet, load_data
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


def test_a_spar_and_a_fight_in_one_scene_both_keep_their_dice(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "spar-and-fight", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ash = next(c["character_id"] for c in cast if c["name"] == "Ash")
    turn = {"n": 0}

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if turn["n"] == 2 and "Hearth" in prompt:
                text = (
                    "ENCOUNTER[goblin]: A goblin bursts in.\n"
                    "ATTACK[longsword at goblin]: Wren swings at it."
                )
                return json.dumps([{"text": text, "cited_fact_keys": ["dnd-sheet:wren"]}])
            return None
        if "You react" in system:
            if "join their party" in prompt:
                reply = {
                    "family": "communicate",
                    "target_character_id": wren,
                    "topic": "Yes, I will come.",
                }
                return json.dumps({**reply, "character_id": ash, "snapshot_id": ash})
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You decide" in system:
            if turn["n"] == 2:
                spar = {"family": "spar", "target_character_id": wren, "weapon": "longsword"}
                return json.dumps({**spar, "character_id": ash, "snapshot_id": ash})
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Fine."})
        return None

    gateway.route = route
    for index, intent in (
        (
            1,
            {
                "family": "communicate",
                "target_character_id": ash,
                "topic": "Will you join me as my companion?",
            },
        ),
        (2, {"family": "wait"}),
    ):
        turn["n"] = index
        moved = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(world_id),
                "absolute_index": index,
                "player_intents": {
                    wren: {**intent, "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
                },
            },
            headers=headers,
        )
        assert moved.status_code == 200, moved.text
    entries = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 80},
        headers=headers,
    ).json()["entries"]
    kinds = [r["kind"] for e in entries if e["combat"] for r in e["combat"]["rolls"]]
    assert "spar" in kinds and "encounter" in kinds, kinds


def test_a_companion_hears_the_party_and_the_fight() -> None:
    from uuid import uuid4

    from worldsim.domain.party import Monster, companion_note

    quiet = companion_note("Wren", [])
    assert quiet.startswith("You travel with Wren's party as their companion")
    assert "fight is on" not in quiet

    def goblin(n: int, hp: int) -> Monster:
        return Monster(
            id=uuid4(),
            world_id=uuid4(),
            name_key=f"goblin-{n}",
            name=f"Goblin {n}",
            hp_current=hp,
            hp_max=7,
            ac=15,
        )

    fight = companion_note("Wren", [goblin(1, 0), goblin(2, 3)])
    assert "A fight is on with Goblin 2 (badly wounded)" in fight
    assert "Goblin 1" not in fight and "Never spar" in fight


def test_a_companion_takes_the_most_wounded_foe_or_the_one_they_are_told() -> None:
    def ash_swings(orders: dict[str, str] | None) -> list[str | None]:
        report = resolve_narration_tags(
            "Steel rings.",
            [_wren(), _ash()],
            DATA,
            _rng(0.0),
            live=_goblins(7, 2, 7),
            fighting=["goblin-1", "goblin-2", "goblin-3"],
            chooses={"wren"},
            strike_back=True,
            present={"wren", "ash"},
            orders=orders,
        )
        return [o.target for o in report.outcomes if o.actor == "Ash"]

    assert ash_swings(None) == ["Goblin 2"]
    assert ash_swings({"ash": "Ash, take the third goblin!"}) == ["Goblin 3"]
    assert ash_swings({"ash": "Ash, watch the door."}) == ["Goblin 2"]


def test_a_companion_follows_the_hero_and_keeps_the_party_in_mind(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "follow-story", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ash = next(c["character_id"] for c in cast if c["name"] == "Ash")
    places = {
        p["name"]: p["id"]
        for p in client.get(
            "/api/v1/stage2/map", params={"world_id": str(world_id)}, headers=headers
        ).json()["places"]
    }
    noted: list[str] = []

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            return None
        if "travel with Wren's party" in prompt:
            noted.append(prompt)
        if "You react" in system and "join their party" in prompt:
            reply = {
                "family": "communicate",
                "target_character_id": wren,
                "topic": "Yes, I will come.",
            }
            return json.dumps({**reply, "character_id": ash, "snapshot_id": ash})
        if "You decide" in system:
            # Ash would rather go to the market alone: a companion stays.
            alone = {"family": "move", "destination_location_id": places["Market"]}
            return json.dumps({**alone, "character_id": ash, "snapshot_id": ash})
        if "You react" in system:
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Fine."})
        return None

    gateway.route = route
    for index, intent in (
        (
            1,
            {
                "family": "communicate",
                "target_character_id": ash,
                "topic": "Will you join me as my companion?",
            },
        ),
        (2, {"family": "wait"}),
        (3, {"family": "move", "destination_location_id": places["Market"]}),
    ):
        moved = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(world_id),
                "absolute_index": index,
                "player_intents": {
                    wren: {**intent, "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
                },
            },
            headers=headers,
        )
        assert moved.status_code == 200, moved.text
        if index == 2:
            here = {
                c["name"]: c.get("location_id")
                for c in client.get(
                    "/api/v1/world/presentation",
                    params={"world_id": str(world_id)},
                    headers=headers,
                ).json()["cast"]
            }
            assert here["Ash"] == here["Wren"] != places["Market"], here
    assert noted, "Ash never heard that they travel with Wren's party"
    where = {
        c["name"]: c.get("location_id")
        for c in client.get(
            "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
        ).json()["cast"]
    }
    assert where["Ash"] == where["Wren"] == places["Market"], where


def test_a_companions_spar_while_a_fight_is_on_is_a_blow(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    from test_combat_depth_2 import _families

    client, gateway = wired
    created = _create(client, FIGHTER, "no-spar-mid-fight", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ash = next(c["character_id"] for c in cast if c["name"] == "Ash")
    turn = {"n": 0}

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if turn["n"] == 2 and "Hearth" in prompt:
                # A zombie: hardy but weak-handed, so the fight is still on next turn.
                text = "ENCOUNTER[zombie]: A zombie shambles in, moaning."
                return json.dumps([{"text": text, "cited_fact_keys": ["dnd-sheet:wren"]}])
            return None
        if "You react" in system and "join their party" in prompt:
            reply = {
                "family": "communicate",
                "target_character_id": wren,
                "topic": "Yes, I will come.",
            }
            return json.dumps({**reply, "character_id": ash, "snapshot_id": ash})
        if "You decide" in system and turn["n"] == 3:
            spar = {"family": "spar", "target_character_id": wren, "weapon": "longsword"}
            return json.dumps({**spar, "character_id": ash, "snapshot_id": ash})
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Fine."})
        return None

    gateway.route = route
    for index, intent in (
        (
            1,
            {
                "family": "communicate",
                "target_character_id": ash,
                "topic": "Will you join me as my companion?",
            },
        ),
        (2, {"family": "wait"}),
        (3, {"family": "wait"}),
    ):
        turn["n"] = index
        moved = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(world_id),
                "absolute_index": index,
                "player_intents": {
                    wren: {**intent, "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
                },
            },
            headers=headers,
        )
        assert moved.status_code == 200, moved.text
        if index == 2:
            _heal_all(world_id)
    entries = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 80},
        headers=headers,
    ).json()["entries"]
    # A fight began (its goblin may have fallen since: Ash fights now).
    assert any(
        r["kind"] == "encounter" for e in entries if e["combat"] for r in e["combat"]["rolls"]
    )
    # A companion's spar mid-fight is their blow at a foe instead.
    families = _families(world_id)
    assert "spar" not in families and "interact" in families


def test_the_prose_count_and_last_turns_foes_make_the_fight() -> None:
    larger = resolve_narration_tags(
        "ENCOUNTER[goblin]: Two goblins burst in through the door.",
        [_wren()],
        DATA,
        _rng(0.0),
    )
    assert larger.outcomes[0].target == "Goblin 1, Goblin 2"
    # Goblins seen last turn, attacked this turn with no fight on yet.
    later = resolve_narration_tags(
        "Wren steps forward, blade raised.",
        [_wren()],
        DATA,
        _rng(0.5),
        deeds=[Deed(key="wren", text="I attack the second goblin")],
        recent="Two goblins burst in through the Hearth's back door.",
    )
    kinds = [(o.kind, o.target) for o in later.outcomes]
    assert kinds[0] == ("encounter", "Goblin 1, Goblin 2")
    assert ("attack", "Goblin 2") in kinds


def test_a_companions_own_blow_in_their_words() -> None:
    from worldsim.domain.rules.dnd.invites import companion_attack

    assert companion_attack(_ash(), "Goblin 2", DATA) == "I attack Goblin 2 with my handaxe"
    assert companion_attack(_ash(hp=0), "Goblin 2", DATA) is None
    sage = Sheet(name="Lyra", character_class="wizard", spells=["fire-bolt"], weapons=[])
    assert companion_attack(sage, "Goblin 1", DATA) == "I cast fire bolt at Goblin 1"


def test_a_waiting_companion_fights_while_a_fight_is_on(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    from test_combat_depth_2 import _families

    client, gateway = wired
    created = _create(client, FIGHTER, "companion-fights", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ash = next(c["character_id"] for c in cast if c["name"] == "Ash")
    turn = {"n": 0}

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if turn["n"] == 2 and "Hearth" in prompt:
                text = "ENCOUNTER[zombie]: A zombie lurches through the door."
                return json.dumps([{"text": text, "cited_fact_keys": ["dnd-sheet:wren"]}])
            return None
        if "You react" in system and "join their party" in prompt:
            reply = {
                "family": "communicate",
                "target_character_id": wren,
                "topic": "Yes, I will come.",
            }
            return json.dumps({**reply, "character_id": ash, "snapshot_id": ash})
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Fine."})
        return None

    gateway.route = route
    for index, intent in (
        (
            1,
            {
                "family": "communicate",
                "target_character_id": ash,
                "topic": "Will you join me as my companion?",
            },
        ),
        (2, {"family": "wait"}),
        (3, {"family": "wait"}),
    ):
        turn["n"] = index
        moved = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(world_id),
                "absolute_index": index,
                "player_intents": {
                    wren: {**intent, "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
                },
            },
            headers=headers,
        )
        assert moved.status_code == 200, moved.text
        if index == 2:
            _heal_all(world_id)
    assert "interact" in _families(world_id)
    entries = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 80},
        headers=headers,
    ).json()["entries"]
    ash_blows = [
        r
        for e in entries
        if e["combat"]
        for r in e["combat"]["rolls"]
        if r["kind"] == "attack" and r.get("actor") == "Ash"
    ]
    assert ash_blows and all(r["target"].startswith("Zombie") for r in ash_blows)


def _heal_all(world_id: UUID) -> None:
    """Everyone back to full: the next turn starts with the fight still on
    and every companion standing, whatever the dice did this one."""
    import asyncio

    from worldsim.infrastructure.db.engine import create_engine
    from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
    from worldsim.infrastructure.settings import Settings

    async def inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                for m in await uow.monsters.list_for_world(world_id):
                    await uow.monsters.save_hp(m.id, m.hp_max, m.version)
                for member in await uow.party.list_for_world(world_id):
                    sheet = member.sheet.model_copy(deep=True)
                    if sheet.hp is not None:
                        sheet.hp = HitPoints(current=sheet.hp.max, max=sheet.hp.max)
                    await uow.party.save_sheet(member.id, sheet, member.version)
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(inner())


def test_an_order_steers_a_companions_own_blow_and_the_fallen_are_not_struck() -> None:
    report = resolve_narration_tags(
        "Steel rings.",
        [_wren(), _ash()],
        DATA,
        _rng(0.5),
        live=[
            *_goblins(0, 0),
            MonsterState(key="goblin-3", name="Goblin 3", hp_current=30, hp_max=30, ac=15),
        ],
        fighting=["goblin-1", "goblin-2", "goblin-3"],
        deeds=[
            Deed(key="wren", text="I strike at the second goblin"),
            Deed(key="ash", text="I attack Goblin 1 with my handaxe"),
        ],
        chooses={"wren"},
        strike_back=True,
        present={"wren", "ash"},
        orders={"ash": "Ash, take the third goblin!"},
    )
    swings = {o.actor: o.target for o in report.outcomes if o.kind == "attack" and not o.actor_foe}
    # Goblin 2 already fell: Wren's blow goes to the one still standing.
    assert swings == {"Wren": "Goblin 3", "Ash": "Goblin 3"}


def test_orders_last_the_fight_they_were_given_in() -> None:
    from worldsim.domain.party import orders_record, stored_orders

    kept = orders_record(
        {"ash": "Ash, take the third goblin!"}, ["goblin-1", "goblin-3", "goblin-3"]
    )
    assert kept == {
        "orders": {"ash": "Ash, take the third goblin!"},
        "foes": ["goblin-1", "goblin-3"],
    }
    assert stored_orders(kept, ["goblin-3"]) == {"ash": "Ash, take the third goblin!"}
    # A new fight (no foe in common), or nothing kept: no order.
    assert stored_orders(kept, ["wolf"]) == {}
    assert stored_orders(None, ["goblin-3"]) == {}
    assert stored_orders({"orders": "junk", "foes": ["goblin-3"]}, ["goblin-3"]) == {}


def test_a_kind_slain_long_ago_can_be_met_again_and_odd_targets_roll_nothing() -> None:
    dead = [MonsterState(key="goblin", name="Goblin", hp_current=0, hp_max=7, ac=15)]
    words = [Deed(key="wren", text="I attack the goblin")]
    prose = "A goblin creeps out from behind the market stalls."
    again = resolve_narration_tags(
        prose, [_wren()], DATA, _rng(0.5), live=dead, deeds=words, slain_lately=set()
    )
    assert [o.kind for o in again.outcomes][:2] == ["encounter", "attack"]
    lately = resolve_narration_tags(
        prose, [_wren()], DATA, _rng(0.5), live=dead, deeds=words, slain_lately={"goblin"}
    )
    assert lately.outcomes == []
    odd = resolve_narration_tags(
        "ATTACK[longsword at enemy]: Wren swings at the shadows.", [_wren()], DATA, _rng(0.5)
    )
    assert odd.outcomes == [] and odd.unresolved == ["ATTACK[longsword at enemy]"]


def test_the_storyteller_hears_the_party_is_looking_for_a_fight() -> None:
    from worldsim.domain.party import seeking_line

    assert seeking_line([]) is None
    line = seeking_line(["Wren tries to attack the first goblin I see"])
    assert line is not None and "looking for a fight" in line and "ENCOUNTER[" in line
