"""Experience for a settled rumour (quest-xp-001).

A combat story's party also grows by finishing matters, not only by
felling foes. When a rumour settles (the director's ending or the
resolver's ``hook_settled``), every party member gains the 5e "medium
encounter" XP threshold for their own level (``ENCOUNTER_BUDGET``): 50 at
level 1, 100 at 2, 150 at 3, 250 at 4, 500 at 5 ... Each member gets it in
full (not shared), and levels follow exactly as for fights (``gain_xp``).

Pure: sheets in, working copies and the rows for the story log out; the
caller persists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldsim.domain.rules.dnd.core import ENCOUNTER_BUDGET
from worldsim.domain.rules.dnd.data import DataTables
from worldsim.domain.rules.dnd.progress import LevelGain, gain_xp, long_rest
from worldsim.domain.rules.dnd.sheets import Sheet

#: Column of ``ENCOUNTER_BUDGET`` (easy, medium, hard, deadly) a settle is worth.
_MEDIUM = 1


def settle_xp(level: int) -> int:
    """XP one member gains for a settled rumour at ``level`` (5e medium encounter)."""
    return ENCOUNTER_BUDGET[min(max(1, level), len(ENCOUNTER_BUDGET)) - 1][_MEDIUM]


@dataclass(frozen=True)
class SettleAward:
    """What a settle gave: changed sheets by name key and the story-log rows."""

    sheets: dict[str, Sheet] = field(default_factory=dict)
    rolls: list[dict[str, Any]] = field(default_factory=list)
    levels: list[LevelGain] = field(default_factory=list)


def award_settled(
    tables: DataTables,
    title: str,
    members: list[tuple[str, Sheet]],
    *,
    chooses: set[str] | None = None,
    day: int | None = None,
) -> SettleAward:
    """Give each member (``(name_key, sheet)``) the settle XP for their level.

    Sheets wake on story ``day`` first (``long_rest``), as for a fight. One
    ``xp`` row (``result`` "settled") per amount given, naming who got it
    when amounts differ; one ``level`` row per level gained."""
    if not members:
        return SettleAward()
    matter = title.strip() or "A rumour"
    working = {key: long_rest(sheet, day).model_copy(deep=True) for key, sheet in members}
    by_amount: dict[int, list[str]] = {}
    for key, sheet in members:
        by_amount.setdefault(settle_xp(sheet.level), []).append(key)
    rows: list[dict[str, Any]] = []
    for amount, keys in by_amount.items():
        names = ", ".join(working[key].name for key in keys)
        row: dict[str, Any] = {
            "kind": "xp",
            "result": "settled",
            "text": f"Settled: {matter} · {amount} XP each.",
            "target": matter,
            "amount": amount * len(keys),
            "share": amount,
        }
        if len(by_amount) > 1:
            row["actor"] = names
            row["text"] = f"Settled: {matter} · {amount} XP each for {names}."
        rows.append(row)
    gains: list[LevelGain] = []
    for amount, keys in by_amount.items():
        for key in keys:
            for gained in gain_xp(tables, working[key], amount, chooses=key in (chooses or set())):
                gains.append(gained)
                rows.append(_level_row(gained))
    return SettleAward(sheets=working, rolls=rows, levels=gains)


def _level_row(gained: LevelGain) -> dict[str, Any]:
    """A level gained, worded as the fights word it."""
    trail = f", proficiency +{gained.prof_bonus}" if gained.prof_changed else ""
    if gained.improved:
        trail += ", " + ", ".join(
            f"{ability.upper()} +{step}" for ability, step in gained.improved.items()
        )
    row: dict[str, Any] = {
        "kind": "level",
        "text": f"{gained.name} reaches level {gained.level}: +{gained.hp_gain} hit points{trail}.",
        "actor": gained.name,
        "amount": gained.hp_gain,
        "level": gained.level,
    }
    if gained.choices:
        row["choose"] = ",".join(gained.choices)
    return row
