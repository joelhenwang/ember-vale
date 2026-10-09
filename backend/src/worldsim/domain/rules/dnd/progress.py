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
  at the new level are added to the ones already known.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from worldsim.domain.rules.dnd.combat import level_up_preview
from worldsim.domain.rules.dnd.core import level_from_xp
from worldsim.domain.rules.dnd.data import DataTables, dict_field, entry, list_field, table
from worldsim.domain.rules.dnd.party import auto_spells
from worldsim.domain.rules.dnd.sheets import HitPoints, Sheet

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


@dataclass(frozen=True)
class LevelGain:
    """One level gained: what changed, for the dice and the panel."""

    name: str
    level: int
    hp_gain: int
    prof_bonus: int
    prof_changed: bool
    new_spells: list[str]


def level_up(tables: DataTables, sheet: Sheet) -> LevelGain | None:
    """Raise the working sheet one level; ``None`` at the cap."""
    preview = level_up_preview(sheet, tables)
    if preview is None:
        return None
    gain = max(1, preview.hp_gain)
    sheet.level = preview.new_level
    if sheet.hp is None:
        sheet.hp = HitPoints(current=gain, max=gain)
    else:
        sheet.hp = HitPoints(current=sheet.hp.current + gain, max=sheet.hp.max + gain)
    learned = [
        spell
        for spell in auto_spells(tables, sheet.character_class, sheet.level, sheet.stats)
        if spell not in sheet.spells
    ]
    sheet.spells = [*sheet.spells, *learned]
    return LevelGain(
        name=sheet.name,
        level=sheet.level,
        hp_gain=gain,
        prof_bonus=preview.prof_bonus,
        prof_changed=preview.prof_changed,
        new_spells=learned,
    )


def gain_xp(tables: DataTables, sheet: Sheet, amount: int) -> list[LevelGain]:
    """Add XP to the working sheet and take every level it now reaches."""
    sheet.xp = max(0, sheet.xp + amount)
    gains: list[LevelGain] = []
    while level_from_xp(sheet.xp) > sheet.level:
        gained = level_up(tables, sheet)
        if gained is None:
            break
        gains.append(gained)
    return gains
