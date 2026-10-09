"""A party member's own plain attack or spell becomes a roll (combat-depth-002).

The storyteller tags blows, but live it often forgets: one fight in three
rolled nothing although the player wrote "I attack the goblin". So the
game reads the hero's own words too. A deed is the attempt a party member
made this scene (the player's "Do" line); when it plainly attacks or casts
and the storyteller did not tag that member, the matching tag line is
added before the rolls, so the dice follow the player and never the prose.

Only what the words say: a weapon or spell on the sheet that they name
(else the first weapon that suits the verb), and a foe of the fight that
is on or one the scene opened (else, when no fight is on, a creature both
the player and the storyteller named, which then opens one). A negated
or stood-down line ("I lower my bow", "I don't attack") is no deed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from worldsim.domain.rules.dnd.core import find_entry
from worldsim.domain.rules.dnd.data import DataTables, entry, str_field, table
from worldsim.domain.rules.dnd.sheets import Sheet
from worldsim.domain.rules.dnd.tags import parse_attack_tag, parse_cast_tag


@dataclass(frozen=True)
class Deed:
    """What a party member tried this scene, in their own words."""

    #: The member's party name key (``slugify(name)``).
    key: str
    text: str


_VERBS = (
    "attack|strike|hit|slash|stab|swing|lunge|shoot|shot|fire|loose|cut|smite|charge|"
    "punch|kick|fight|cleave|thrust|hurl|throw|bash|stick|skewer|hack|cast|blast"
)
_ATTACK_RE = re.compile(rf"\b(?:{_VERBS})(?:s|es|ed|ing)?\b", re.IGNORECASE)
_RANGED_RE = re.compile(
    r"\b(?:shoot|shot|fire|loose|arrow|bow|bolt|crossbow|sling|throw|hurl)", re.IGNORECASE
)
#: Words that stand the deed down: no roll.
_STAND_DOWN_RE = re.compile(
    r"\b(?:don'?t|do not|won'?t|will not|never|refuse|stop|instead of|sheathe|lower|"
    r"put away|holster|pretend|threaten|feint)\b",
    re.IGNORECASE,
)
_GENERIC = {
    "sword": ("sword", "rapier", "scimitar"),
    "blade": ("sword", "rapier", "scimitar", "dagger"),
    "bow": ("bow",),
    "arrow": ("bow",),
    "bolt": ("crossbow",),
    "axe": ("axe",),
    "knife": ("dagger",),
    "dagger": ("dagger",),
    "mace": ("mace",),
    "staff": ("quarterstaff",),
    "spear": ("spear",),
    "hammer": ("hammer",),
    "club": ("club",),
}
_ENCOUNTER_RE = re.compile(r"^\s*ENCOUNTER\s*\[[^\]]+\][^\n]*\n?", re.IGNORECASE | re.MULTILINE)
_SHEET_TAG_RE = re.compile(r"^\s*(ATTACK|CAST)\s*\[([^\]]+)\]", re.IGNORECASE | re.MULTILINE)
_ORDINALS = "first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"


def _named(text: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name.lower())}s?\b", text.lower()) is not None


def _carrier(order: list[Sheet], loadout: str, index: str) -> Sheet | None:
    return next(
        (s for s in order if index in (s.weapons if loadout == "weapon" else s.spells)), None
    )


def tagged_members(text: str, order: list[Sheet], tables: DataTables) -> set[str]:
    """Names of the party members the storyteller already tagged acting."""
    acted: set[str] = set()
    for match in _SHEET_TAG_RE.finditer(text):
        kind, inner = match.group(1).upper(), match.group(2)
        if kind == "ATTACK":
            tag = parse_attack_tag(inner, tables)
            if tag is not None and tag.index:
                sheet = _carrier(order, "weapon", tag.index)
                if sheet is not None:
                    acted.add(sheet.name)
        else:
            tag = parse_cast_tag(inner, tables)
            if tag is not None and tag.index:
                sheet = _carrier(order, "spell", tag.index)
                if sheet is not None:
                    acted.add(sheet.name)
    return acted


def _spell_named(text: str, sheet: Sheet, tables: DataTables) -> str | None:
    spells = table(tables, "spells")
    named = [
        index
        for index in sheet.spells
        if (name := str_field(entry(spells, index), "name")) and _named(text, name)
    ]
    return max(named, key=lambda i: len(i)) if named else None


def _weapon_for(text: str, sheet: Sheet, tables: DataTables) -> str | None:
    weapons = table(tables, "weapons")
    if not sheet.weapons:
        return None
    for index in sheet.weapons:
        if _named(text, str_field(entry(weapons, index), "name") or index):
            return index
    lowered = text.lower()
    for word, fits in _GENERIC.items():
        if re.search(rf"\b{word}s?\b", lowered):
            for index in sheet.weapons:
                if any(fit in index for fit in fits):
                    return index
    ranged = _RANGED_RE.search(text) is not None
    for index in sheet.weapons:
        if (str_field(entry(weapons, index), "weapon_range") == "Ranged") == ranged:
            return index
    return sheet.weapons[0]


def _foe_phrase(text: str, kind: str, label: str) -> str | None:
    """How the words name a foe of this kind: ``goblin 2``, ``the second
    goblin``, or just the kind (the first one standing)."""
    names = {label.lower(), kind.replace("-", " ")}
    for name in sorted(names, key=len, reverse=True):
        pattern = (
            rf"\b(?:(?:{_ORDINALS}|\d+(?:st|nd|rd|th))\s+)?{re.escape(name)}s?"
            rf"(?:\s*(?:#|no\.?\s*|number\s+)?\d+)?\b"
        )
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            return found.group(0).strip()
    return None


def _creature_named(text: str, prose: str, tables: DataTables) -> tuple[str, str] | None:
    """A creature both the words and the storyteller's prose name: (kind, name)."""
    best: tuple[str, str] | None = None
    monsters = table(tables, "monsters")
    for index in monsters:
        name = str_field(entry(monsters, index), "name") or index
        if _named(text, name) and _named(prose, name):
            if best is None or len(name) > len(best[1]):
                best = (index, name)
    return best


def deed_lines(
    text: str,
    deeds: list[Deed],
    order: list[Sheet],
    keys: list[str],
    tables: DataTables,
    foes: list[tuple[str, str]],
) -> tuple[str, int]:
    """The narration with the deeds' tag lines added, and how many were.

    ``foes`` are the kinds standing in the fight that is on or opened in
    this scene, as (kind, name), in order. Lines go right after the
    scene's first ENCOUNTER line (else at the start)."""
    if not deeds:
        return text, 0
    acted = tagged_members(text, order, tables)
    lines: list[str] = []
    opened: list[str] = []
    spells = table(tables, "spells")
    for deed in deeds:
        if deed.key not in keys:
            continue
        sheet = order[keys.index(deed.key)]
        words = deed.text
        if sheet.name in acted or _STAND_DOWN_RE.search(words):
            continue
        spell = _spell_named(words, sheet, tables)
        if spell is None and not _ATTACK_RE.search(words):
            continue
        spell_row = entry(spells, spell) if spell else {}
        if spell and spell_row.get("heal") and not spell_row.get("damage"):
            mate = next((s.name for s in order if _named(words, s.name)), sheet.name)
            lines.append(f"CAST[{spell} on {mate}]: {sheet.name} casts at {mate}'s word.")
            continue
        target: str | None = None
        for kind, label in foes:
            target = _foe_phrase(words, kind, label)
            if target:
                break
        if target is None and foes:
            target = foes[0][1]
        if target is None:
            found = _creature_named(words, text, tables)
            if found is None:
                continue
            kind, label = found
            opened.append(f"ENCOUNTER[{label}]: {label} turns on {sheet.name}.")
            foes = [(kind, label)]
            target = label
        if spell:
            lines.append(f"CAST[{spell} at {target}]: {sheet.name} casts.")
            continue
        weapon = _weapon_for(words, sheet, tables)
        if weapon is None or find_entry(table(tables, "weapons"), weapon) is None:
            continue
        lines.append(f"ATTACK[{weapon} at {target}]: {sheet.name} attacks.")
    if not lines:
        return text, 0
    block = "\n".join([*opened, *lines]) + "\n"
    first = _ENCOUNTER_RE.search(text)
    if first is None:
        return block + text, len(lines)
    cut = first.end()
    head = text[:cut] if text[:cut].endswith("\n") else text[:cut] + "\n"
    return head + block + text[cut:], len(lines)
