"""Draft validation shared by preview and atomic creation."""

from __future__ import annotations

import functools
from pathlib import Path

from worldsim.domain.rules.dnd import DataTables, load_data
from worldsim.domain.rules.dnd.data import table
from worldsim.domain.stories import DraftPayload

VALID_ROLES = ("player", "watcher", "director", "deity")
DND_DATA_DIR = Path(__file__).resolve().parents[5] / "content" / "dnd"


@functools.cache
def story_dnd_tables() -> DataTables:
    """The vendored 5e tables a combat story's hero is built from."""
    return load_data(DND_DATA_DIR)


@functools.cache
def hero_choices() -> tuple[frozenset[str], frozenset[str]]:
    """Races and classes a combat story's hero can start as."""
    tables = story_dnd_tables()
    return frozenset(table(tables, "races")), frozenset(table(tables, "classes"))


def validate_draft(payload: DraftPayload) -> list[str]:
    """Structural issues; empty means creatable (preset pins resolve later)."""
    issues: list[str] = []
    keys = [member.instance_key for member in payload.cast]
    if len(set(keys)) != len(keys):
        issues.append("cast instance keys must be unique")
    if not payload.cast:
        issues.append("select at least one character")
    if payload.mode.role not in VALID_ROLES:
        issues.append(f"unknown role: {payload.mode.role}")
    if payload.mode.role == "player":
        if not payload.mode.controlled_cast_key:
            issues.append("player mode needs a controlled cast member")
        elif payload.mode.controlled_cast_key not in keys:
            issues.append("controlled character is not in the cast")
    for member in payload.cast:
        if not member.name.strip():
            issues.append(f"cast member {member.instance_key} needs a name")
    adventure = payload.mode.adventure
    if adventure is not None and payload.mode.role == "player":
        races, classes = hero_choices()
        if adventure.race not in races:
            issues.append(f"unknown people for the hero: {adventure.race}")
        if adventure.character_class not in classes:
            issues.append(f"unknown calling for the hero: {adventure.character_class}")
    elif adventure is not None and (
        adventure.race is not None or adventure.character_class is not None
    ):
        # A watched party: each member's calling comes from their own card.
        issues.append("a watched party's callings come from the cast, not the draft")
    return issues
