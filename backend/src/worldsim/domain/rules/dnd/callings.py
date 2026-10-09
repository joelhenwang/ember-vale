"""Changing a companion's people and calling before their first fight (callings-001).

A companion joins with a calling suggested for them; the player may change
it until the companion has fought. "Fought" is read from the dice the story
kept, not guessed from the sheet: a roll in any event that names them as the
one acting or the one struck (a recruit line, experience and level rows do
not count, since a settled rumour gives experience without a fight). While a
fight is on nobody changes. The played hero's calling is chosen in the New
Story wizard and never changes here.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import cast

from worldsim.domain.ids import CharacterId
from worldsim.domain.party import PartyMember
from worldsim.domain.rules.dnd.data import DataTables, table
from worldsim.domain.rules.dnd.party import auto_sheet
from worldsim.domain.rules.dnd.sheets import Sheet

#: Rows that are not a fight: joining, experience and levels.
_NOT_FIGHTING = frozenset({"recruit", "xp", "level"})


def _names(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in cast("list[object]", value)]
    return []


def has_fought(name: str, summaries: Iterable[Mapping[str, str]]) -> bool:
    """Some kept roll names ``name`` as the one acting or the one struck."""
    key = name.strip().casefold()
    for summary in summaries:
        try:
            raw: object = json.loads(summary.get("rolls", "[]"))
        except ValueError:
            continue
        if not isinstance(raw, list):
            continue
        for row in cast("list[object]", raw):
            if not isinstance(row, dict):
                continue
            roll = cast("dict[str, object]", row)
            if roll.get("kind") in _NOT_FIGHTING:
                continue
            who = _names(roll.get("actor")) + _names(roll.get("target"))
            if any(w.strip().casefold() == key for w in who):
                return True
    return False


def calling_changeable(
    member: PartyMember, played: CharacterId | None, fought: bool, fight_on: bool
) -> bool:
    """A companion (not the played hero) who has never fought, with no fight on."""
    return played is not None and member.character_id != played and not fought and not fight_on


def valid_calling(race: str, character_class: str, data: DataTables) -> bool:
    return race in table(data, "races") and character_class in table(data, "classes")


def rebuild_calling(sheet: Sheet, race: str, character_class: str, data: DataTables) -> Sheet:
    """A fresh sheet for the new people and calling, at the same level, with
    the same name and experience (and the same story day for rests)."""
    fresh = auto_sheet(sheet.name, race, character_class, sheet.level, data)
    return fresh.model_copy(
        update={"xp": sheet.xp, "rest_day": sheet.rest_day, "slots_day": sheet.slots_day}
    )
