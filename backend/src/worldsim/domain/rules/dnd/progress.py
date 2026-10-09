"""Spell slots spent, XP shared and levels gained (combat-depth-001).

Pure helpers over a sheet and the SRD tables; the caller persists.

- **Slots.** A sheet's class table gives its slots a day by spell level.
  ``slots_used`` counts what was spent on ``slots_day`` (a story day);
  a new story day is the night's long rest, so slots spent on an earlier
  day are back. Cantrips never take a slot.
- **XP.** A foe that falls gives the XP its stat block lists (SRD, by
  challenge rating), shared evenly by the whole party (5e: rounded down).
- **Levels.** Crossing a 5e threshold (``LEVEL_XP``) levels up through
  ``level_up_preview``: average hit-die HP (never below 1), the new level's
  proficiency and slots follow from the level, and spells the class gains
  at the new level are added to the ones already known. A hero at 0 hit
  points stays down: the level raises the maximum, not the current.
- **Choices** (combat-depth-002). A level that brings an Ability Score
  Improvement leaves the player a choice (+2 to one ability or +1 to two);
  the spells a level brings are picked for them and may be swapped. Those
  who do not choose (companions) take +2 in their class's first ability.
- **Long rest.** A later story day is the night's rest: full health, no
  conditions, every slot back (``long_rest``, lazy like the slots).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

from worldsim.domain.rules.dnd.combat import level_up_preview
from worldsim.domain.rules.dnd.core import level_from_xp
from worldsim.domain.rules.dnd.data import (
    DataTables,
    dict_field,
    entry,
    int_field,
    list_field,
    table,
)
from worldsim.domain.rules.dnd.party import ABILITY_PRIORITY, auto_spells, spell_limits
from worldsim.domain.rules.dnd.sheets import HitPoints, LevelChoice, Sheet

_NUMBERED_RE = re.compile(r"^(.+)-(\d+)$")


def class_slots(tables: DataTables, sheet: Sheet) -> list[int]:
    """Slots a day by spell level at the sheet's level ([] for non-casters)."""
    levels = list_field(entry(table(tables, "classes"), sheet.character_class), "levels")
    at = min(max(sheet.level, 1), 20) - 1
    raw: object = levels[at] if len(levels) > at else None
    row = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    casting = dict_field(row, "spellcasting")
    slots = [n if isinstance(n, int) else 0 for n in list_field(casting, "slots")]
    while slots and slots[-1] == 0:
        slots.pop()
    return slots


def slots_spent(sheet: Sheet, day: int | None) -> list[int]:
    """Slots spent today; a new story day (the long rest) gives them back."""
    if day is not None and sheet.slots_day != day:
        return []
    return list(sheet.slots_used)


def slots_left(tables: DataTables, sheet: Sheet, day: int | None) -> list[int]:
    """Slots still free today by spell level (index 0 = first level)."""
    used = slots_spent(sheet, day)
    return [
        max(0, total - (used[pos] if pos < len(used) else 0))
        for pos, total in enumerate(class_slots(tables, sheet))
    ]


def free_slot(tables: DataTables, sheet: Sheet, want: int, day: int | None) -> int | None:
    """The lowest free slot level at or above ``want``; ``None`` when none is left."""
    left = slots_left(tables, sheet, day)
    for level in range(max(1, want), len(left) + 1):
        if left[level - 1] > 0:
            return level
    return None


def spend_slot(sheet: Sheet, level: int, day: int | None) -> None:
    """Mark one slot of ``level`` spent today (mutates the working sheet)."""
    used = slots_spent(sheet, day)
    while len(used) < level:
        used.append(0)
    used[level - 1] += 1
    sheet.slots_used = used
    if day is not None:
        sheet.slots_day = day


def monster_kind(key: str, monsters: dict[str, Any]) -> str:
    """The stat block a pool key belongs to: ``goblin-2`` is a ``goblin``."""
    if key in monsters:
        return key
    match = _NUMBERED_RE.match(key)
    if match and match.group(1) in monsters:
        return match.group(1)
    return key


def pool_number(key: str) -> int:
    """``goblin-2`` is number 2; a plain ``goblin`` counts as the first."""
    match = _NUMBERED_RE.match(key)
    return int(match.group(2)) if match else 1


ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
ABILITY_CAP = 20


@dataclass(frozen=True)
class LevelGain:
    """One level gained: what changed, for the dice and the panel."""

    name: str
    level: int
    hp_gain: int
    prof_bonus: int
    prof_changed: bool
    new_spells: list[str]
    #: Choices this level left to the player (``ability``, ``spells``).
    choices: list[str] = field(default_factory=list)
    #: Abilities raised for those who do not choose: {"str": 2}.
    improved: dict[str, int] = field(default_factory=dict)


def _tier(tables: DataTables, sheet: Sheet, level: int) -> dict[str, Any]:
    levels = list_field(entry(table(tables, "classes"), sheet.character_class), "levels")
    raw: object = levels[level - 1] if 0 < level <= len(levels) else None
    return cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}


def brings_improvement(tables: DataTables, sheet: Sheet, level: int) -> bool:
    """The class gains an Ability Score Improvement at ``level``."""
    now = int_field(_tier(tables, sheet, level), "ability_score_bonuses")
    return now > int_field(_tier(tables, sheet, level - 1), "ability_score_bonuses")


def auto_improve(sheet: Sheet) -> dict[str, int]:
    """+2 to the class's first abilities below the cap (mutates the sheet)."""
    order = ABILITY_PRIORITY.get(sheet.character_class, ABILITY_PRIORITY["fighter"])
    left = 2
    raised: dict[str, int] = {}
    for ability in order:
        step = min(ABILITY_CAP - sheet.stats.get(ability, 10), left)
        if step > 0:
            sheet.stats = {**sheet.stats, ability: sheet.stats.get(ability, 10) + step}
            raised[ability] = step
            left -= step
        if left == 0:
            break
    return raised


def level_up(tables: DataTables, sheet: Sheet, *, chooses: bool = False) -> LevelGain | None:
    """Raise the working sheet one level; ``None`` at the cap.

    ``chooses``: the player makes the level's choices (an improvement, the
    spells); otherwise they are made here."""
    preview = level_up_preview(sheet, tables)
    if preview is None:
        return None
    gain = max(1, preview.hp_gain)
    sheet.level = preview.new_level
    if sheet.hp is None:
        sheet.hp = HitPoints(current=gain, max=gain)
    else:
        # A hero who is down stays down: only the maximum grows.
        current = sheet.hp.current + gain if sheet.hp.current > 0 else 0
        sheet.hp = HitPoints(current=current, max=sheet.hp.max + gain)
    known_before = list(sheet.spells)
    learned = [
        spell
        for spell in auto_spells(tables, sheet.character_class, sheet.level, sheet.stats)
        if spell not in known_before
    ]
    sheet.spells = [*known_before, *learned]
    choices: list[str] = []
    improved: dict[str, int] = {}
    if brings_improvement(tables, sheet, sheet.level):
        if chooses:
            sheet.choices = [*sheet.choices, LevelChoice(kind="ability", level=sheet.level)]
            choices.append("ability")
        else:
            improved = auto_improve(sheet)
    if chooses and learned:
        pool = spell_limits(tables, sheet.character_class, sheet.level, sheet.stats).pool
        options = [spell for spell in pool if spell not in known_before]
        if len(options) > len(learned):
            sheet.choices = [
                *sheet.choices,
                LevelChoice(kind="spells", level=sheet.level, picked=learned, options=options),
            ]
            choices.append("spells")
    return LevelGain(
        name=sheet.name,
        level=sheet.level,
        hp_gain=gain,
        prof_bonus=preview.prof_bonus,
        prof_changed=preview.prof_changed,
        new_spells=learned,
        choices=choices,
        improved=improved,
    )


def gain_xp(
    tables: DataTables, sheet: Sheet, amount: int, *, chooses: bool = False
) -> list[LevelGain]:
    """Add XP to the working sheet and take every level it now reaches."""
    sheet.xp = max(0, sheet.xp + amount)
    gains: list[LevelGain] = []
    while level_from_xp(sheet.xp) > sheet.level:
        gained = level_up(tables, sheet, chooses=chooses)
        if gained is None:
            break
        gains.append(gained)
    return gains


def long_rest(sheet: Sheet, day: int | None) -> Sheet:
    """The sheet as it wakes on story day ``day`` (a copy; the input stays).

    A later day than the one it last woke on is the night's long rest:
    full health, conditions gone, every slot back. A sheet that has not
    woken on any day yet (``rest_day`` unknown) only learns the day."""
    if day is None or sheet.rest_day == day:
        return sheet
    woke = sheet.model_copy(deep=True)
    woke.rest_day = day
    if sheet.rest_day is None or sheet.rest_day > day:
        return woke
    if woke.hp is not None:
        woke.hp = HitPoints(current=woke.hp.max, max=woke.hp.max)
    woke.conditions = []
    woke.slots_used = []
    woke.slots_day = None
    return woke


def make_choice(
    sheet: Sheet,
    choice_id: str,
    *,
    abilities: dict[str, int] | None = None,
    spells: list[str] | None = None,
) -> Sheet:
    """The sheet with one level-up choice made (a copy). ``ValueError`` says
    what is wrong with the choice in plain words."""
    choice = next((c for c in sheet.choices if c.id == choice_id), None)
    if choice is None:
        raise ValueError("That choice has already been made.")
    made = sheet.model_copy(deep=True)
    if choice.kind == "ability":
        raised = {k: v for k, v in (abilities or {}).items() if v}
        if sorted(raised.values()) not in ([2], [1, 1]):
            raise ValueError("Choose +2 to one ability or +1 to two.")
        for ability, step in raised.items():
            if ability not in ABILITIES:
                raise ValueError(f"Unknown ability: {ability}.")
            if made.stats.get(ability, 10) + step > ABILITY_CAP:
                raise ValueError(f"An ability cannot go above {ABILITY_CAP}.")
            made.stats = {**made.stats, ability: made.stats.get(ability, 10) + step}
    else:
        chosen = list(dict.fromkeys(spells or []))
        if len(chosen) != len(choice.picked):
            raise ValueError(f"Choose {len(choice.picked)} spells.")
        allowed = set(choice.options) | set(choice.picked)
        if any(spell not in allowed for spell in chosen):
            raise ValueError("That spell is not one this level can teach.")
        kept = [spell for spell in made.spells if spell not in choice.picked]
        made.spells = [*kept, *[spell for spell in chosen if spell not in kept]]
    made.choices = [c for c in made.choices if c.id != choice_id]
    return made
