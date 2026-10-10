"""Combat stories: the hero's sheet at creation, rolls under their scene, foes.

A player story can opt into fights in the New Story wizard; the hero's 5e
sheet is made in the same transaction as the story. The storyteller's tags
then roll through the existing engine, and the reads show the rolls in
parts (chronicle), the prose without tags (narration) and the party with
the current foes (roster).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.domain.rules.dnd import strip_combat_tags
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"
WREN_PRESET_ID = "20000000-0000-4000-8000-000000000101"
ASH_PRESET_ID = "20000000-0000-4000-8000-000000000102"

NIL_SNAPSHOT = "00000000-0000-0000-0000-000000000000"
FIGHT = (
    "ENCOUNTER[goblin]: A goblin bursts from behind the hearth stones.\n"
    "ATTACK[longsword at goblin]: Wren swings her blade at it.\n"
    "ATTACK[goblin at Wren]: The goblin slashes back.\n"
    "Smoke curls between them."
)


@pytest.fixture
def wired(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _draft(client: ApiClient, mode: dict[str, Any], ash_at: str = "market") -> str:
    created = client.post(
        "/api/v1/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": WORLD_PRESET_ID, "preset_revision": 2},
                "cast": [
                    {
                        "instance_key": "cast-wren",
                        "preset_id": WREN_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Wren",
                        "location_key": "hearth",
                    },
                    {
                        "instance_key": "cast-ash",
                        "preset_id": ASH_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Ash",
                        "location_key": ash_at,
                    },
                ],
                "mode": mode,
                "story": {"title": "Smoke at the Hearth"},
                "ai": {"art_source": "curated"},
            },
            "current_step": "review",
        },
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _create(client: ApiClient, mode: dict[str, Any], key: str, ash_at: str = "market") -> Any:
    return client.post(
        "/api/v1/stories",
        json={"draft_id": _draft(client, mode, ash_at), "expected_draft_version": 1},
        headers={"Idempotency-Key": key},
    )


FIGHTER = {
    "role": "player",
    "controlled_cast_key": "cast-wren",
    "adventure": {"race": "human", "character_class": "fighter"},
}


def _pools(world_id: UUID) -> dict[str, int]:
    async def inner() -> dict[str, int]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return {
                    m.name_key: m.hp_current for m in await uow.monsters.list_for_world(world_id)
                }
        finally:
            await engine.dispose()

    return asyncio.run(inner())


def test_strip_combat_tags_keeps_the_prose() -> None:
    assert strip_combat_tags(FIGHT) == (
        "A goblin bursts from behind the hearth stones.\n"
        "Wren swings her blade at it.\n"
        "The goblin slashes back.\n"
        "Smoke curls between them."
    )
    assert strip_combat_tags("RECRUIT[Lyra]: elf ranger, level 3\nLyra nods.") == "Lyra nods."
    assert strip_combat_tags("CONDITION[poisoned on Wren]") == ""
    assert strip_combat_tags("Wren [quietly] waits.") == "Wren [quietly] waits."


def test_a_played_story_fights_with_a_known_hero(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, _ = wired
    watcher = _create(
        client,
        {"role": "watcher", "adventure": {"race": "human", "character_class": "fighter"}},
        "fight-watcher",
    )
    # A watched party's callings come from its cast (test_watched_party).
    assert watcher.status_code == 422, watcher.text
    assert "callings come from the cast" in watcher.text
    unknown = _create(
        client,
        {**FIGHTER, "adventure": {"race": "centaur", "character_class": "fighter"}},
        "fight-centaur",
    )
    assert unknown.status_code == 422, unknown.text
    narrative = _create(client, {"role": "player", "controlled_cast_key": "cast-wren"}, "plain")
    assert narrative.status_code == 200, narrative.text
    roster = client.get(
        "/api/v1/stage1/party", params={"world_id": narrative.json()["world_id"]}
    ).json()
    assert roster["members"] == [] and roster["foes"] == []


def test_combat_story_rolls_show_under_their_scene(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "fight-story")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}

    roster = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    (hero,) = roster["members"]
    assert (hero["name"], hero["race"], hero["character_class"], hero["level"]) == (
        "Wren",
        "human",
        "fighter",
        1,
    )
    assert hero["character_id"] == wren
    assert hero["weapons"] == ["Longsword", "Handaxe"]
    assert hero["armor_class"] >= 16 and hero["hp_current"] == hero["hp_max"] > 0
    assert hero["spell_slots"] == [] and roster["foes"] == []

    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ids = {c["name"]: c["character_id"] for c in cast}

    told: list[str] = []

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if "Hearth" not in prompt:
                return None
            told.append(prompt)
            return json.dumps(
                [{"text": FIGHT, "cited_fact_keys": ["attempt:wait", "dnd-sheet:wren"]}]
            )
        who = ids["Wren"] if "Wren" in prompt else ids["Ash"]
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Waiting."})
        return None

    gateway.route = route
    advanced = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": 1,
            "player_intents": {
                wren: {"family": "wait", "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
            },
        },
        headers=headers,
    )
    assert advanced.status_code == 200, advanced.text

    chronicle = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 50},
        headers=headers,
    ).json()
    fights = [e for e in chronicle["entries"] if e["combat"]]
    assert len(fights) == 1, chronicle["entries"]
    log = fights[0]["combat"]
    scene = next(e for e in chronicle["entries"] if e["event_id"] == log["scene_event_id"])
    assert scene["scene_id"] is not None
    assert "[" not in (scene["text"] or "") and "Wren swings her blade" in scene["text"]

    # The story room (Director and God seats) reads the timeline and the
    # party: the same rolls under the same scene, the same roster.
    timeline = client.get(
        "/api/v1/stage2/timeline",
        params={"world_id": str(world_id), "after": 0, "limit": 50},
        headers=headers,
    ).json()
    (logged,) = [e["combat"] for e in timeline["entries"] if e["combat"]]
    assert logged == log
    for seat in ("director", "deity", "watcher"):
        seen = client.get(
            "/api/v1/stage1/party",
            params={"world_id": str(world_id)},
            headers={"X-Worldsim-Role": seat},
        )
        assert seen.status_code == 200, seen.text
        assert [m["name"] for m in seen.json()["members"]] == ["Wren"]

    # Experience rows follow a fallen foe (combat-depth-001); the dice decide
    # whether the opening blow fells the goblin, so they are checked apart.
    fight = [r for r in log["rolls"] if r["kind"] not in ("xp", "level", "loot")]
    kinds = [(r["kind"], r.get("actor"), r.get("target")) for r in fight]
    strike = fight[1]
    felled = strike.get("hp_after") == 0  # a fallen goblin does not strike back
    assert any(r["kind"] == "xp" for r in log["rolls"]) == felled
    assert kinds == [
        ("encounter", None, "Goblin"),
        ("attack", "Wren", "Goblin"),
        *([] if felled else [("attack", "Goblin", "Wren")]),
    ]
    assert strike["using"] == "Longsword" and strike["target_foe"] is True
    assert strike["result"] in ("hit", "miss", "crit") and strike["ac"] == 15
    assert strike["roll"] - strike["natural"] == 5  # +3 Str, +2 proficiency
    back = {} if felled else fight[2]
    if back:
        assert back["actor_foe"] is True and back["using"] == "Scimitar"
        assert back["ac"] == hero["armor_class"]

    narration = client.get(
        f"/api/v1/stage1/scenes/{scene['scene_id']}/narration", headers=headers
    ).json()
    assert narration and all("[" not in beat["text"] for beat in narration)

    after = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    goblin_hp = _pools(world_id)["goblin"]
    if back.get("result") in ("hit", "crit"):
        assert after["members"][0]["hp_current"] == back["hp_after"] < hero["hp_max"]
    if goblin_hp > 0:
        assert [(f["key"], f["hp_current"]) for f in after["foes"]] == [("goblin", goblin_hp)]
        assert after["fight_index"] == 1
    else:
        assert after["foes"] == []

    # The next turn's storyteller hears the fight that is on, in words.
    assert all("A fight is on" not in prompt for prompt in told)
    again = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": 2,
            "player_intents": {
                wren: {"family": "wait", "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
            },
        },
        headers=headers,
    )
    assert again.status_code == 200, again.text
    on = "A fight is on with: Goblin" in told[-1]
    assert on == (goblin_hp > 0)


def test_a_fight_that_is_on_is_told_in_words() -> None:
    from worldsim.domain.ids import new_monster_id, new_world_id
    from worldsim.domain.party import Monster, fight_keys, foes_line, foes_on

    world = new_world_id()

    def goblin(hp: int) -> Monster:
        return Monster(
            id=new_monster_id(),
            world_id=world,
            name_key="goblin",
            name="Goblin",
            hp_current=hp,
            hp_max=7,
            ac=15,
        )

    keys = fight_keys({"foes": '["goblin", "wolf"]'})
    assert keys == ["goblin", "wolf"] and fight_keys({"foes": "nope"}) == []
    assert [f.hp_current for f in foes_on(3, 5, keys, [goblin(3)])] == [3]
    assert foes_on(3, 6, keys, [goblin(3)]) == []  # three turns on: over
    assert foes_on(3, 4, keys, [goblin(0)]) == []  # nobody standing
    line = foes_line([goblin(3)])
    assert line.startswith("A fight is on with: Goblin (badly wounded).")
    assert not any(ch.isdigit() for ch in line)


CLERIC = {
    "role": "player",
    "controlled_cast_key": "cast-wren",
    "adventure": {"race": "human", "character_class": "cleric"},
}


def _set_state(world_id: UUID, *, hero_xp: int, pools: dict[str, int]) -> None:
    """Put the story where the next turn's dice can only finish the job."""

    async def inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                (hero,) = await uow.party.list_for_world(world_id)
                sheet = hero.sheet.model_copy(deep=True)
                sheet.xp = hero_xp
                # The goblins strike back on their own now (combat-depth-002):
                # stand the hero up so this turn's blows are theirs to make.
                if sheet.hp is not None:
                    sheet.hp = sheet.hp.model_copy(update={"current": sheet.hp.max})
                await uow.party.save_sheet(hero.id, sheet, hero.version)
                for monster in await uow.monsters.list_for_world(world_id):
                    if monster.name_key in pools:
                        await uow.monsters.save_hp(
                            monster.id, pools[monster.name_key], monster.version
                        )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(inner())


def test_group_foes_xp_levels_and_spent_slots(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    """combat-depth-001 end to end: Goblin 1 and Goblin 2 with their own
    health, a cleric's slots spent (the third cure fails plainly), and the
    goblin that falls gives XP that levels the hero up."""
    client, gateway = wired
    created = _create(client, CLERIC, "group-fight")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    roster = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    (hero,) = roster["members"]
    assert hero["spell_slots"] == [2] and hero["spell_slots_left"] == [2]
    assert (hero["xp"], hero["xp_level_start"], hero["xp_next_level"]) == (0, 0, 300)
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ids = {c["name"]: c["character_id"] for c in cast}

    scripts = [
        "ENCOUNTER[2x goblin]: Two goblins spill out of the smoke.\n"
        + "CAST[cure wounds on Wren]: Wren whispers a prayer.\n" * 3,
        "ATTACK[mace at Goblin 2]: Wren swings at the second goblin.\n" * 20,
    ]

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if "Hearth" not in prompt:
                return None
            return json.dumps(
                [{"text": scripts[0], "cited_fact_keys": ["attempt:wait", "dnd-sheet:wren"]}]
            )
        who = ids["Wren"] if "Wren" in prompt else ids["Ash"]
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Waiting."})
        return None

    gateway.route = route

    def advance(index: int) -> list[dict[str, Any]]:
        moved = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(world_id),
                "absolute_index": index,
                "player_intents": {
                    wren: {"family": "wait", "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
                },
            },
            headers=headers,
        )
        assert moved.status_code == 200, moved.text
        chronicle = client.get(
            "/api/v1/world/chronicle",
            params={"world_id": str(world_id), "after": 0, "limit": 80},
            headers=headers,
        ).json()
        # Ash, waiting at the market away from the fight, is told without
        # the party's sheets (they once leaked into fallback narration).
        assert all("D&D" not in (e["text"] or "") for e in chronicle["entries"])
        fights = [e for e in chronicle["entries"] if e["combat"]]
        return fights[-1]["combat"]["rolls"]

    first = advance(1)
    assert first[0]["kind"] == "encounter" and first[0]["target"] == "Goblin 1, Goblin 2"
    cures = [r for r in first if r["kind"] == "cast"]
    assert [r.get("result") for r in cures] == ["healed", "healed", "no-slot"]
    assert cures[-1]["text"] == "Wren has no 1st-level spell slot left: Cure Wounds fails."
    assert _pools(world_id) == {"goblin-1": 7, "goblin-2": 7}
    party = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    assert party["members"][0]["spell_slots_left"] == [0]
    assert [(f["key"], f["name"], f["hp_current"]) for f in party["foes"]] == [
        ("goblin-1", "Goblin 1", 7),
        ("goblin-2", "Goblin 2", 7),
    ]

    _set_state(world_id, hero_xp=290, pools={"goblin-2": 1})
    scripts.pop(0)
    second = advance(2)
    # Wren's blows go at Goblin 2 until it falls; the rest re-aim at the foe
    # still standing (companions-002), so Goblin 1 may fall too.
    blows = [r for r in second if r["kind"] == "attack" and not r.get("actor_foe")]
    assert blows[0]["target"] == "Goblin 2"
    assert {r["target"] for r in blows} <= {"Goblin 1", "Goblin 2"}
    xp = next(r for r in second if r["kind"] == "xp")
    # Story pacing: 4x the 5e XP (WORLDSIM_APP__XP_SCALE, long-adventure-001).
    assert xp["target"].startswith("Goblin 2") and xp["amount"] in (200, 400)
    level = next(r for r in second if r["kind"] == "level")
    assert (level["actor"], level["level"]) == ("Wren", 2)
    pools = _pools(world_id)
    assert pools["goblin-2"] == 0 and pools["goblin-1"] <= 7
    after = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    (wren_now,) = after["members"]
    assert (wren_now["level"], wren_now["xp_next_level"]) == (2, 900)
    assert wren_now["xp"] == 290 + xp["share"]
    assert wren_now["hp_max"] == hero["hp_max"] + level["amount"]
    # Level 2 brings a third first-level slot; two were spent today.
    assert wren_now["spell_slots"] == [3] and wren_now["spell_slots_left"] == [1]
    if pools["goblin-1"] > 0:
        assert [(f["name"], f["hp_current"]) for f in after["foes"]] == [
            ("Goblin 1", pools["goblin-1"]),
            ("Goblin 2", 0),
        ]
    else:
        assert after["foes"] == []  # both fell: the fight is over


def test_the_party_is_only_in_its_own_scenes() -> None:
    from worldsim.domain.ids import new_character_id, new_party_member_id, new_world_id
    from worldsim.domain.party import PartyMember, party_in_scene
    from worldsim.domain.rules.dnd import Sheet

    world, hero = new_world_id(), new_character_id()

    def member(character: UUID | None) -> PartyMember:
        return PartyMember(
            id=new_party_member_id(),
            world_id=world,
            name="Wren",
            name_key="wren",
            character_id=character,
            sheet=Sheet(name="Wren"),
        )

    linked = [member(hero)]
    assert party_in_scene(linked, [str(hero)]) == linked
    assert party_in_scene(linked, [str(new_character_id())]) == []
    unlinked = [member(None)]  # a party begun by hand counts everywhere
    assert party_in_scene(unlinked, []) == unlinked
