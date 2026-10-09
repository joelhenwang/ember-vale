"""Pure combat tag resolution (owned by DND-WIRE-2).

Scripted RNG makes every roll exact; the input sheets must be
untouched (the caller persists deltas). Goblin: AC 15, HP 7, DEX +2.
Borin: +5 longsword, AC 18. Elara: +5 spell attack, DC 13.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path

from worldsim.domain.rules.dnd import (
    HitPoints,
    MonsterState,
    Sheet,
    combat_rolls,
    load_data,
    resolve_narration_tags,
)

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")


def _borin(hp: int = 13) -> Sheet:
    return Sheet(
        name="Borin",
        race="dwarf",
        character_class="fighter",
        level=1,
        stats={"str": 16, "dex": 12, "con": 15, "int": 8, "wis": 11, "cha": 10},
        hp=HitPoints(current=hp, max=13),
        armor="Chain Mail",
        shield=True,
        weapons=["longsword"],
    )


def _elara(level: int = 3) -> Sheet:
    return Sheet(
        name="Elara",
        race="elf",
        character_class="wizard",
        level=level,
        stats={"str": 8, "dex": 14, "con": 12, "int": 16, "wis": 10, "cha": 10},
        hp=HitPoints(current=17, max=17),
        weapons=["dagger"],
        spells=["fire-bolt", "fireball", "cure-wounds"],
    )


def _rng(*seq: float) -> Callable[[], float]:
    values = list(seq)
    state = {"i": 0}

    def draw() -> float:
        value = values[state["i"] % len(values)]
        state["i"] += 1
        return value

    return draw


def test_melee_hit_and_miss() -> None:
    report = resolve_narration_tags("ATTACK[longsword at goblin]", [_borin()], DATA, _rng(0.5, 0.5))
    assert len(report.outcomes) == 1
    assert report.outcomes[0].text == "Borin hits Goblin for 5 slashing. (7->2 HP)"
    assert report.beats[0].text == "Borin's Longsword hits Goblin for 5 slashing."
    assert report.beats[0].cited == ["dnd-sheet:borin"]
    assert report.hp == {} and report.unresolved == []

    missed = resolve_narration_tags("ATTACK[longsword at goblin]", [_borin()], DATA, _rng(0.0))
    assert missed.outcomes[0].text == "Borin misses Goblin (6 vs AC 15)."


def test_melee_crit_doubles_dice() -> None:
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]", [_borin()], DATA, _rng(0.9999, 0.5, 0.5)
    )
    assert report.outcomes[0].text == ("Borin hits Goblin for 10 slashing. Critical! (7->0 HP)")


def test_party_target_takes_hp_delta() -> None:
    sheets = [_borin(), _elara()]
    before = [s.model_dump() for s in sheets]
    report = resolve_narration_tags("ATTACK[longsword at Elara]", sheets, DATA, _rng(0.5, 0.25))
    assert report.outcomes[0].text == "Borin hits Elara for 3 slashing. (17->14 HP)"
    assert report.hp == {"elara": 14}
    assert report.beats[0].cited == ["dnd-sheet:borin", "dnd-sheet:elara"]
    assert [s.model_dump() for s in sheets] == before


def test_cantrip_attack_roll() -> None:
    report = resolve_narration_tags("CAST[fire bolt at goblin]", [_elara()], DATA, _rng(0.5, 0.5))
    assert report.outcomes[0].text == ("Fire Bolt hits Goblin for 6 fire. (7->1 HP)")


def test_save_for_half_damage() -> None:
    failed = resolve_narration_tags(
        "CAST[fireball at goblin]", [_elara(5)], DATA, _rng(0.0, *[0.0] * 8)
    )
    assert failed.outcomes[0].text == ("Fireball Goblin fails (3 vs DC 14) for 8 fire. (7->0 HP)")
    saved = resolve_narration_tags(
        "CAST[fireball at goblin]", [_elara(5)], DATA, _rng(0.9999, *[0.5] * 8)
    )
    assert saved.outcomes[0].text == (
        "Fireball Goblin saves (22 vs DC 14), half damage for 16 fire. (7->0 HP)"
    )


def test_heal_substitutes_mod() -> None:
    report = resolve_narration_tags(
        "CAST[cure wounds on Borin]", [_borin(hp=5), _elara()], DATA, _rng(0.5)
    )
    assert report.outcomes[0].text == "Elara heals Borin for 8. (5->13 HP)"
    assert report.hp == {"borin": 13}


def test_condition_applies_once() -> None:
    report = resolve_narration_tags(
        "CONDITION[poisoned on Borin for 3 rounds]", [_borin()], DATA, _rng()
    )
    assert report.conditions == {"borin": ["Poisoned"]}
    assert report.beats[0].text == "Borin is poisoned (3 round)."
    again = resolve_narration_tags(
        "CONDITION[poisoned on Borin for 3 rounds]",
        [_borin()],
        DATA,
        _rng(),
    )
    assert again.conditions == {"borin": ["Poisoned"]}


def test_condition_stacks_on_existing() -> None:
    wounded = _borin()
    wounded.conditions.append("Prone")
    report = resolve_narration_tags("CONDITION[poisoned on Borin]", [wounded], DATA, _rng())
    assert report.conditions == {"borin": ["Prone", "Poisoned"]}


def test_encounter_rates_difficulty() -> None:
    report = resolve_narration_tags("ENCOUNTER[2x goblin]", [_borin(), _elara()], DATA, _rng())
    assert report.outcomes[0].text == "Encounter: 2x Goblin (easy, 150 adjusted XP)."


def test_unresolved_and_empty() -> None:
    report = resolve_narration_tags(
        "ATTACK[ballista]\nCAST[wish]\nRECRUIT[Lyra]: elf ranger",
        [_borin()],
        DATA,
        _rng(),
    )
    assert report.unresolved == ["ATTACK[ballista]", "CAST[wish]"]
    assert report.outcomes == [] and report.beats == []
    assert resolve_narration_tags("", [_borin()], DATA, _rng()) == resolve_narration_tags(
        "Dreams.", [], DATA, _rng()
    )


def test_seeded_streams_replay() -> None:
    text = "ATTACK[longsword at goblin]\nCAST[fire bolt at goblin]"
    first = resolve_narration_tags(text, [_borin(), _elara()], DATA, random.Random(7).random)
    second = resolve_narration_tags(text, [_borin(), _elara()], DATA, random.Random(7).random)
    assert first == second


def _goblin(current: int) -> MonsterState:
    return MonsterState(key="goblin", name="Goblin", hp_current=current, hp_max=7, ac=15)


def test_carried_pool_continues_across_scenes() -> None:
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]",
        [_borin()],
        DATA,
        _rng(0.5, 0.5),
        live=[_goblin(2)],
    )
    assert report.outcomes[0].text == "Borin hits Goblin for 5 slashing. (2->0 HP)"
    pool = report.monsters["goblin"]
    assert (pool.hp_current, pool.hp_max, pool.spawned) == (0, 7, False)


def test_fresh_encounter_respawns_pool() -> None:
    report = resolve_narration_tags(
        "ENCOUNTER[goblin]\nATTACK[longsword at goblin]",
        [_borin()],
        DATA,
        _rng(0.5, 0.5),
        live=[_goblin(2)],
    )
    assert report.outcomes[1].text == "Borin hits Goblin for 5 slashing. (7->2 HP)"
    pool = report.monsters["goblin"]
    assert (pool.hp_current, pool.spawned) == (2, True)


def test_untouched_pool_not_persisted() -> None:
    report = resolve_narration_tags(
        "CONDITION[poisoned on Borin for 2 rounds]",
        [_borin()],
        DATA,
        _rng(),
        live=[_goblin(2)],
    )
    assert report.monsters == {}
    assert report.conditions == {"borin": ["Poisoned"]}


def test_dead_pool_stays_down() -> None:
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]",
        [_borin()],
        DATA,
        _rng(0.5, 0.5),
        live=[_goblin(0)],
    )
    assert report.outcomes[0].text == "Borin hits Goblin for 5 slashing. (0->0 HP)"
    assert report.monsters == {}


def test_foe_strikes_back_with_its_own_weapon() -> None:
    report = resolve_narration_tags(
        "ENCOUNTER[goblin]\nATTACK[goblin at Borin]", [_borin()], DATA, _rng(0.9, 0.5)
    )
    strike = report.outcomes[1]
    assert (strike.actor, strike.target, strike.using) == ("Goblin", "Borin", "Scimitar")
    assert strike.actor_foe and not strike.target_foe
    assert (strike.natural, strike.roll, strike.ac, strike.result) == (19, 23, 18, "hit")
    assert strike.text == "Goblin hits Borin for 6 slashing. (13->7 HP)"
    assert report.hp == {"borin": 7}
    assert report.beats[1].text == "The goblin's scimitar hits Borin for 6 slashing."
    assert report.foes == ["goblin"]


def test_fallen_or_unknown_foes_do_not_strike() -> None:
    fallen = resolve_narration_tags(
        "ATTACK[goblin at Borin]", [_borin()], DATA, _rng(0.9), live=[_goblin(0)]
    )
    assert fallen.unresolved == ["ATTACK[goblin at Borin]"] and fallen.hp == {}
    nobody = resolve_narration_tags("ATTACK[goblin at Ash]", [_borin()], DATA, _rng(0.9))
    assert nobody.unresolved == ["ATTACK[goblin at Ash]"]


def test_rolls_carry_their_parts() -> None:
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]\nCAST[fireball at goblin]",
        [_borin(), _elara(5)],
        DATA,
        _rng(0.0, *[0.0] * 9),
    )
    miss, burn, *_ = report.outcomes
    assert (miss.result, miss.roll, miss.ac, miss.target_foe) == ("miss", 6, 15, True)
    assert (burn.result, burn.dc, burn.using, burn.damage_type) == (
        "failed",
        14,
        "Fireball",
        "fire",
    )
    # A foe first met mid-fight is kept for the next scene and the party panel.
    assert report.foes == ["goblin"] and "goblin" in report.monsters
    rows = combat_rolls(report.outcomes, ["Lyra"])
    assert rows[0] == {
        "kind": "attack",
        "text": "Borin misses Goblin (6 vs AC 15).",
        "actor": "Borin",
        "target": "Goblin",
        "using": "Longsword",
        "roll": 6,
        "natural": 1,
        "ac": 15,
        "result": "miss",
        "target_foe": True,
    }
    assert rows[-1] == {"kind": "recruit", "text": "Lyra joins the party.", "actor": "Lyra"}


# --- combat-depth-001: each foe its own health, XP and levels, slots spent ---


def test_group_foes_get_their_own_pools_and_numbers() -> None:
    report = resolve_narration_tags(
        "ENCOUNTER[2x goblin]\nATTACK[longsword at Goblin 2]\nATTACK[longsword at goblin]",
        [_borin()],
        DATA,
        _rng(0.5, 0.5),
    )
    encounter, second, first = report.outcomes[:3]
    assert encounter.target == "Goblin 1, Goblin 2"
    assert report.beats[0].text.startswith("Goblin 1, Goblin 2 bar the way")
    # A number aims at that one; a plain name is the first still standing.
    assert (second.target, second.hp_before, second.hp_after) == ("Goblin 2", 7, 2)
    assert (first.target, first.hp_before, first.hp_after) == ("Goblin 1", 7, 2)
    assert report.foes == ["goblin-1", "goblin-2"]
    assert {k: (m.name, m.hp_current) for k, m in report.monsters.items()} == {
        "goblin-1": ("Goblin 1", 2),
        "goblin-2": ("Goblin 2", 2),
    }


def test_foe_name_parts_reads_every_way_of_numbering() -> None:
    from worldsim.domain.rules.dnd.combat_resolve import foe_name_parts

    assert foe_name_parts("Goblin 2") == ("Goblin", 2)
    assert foe_name_parts("the second goblin") == ("goblin", 2)
    assert foe_name_parts("2nd goblin") == ("goblin", 2)
    assert foe_name_parts("goblin #3") == ("goblin", 3)
    assert foe_name_parts("the goblin") == ("goblin", None)


def _pack(*hps: int) -> list[MonsterState]:
    return [
        MonsterState(key=f"goblin-{n}", name=f"Goblin {n}", hp_current=hp, hp_max=7, ac=15)
        for n, hp in enumerate(hps, start=1)
    ]


def test_plain_target_skips_the_fallen_and_strikes_come_from_the_standing() -> None:
    report = resolve_narration_tags(
        "ATTACK[longsword at the goblin]\nATTACK[goblin at Borin]",
        [_borin()],
        DATA,
        _rng(0.5, 0.5, 0.9, 0.5),
        live=_pack(0, 4),
        fighting=["goblin-1", "goblin-2"],
    )
    hit, strike = report.outcomes[:2]
    assert (hit.target, hit.hp_before, hit.hp_after) == ("Goblin 2", 4, 0)
    # Both have fallen now: nobody strikes back.
    assert strike.kind == "xp" and report.unresolved == ["ATTACK[goblin at Borin]"]


def test_fresh_encounter_after_a_finished_fight_starts_fresh() -> None:
    report = resolve_narration_tags(
        "ENCOUNTER[2x goblin]", [_borin()], DATA, _rng(), live=_pack(0, 0), fighting=[]
    )
    assert report.foes == ["goblin-1", "goblin-2"]
    assert all(m.hp_current == 7 and m.spawned for m in report.monsters.values())


def test_reinforcements_join_a_fight_that_is_on() -> None:
    report = resolve_narration_tags(
        "ENCOUNTER[goblin]",
        [_borin()],
        DATA,
        _rng(),
        live=_pack(0, 5),
        fighting=["goblin-1", "goblin-2"],
    )
    assert report.foes == ["goblin-3"]
    assert report.monsters["goblin-3"].name == "Goblin 3"
    assert "goblin-2" not in report.monsters  # the standing one is untouched


def test_defeated_foes_give_shared_xp() -> None:
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]",
        [_borin(), _elara()],
        DATA,
        _rng(0.5, 0.5),
        live=_pack(2),
    )
    xp = report.outcomes[-1]
    assert (xp.kind, xp.amount, xp.share, xp.target) == ("xp", 50, 25, "Goblin 1")
    assert report.defeated == ["goblin-1"]
    assert report.sheets["borin"].xp == 25 and report.sheets["elara"].xp == 25
    assert report.levels == []


def test_crossing_a_threshold_levels_up() -> None:
    veteran = _borin()
    veteran.xp = 290
    report = resolve_narration_tags(
        "ATTACK[longsword at goblin]", [veteran], DATA, _rng(0.5, 0.5), live=_pack(2)
    )
    sheet = report.sheets["borin"]
    assert (sheet.xp, sheet.level) == (340, 2)
    # Fighter d10 average 6 + CON +2; current and max both rise.
    assert sheet.hp is not None and (sheet.hp.current, sheet.hp.max) == (21, 21)
    level = report.outcomes[-1]
    assert (level.kind, level.actor, level.level, level.amount) == ("level", "Borin", 2, 8)
    assert level.text == "Borin reaches level 2: +8 hit points."
    rows = combat_rolls(report.outcomes, [])
    assert rows[-1]["kind"] == "level" and rows[-2]["share"] == 50
    assert veteran.level == 1 and veteran.xp == 290  # inputs untouched


def test_levelled_spells_spend_slots_and_fail_without_one() -> None:
    elara = _elara()  # level 3 wizard: 4 first-level, 2 second-level slots
    text = "\n".join(["CAST[magic missile at goblin]"] * 7)
    if "magic-missile" not in elara.spells:
        elara.spells.append("magic-missile")
    report = resolve_narration_tags(text, [elara], DATA, _rng(0.5), live=_pack(99), day=1)
    results = [o.result for o in report.outcomes if o.kind == "cast"]
    # 4 first-level slots, then 2 second-level (upcast), then none.
    assert results.count("no-slot") == 1 and results[-1] == "no-slot"
    assert report.outcomes[-1].text == (
        "Elara has no 1st-level spell slot left: Magic Missile fails."
    )
    assert report.sheets["elara"].slots_used == [4, 2]
    assert report.sheets["elara"].slots_day == 1
    # A new day is the long rest: the slots are back.
    rested = resolve_narration_tags(
        "CAST[magic missile at goblin]",
        [report.sheets["elara"]],
        DATA,
        _rng(0.5),
        live=_pack(99),
        day=2,
    )
    assert rested.sheets["elara"].slots_used == [1]


def test_cantrips_are_free() -> None:
    report = resolve_narration_tags(
        "CAST[fire bolt at goblin]\n" * 6, [_elara()], DATA, _rng(0.5), live=_pack(99), day=1
    )
    assert all(o.result != "no-slot" for o in report.outcomes)
    assert report.sheets["elara"].slots_used == []  # changed only by the XP
