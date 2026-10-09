"""Fights that follow the player, a night's rest, and level-up choices
(combat-depth-002).

- A hero's own plain attack or spell rolls even when the storyteller did
  not tag it (``deeds``); a tagged hero is never rolled twice.
- A hero at 0 hit points stays down when a level comes.
- A later story day is the long rest: full health, no conditions, slots back.
- A level with an Ability Score Improvement leaves the player a choice, and
  the spells it brings may be swapped; companions take theirs at once.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.domain.rules.dnd import HitPoints, MonsterState, Sheet, load_data
from worldsim.domain.rules.dnd.combat_resolve import resolve_narration_tags
from worldsim.domain.rules.dnd.deeds import Deed
from worldsim.domain.rules.dnd.progress import gain_xp, long_rest, make_choice
from worldsim.domain.rules.dnd.sheets import LevelChoice
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")


def _wren(hp: int = 12, **extra: Any) -> Sheet:
    return Sheet(
        name="Wren",
        race="human",
        character_class="fighter",
        level=1,
        stats={"str": 16, "dex": 13, "con": 14, "int": 8, "wis": 12, "cha": 10},
        hp=HitPoints(current=hp, max=12),
        armor="Chain Mail",
        weapons=["longsword", "crossbow-light"],
        **extra,
    )


def _elara() -> Sheet:
    return Sheet(
        name="Elara",
        race="elf",
        character_class="wizard",
        level=3,
        stats={"str": 8, "dex": 14, "con": 12, "int": 16, "wis": 10, "cha": 10},
        hp=HitPoints(current=17, max=17),
        weapons=["dagger"],
        spells=["fire-bolt", "cure-wounds"],
    )


def _rng(*seq: float) -> Callable[[], float]:
    values = list(seq) or [0.5]
    state = {"i": 0}

    def draw() -> float:
        value = values[state["i"] % len(values)]
        state["i"] += 1
        return value

    return draw


def _goblins(*hps: int) -> list[MonsterState]:
    return [
        MonsterState(key=f"goblin-{n}", name=f"Goblin {n}", hp_current=hp, hp_max=7, ac=15)
        for n, hp in enumerate(hps, start=1)
    ]


# --- the player's own words ------------------------------------------------


def test_an_untagged_attack_in_the_players_words_rolls() -> None:
    report = resolve_narration_tags(
        "Wren's blade flashes in the smoke.",
        [_wren()],
        DATA,
        _rng(0.5),
        live=_goblins(7, 7),
        fighting=["goblin-1", "goblin-2"],
        deeds=[Deed(key="wren", text="I attack the second goblin with my longsword")],
    )
    (swing,) = [o for o in report.outcomes if o.kind == "attack"]
    assert (swing.actor, swing.using, swing.target) == ("Wren", "Longsword", "Goblin 2")
    assert report.deeds == 1 and report.unresolved == []


def test_a_tagged_hero_is_not_rolled_twice() -> None:
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]: Wren lunges.",
        [_wren()],
        DATA,
        _rng(0.5),
        live=_goblins(7),
        fighting=["goblin-1"],
        deeds=[Deed(key="wren", text="I attack the goblin")],
    )
    assert report.deeds == 0
    assert len([o for o in report.outcomes if o.kind == "attack"]) == 1


def test_standing_down_or_talking_is_no_deed() -> None:
    for words in ("I lower my sword and talk to it", "I don't attack, I wait", "I look around"):
        report = resolve_narration_tags(
            "The goblin snarls.",
            [_wren()],
            DATA,
            _rng(0.5),
            live=_goblins(7),
            fighting=["goblin-1"],
            deeds=[Deed(key="wren", text=words)],
        )
        assert report.deeds == 0 and report.outcomes == [], words


def test_shooting_takes_the_ranged_weapon_and_a_spell_by_name_is_cast() -> None:
    shot = resolve_narration_tags(
        "The goblin ducks behind a cart.",
        [_wren()],
        DATA,
        _rng(0.5),
        live=_goblins(7),
        fighting=["goblin-1"],
        deeds=[Deed(key="wren", text="I shoot at it")],
    )
    assert [o.using for o in shot.outcomes if o.kind == "attack"] == ["Crossbow, light"]
    spell = resolve_narration_tags(
        "Sparks gather.",
        [_wren(), _elara()],
        DATA,
        _rng(0.5),
        live=_goblins(7),
        fighting=["goblin-1"],
        deeds=[Deed(key="elara", text="I hurl a fire bolt at the goblin")],
    )
    (cast,) = [o for o in spell.outcomes if o.kind == "cast"]
    assert (cast.actor, cast.using, cast.target) == ("Elara", "Fire Bolt", "Goblin 1")
    healed = resolve_narration_tags(
        "Elara kneels.",
        [_wren(hp=4), _elara()],
        DATA,
        _rng(0.5),
        deeds=[Deed(key="elara", text="I cast cure wounds on Wren")],
    )
    assert healed.hp == {"wren": 12}


def test_a_creature_both_name_opens_the_fight_and_an_unnamed_one_does_not() -> None:
    opened = resolve_narration_tags(
        "A grey wolf circles the camp, hackles raised.",
        [_wren()],
        DATA,
        _rng(0.5),
        deeds=[Deed(key="wren", text="I attack the wolf")],
    )
    kinds = [(o.kind, o.target) for o in opened.outcomes]
    assert kinds[:2] == [("encounter", "Wolf"), ("attack", "Wolf")]
    nothing = resolve_narration_tags(
        "The road is quiet.",
        [_wren()],
        DATA,
        _rng(0.5),
        deeds=[Deed(key="wren", text="I attack the wolf")],
    )
    assert nothing.outcomes == [] and nothing.deeds == 0


def test_the_deed_rolls_after_the_scenes_encounter() -> None:
    report = resolve_narration_tags(
        "ENCOUNTER[2x goblin]: Two goblins leap out.\nThey shriek.",
        [_wren()],
        DATA,
        _rng(0.5),
        deeds=[Deed(key="wren", text="I charge the first goblin")],
    )
    assert [o.kind for o in report.outcomes][:2] == ["encounter", "attack"]
    assert report.outcomes[1].target == "Goblin 1"


# --- levels, rest and choices --------------------------------------------


def test_a_downed_hero_stays_down_when_a_level_comes() -> None:
    sheet = _wren(hp=0)
    (gained,) = gain_xp(DATA, sheet, 300)
    assert sheet.level == 2 and sheet.hp is not None
    assert (sheet.hp.current, sheet.hp.max) == (0, 12 + gained.hp_gain)
    standing = _wren(hp=5)
    gain_xp(DATA, standing, 300)
    assert standing.hp is not None and standing.hp.current == 5 + gained.hp_gain


def test_a_later_day_is_the_long_rest() -> None:
    hurt = _wren(hp=3, conditions=["Poisoned"], slots_used=[2], slots_day=1, rest_day=1)
    assert long_rest(hurt, 1) is hurt
    woke = long_rest(hurt, 2)
    assert woke.hp is not None and woke.hp.current == 12
    assert (woke.conditions, woke.slots_used, woke.rest_day) == ([], [], 2)
    assert hurt.hp is not None and hurt.hp.current == 3  # the input stays
    # A sheet that never woke on a day only learns the day.
    fresh = long_rest(_wren(hp=3), 2)
    assert fresh.hp is not None and (fresh.hp.current, fresh.rest_day) == (3, 2)


def test_a_fight_on_a_new_day_starts_rested_and_keeps_the_day() -> None:
    report = resolve_narration_tags(
        "ATTACK[goblin at Wren]: The goblin lunges.",
        [_wren(hp=2, rest_day=1)],
        DATA,
        _rng(0.95, 0.5),
        live=_goblins(7),
        fighting=["goblin-1"],
        day=2,
    )
    (strike,) = report.outcomes
    assert strike.hp_before == 12
    assert report.sheets["wren"].rest_day == 2


def test_an_improvement_is_the_players_choice_and_a_companions_is_made() -> None:
    hero = _wren()
    gains = gain_xp(DATA, hero, 2700, chooses=True)
    assert [g.level for g in gains] == [2, 3, 4] and gains[-1].choices == ["ability"]
    assert hero.stats["str"] == 16 and [c.id for c in hero.choices] == ["ability-4"]
    made = make_choice(hero, "ability-4", abilities={"str": 1, "con": 1})
    assert (made.stats["str"], made.stats["con"], made.choices) == (17, 15, [])
    with pytest.raises(ValueError, match=r"\+2 to one ability or \+1 to two"):
        make_choice(hero, "ability-4", abilities={"str": 3})
    with pytest.raises(ValueError, match="already been made"):
        make_choice(made, "ability-4", abilities={"str": 2})
    mate = _wren()
    gains = gain_xp(DATA, mate, 2700)
    assert gains[-1].improved == {"str": 2} and mate.stats["str"] == 18 and mate.choices == []


def test_the_spells_a_level_brings_can_be_swapped() -> None:
    sage = _elara()
    sage.spells = []
    gains = gain_xp(DATA, sage, 2700, chooses=True)
    (choice,) = [c for c in sage.choices if c.kind == "spells"]
    assert "spells" in gains[-1].choices and choice.picked
    other = next(s for s in choice.options if s not in choice.picked)
    chosen = [other, *choice.picked[1:]]
    made = make_choice(sage, choice.id, spells=chosen)
    assert other in made.spells and choice.picked[0] not in made.spells
    with pytest.raises(ValueError, match="Choose"):
        make_choice(sage, choice.id, spells=chosen[:-1] if len(chosen) > 1 else [])
    with pytest.raises(ValueError, match="not one this level"):
        make_choice(sage, choice.id, spells=["wish", *chosen[1:]])


# --- end to end -------------------------------------------------------------


def _hero(world_id: UUID, change: Callable[[Sheet], None]) -> None:
    async def inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                (hero,) = await uow.party.list_for_world(world_id)
                sheet = hero.sheet.model_copy(deep=True)
                change(sheet)
                await uow.party.save_sheet(hero.id, sheet, hero.version)
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(inner())


def test_the_players_attack_rolls_rest_heals_and_choices_are_made(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "deed-story")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ids = {c["name"]: c["character_id"] for c in cast}

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if "Hearth" not in prompt:
                return None
            # The storyteller opens the fight but forgets to tag Wren's blow.
            text = "ENCOUNTER[goblin]: A goblin bursts from the hearth.\nWren's sword rings."
            return json.dumps([{"text": text, "cited_fact_keys": ["dnd-sheet:wren"]}])
        who = ids["Wren"] if "Wren" in prompt else ids["Ash"]
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Swung."})
        return None

    gateway.route = route
    moved = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": 1,
            "player_intents": {
                wren: {
                    "family": "interact",
                    "character_id": wren,
                    "snapshot_id": NIL_SNAPSHOT,
                    "attempt": "I attack the goblin with my longsword",
                }
            },
        },
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    chronicle = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 50},
        headers=headers,
    ).json()
    (fight,) = [e["combat"] for e in chronicle["entries"] if e["combat"]]
    swings = [r for r in fight["rolls"] if r["kind"] == "attack" and r.get("actor") == "Wren"]
    assert [(r["using"], r["target"]) for r in swings] == [("Longsword", "Goblin")]

    # A night later: rest heals; a level-four improvement waits for the player.
    def hurt(sheet: Sheet) -> None:
        assert sheet.hp is not None and sheet.rest_day == 1
        sheet.hp = HitPoints(current=1, max=sheet.hp.max)
        sheet.rest_day = 0
        sheet.choices = [LevelChoice(kind="ability", level=4)]

    _hero(world_id, hurt)
    party = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    (hero,) = party["members"]
    assert hero["hp_current"] == hero["hp_max"]
    assert [(c["id"], c["kind"]) for c in hero["choices"]] == [("ability-4", "ability")]
    strength = hero["abilities"]["str"]

    body = {
        "world_id": str(world_id),
        "choice_id": "ability-4",
        "expected_version": hero["version"],
        "abilities": {"str": 2},
    }
    made = client.post(f"/api/v1/stage1/party/{hero['id']}/choices", json=body, headers=headers)
    assert made.status_code == 200, made.text
    assert made.json()["abilities"]["str"] == strength + 2 and made.json()["choices"] == []
    again = client.post(
        f"/api/v1/stage1/party/{hero['id']}/choices",
        json={**body, "expected_version": made.json()["version"]},
        headers=headers,
    )
    assert again.status_code == 422, again.text


def test_a_level_roll_keeps_its_choice_for_the_reader() -> None:
    from worldsim.application.queries.presentation import _ROLLS
    from worldsim.domain.rules.dnd.combat_resolve import TagOutcome, combat_rolls_json

    rolls = combat_rolls_json(
        [
            TagOutcome(
                kind="level", text="Wren reaches level 4.", actor="Wren", level=4, choose="ability"
            )
        ],
        [],
    )
    (row,) = _ROLLS.validate_json(rolls)
    assert (row.kind, row.level, row.choose) == ("level", 4, "ability")


def test_foes_the_storyteller_left_silent_strike_back() -> None:
    report = resolve_narration_tags(
        "Steel rings in the smoke.",
        [_wren()],
        DATA,
        _rng(0.95, 0.5),
        live=_goblins(7, 7),
        fighting=["goblin-1", "goblin-2"],
        deeds=[Deed(key="wren", text="I attack the first goblin")],
        strike_back=True,
    )
    strikes = [o for o in report.outcomes if o.actor_foe]
    assert {(o.actor, o.target) for o in strikes} == {
        ("Goblin 1", "Wren"),
        ("Goblin 2", "Wren"),
    } or ([(o.actor, o.target) for o in strikes] == [("Goblin 2", "Wren")])
    # A tagged strike is the storyteller's: none are added; nor without a fight.
    tagged = resolve_narration_tags(
        "ATTACK[goblin at Wren]: It slashes.",
        [_wren()],
        DATA,
        _rng(0.5),
        live=[MonsterState(key="goblin-1", name="Goblin 1", hp_current=30, hp_max=30, ac=15)],
        fighting=["goblin-1"],
        deeds=[Deed(key="wren", text="I attack the goblin")],
        strike_back=True,
    )
    assert len([o for o in tagged.outcomes if o.actor_foe]) == 1
    quiet = resolve_narration_tags(
        "Wren looks around.",
        [_wren()],
        DATA,
        _rng(0.5),
        live=_goblins(7),
        fighting=["goblin-1"],
        deeds=[Deed(key="wren", text="I look around")],
        strike_back=True,
    )
    assert quiet.outcomes == []


def test_the_slain_do_not_come_back_by_the_players_words() -> None:
    report = resolve_narration_tags(
        "The wolf lies still by the hearth.",
        [_wren()],
        DATA,
        _rng(0.5),
        live=[MonsterState(key="wolf", name="Wolf", hp_current=0, hp_max=11, ac=13)],
        deeds=[Deed(key="wren", text="I stab at the wolf")],
    )
    assert report.outcomes == [] and report.deeds == 0


def test_a_blow_reads_as_the_dices_to_decide() -> None:
    from worldsim.domain.rules.dnd.deeds import looks_like_deed

    assert looks_like_deed("Wren tries to attack the goblin: it does not work")
    assert not looks_like_deed("Wren tries to lower the sword and talk")
    assert not looks_like_deed("Wren tries to bake bread: it works")


def test_a_downed_hero_does_not_swing_and_more_ways_of_attacking_count() -> None:
    down = resolve_narration_tags(
        "ATTACK[longsword at goblin]: Wren lunges.",
        [_wren(hp=0)],
        DATA,
        _rng(0.5),
        live=_goblins(7),
        fighting=["goblin-1"],
        deeds=[Deed(key="wren", text="I attack the goblin")],
    )
    assert [o for o in down.outcomes if o.actor == "Wren"] == [] and down.deeds == 0
    for words in ("I go after the second goblin", "I take on the goblin", "I rush the goblin"):
        report = resolve_narration_tags(
            "",
            [_wren()],
            DATA,
            _rng(0.5),
            live=_goblins(7, 7),
            fighting=["goblin-1", "goblin-2"],
            deeds=[Deed(key="wren", text=words)],
        )
        assert report.deeds == 1, words


def test_a_sparring_npc_without_a_sheet_does_not_break_the_turn(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "spar-story", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ids = {c["name"]: c["character_id"] for c in cast}

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            return None
        if "You decide" in system:  # only Ash decides: Wren is played
            return json.dumps(
                {
                    "family": "spar",
                    "character_id": ids["Ash"],
                    "snapshot_id": ids["Ash"],
                    "target_character_id": wren,
                    "weapon": "longsword",
                }
            )
        who = ids["Wren"] if "Wren" in prompt else ids["Ash"]
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Fine."})
        return None

    gateway.route = route
    for index in (1, 2):
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
    assert "spar" in _families(world_id), "Ash's spar never reached the turn"


def _families(world_id: UUID) -> list[str]:
    from sqlalchemy import text

    async def inner() -> list[str]:
        engine = create_engine(Settings())
        try:
            async with engine.connect() as conn:
                rows = await conn.execute(
                    text("SELECT family FROM character_intent WHERE world_id = :w"),
                    {"w": world_id},
                )
                return [str(row[0]) for row in rows]
        finally:
            await engine.dispose()

    return asyncio.run(inner())


def test_the_storyteller_hears_a_fight_is_over_and_who_is_down() -> None:
    from uuid import uuid4

    from worldsim.domain.party import Monster, down_line, fight_over_line

    def wolf(hp: int) -> Monster:
        return Monster(
            id=uuid4(),
            world_id=uuid4(),
            name_key="wolf",
            name="Wolf",
            hp_current=hp,
            hp_max=11,
            ac=13,
        )

    assert fight_over_line(3, 4, ["wolf"], [wolf(0)]) == (
        "The fight is over: Wolf lies defeated. They do not rise, growl or strike again."
    )
    assert fight_over_line(3, 4, ["wolf"], [wolf(4)]) is None  # still on
    assert fight_over_line(3, 9, ["wolf"], [wolf(0)]) is None  # long ago
    assert down_line([]) is None
    line = down_line(["Wren"])
    assert line is not None and line.startswith("Wren is down")


def test_the_fallen_get_back_up_once_the_fight_is_over() -> None:
    mate = Sheet(
        name="Ash",
        character_class="fighter",
        stats={"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10},
        hp=HitPoints(current=12, max=12),
        weapons=["longsword"],
    )
    # Ash finishes the last goblin while Wren lies down: Wren gets back up.
    ended = resolve_narration_tags(
        "ATTACK[longsword at goblin]: Ash swings.",
        [_wren(hp=0), mate],
        DATA,
        _rng(0.95, 0.5),
        live=_goblins(1),
        fighting=["goblin-1"],
        strike_back=True,
    )
    assert ("recover", "Wren", 0, 1) in [
        (o.kind, o.actor, o.hp_before, o.hp_after) for o in ended.outcomes
    ]
    assert ended.hp["wren"] == 1
    # No fight on: whoever was down is up at the start of the scene.
    calm = resolve_narration_tags(
        "Wren stirs by the hearth.", [_wren(hp=0)], DATA, _rng(0.5), strike_back=True
    )
    assert [o.kind for o in calm.outcomes] == ["recover"] and calm.hp == {"wren": 1}
    # A foe still standing: Wren stays down; elsewhere (no party here) too.
    on = resolve_narration_tags(
        "The goblin circles.",
        [_wren(hp=0)],
        DATA,
        _rng(0.5),
        live=_goblins(7),
        fighting=["goblin-1"],
        strike_back=True,
    )
    assert on.outcomes == []
    away = resolve_narration_tags("Ash sells apples.", [_wren(hp=0)], DATA, _rng(0.5))
    assert away.outcomes == []


def test_a_fight_begun_without_an_encounter_is_as_large_as_the_words_say() -> None:
    from worldsim.domain.rules.dnd.deeds import group_size

    assert group_size(["Two goblins rush in."], "Goblin") == 2
    assert group_size(["A pair of grey wolves circle."], "Wolf") == 2
    assert group_size(["3 bandits block the road", "the bandit"], "Bandit") == 3
    assert group_size(["The goblin snarls."], "Goblin") == 1
    # The storyteller strikes without opening the fight: two goblins, not one.
    tagged = resolve_narration_tags(
        "Two goblins burst in.\nATTACK[longsword at goblin]: Wren lunges.",
        [_wren()],
        DATA,
        _rng(0.0),
    )
    assert tagged.outcomes[0].kind == "encounter"
    assert tagged.outcomes[0].target == "Goblin 1, Goblin 2"
    assert tagged.foes == ["goblin-1", "goblin-2"]
    # The player's "second goblin" is a real foe.
    second = resolve_narration_tags(
        "Two goblins burst in through the back door.",
        [_wren()],
        DATA,
        _rng(0.5),
        deeds=[Deed(key="wren", text="I attack the second goblin")],
    )
    (swing,) = [o for o in second.outcomes if o.kind == "attack"]
    assert swing.target == "Goblin 2"
    wolves = resolve_narration_tags(
        "A pair of grey wolves slink in.",
        [_wren()],
        DATA,
        _rng(0.0),
        deeds=[Deed(key="wren", text="I attack the wolves")],
    )
    assert wolves.outcomes[0].target == "Wolf 1, Wolf 2"
    # A kind already slain opens nothing, even from the storyteller's tag.
    slain = resolve_narration_tags(
        "ATTACK[longsword at goblin]: Wren strikes the body.",
        [_wren()],
        DATA,
        _rng(0.5),
        live=[MonsterState(key="goblin", name="Goblin", hp_current=0, hp_max=7, ac=15)],
    )
    assert slain.outcomes == []
