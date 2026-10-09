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
_ATTACK_RE = re.compile(
    rf"\b(?:(?:{_VERBS})(?:s|es|ed|ing)?|go(?:es)? (?:after|for)|takes? on|"
    r"finish(?:es)? off|engage[sd]?|rush(?:es)?|tackle[sd]?|swipe[sd]?|jab(?:s|bed)?)\b",
    re.IGNORECASE,
)
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


def looks_like_deed(text: str) -> bool:
    """Words that plainly attack or cast (the dice, not the resolver, decide)."""
    return bool(_ATTACK_RE.search(text)) and not _STAND_DOWN_RE.search(text)


def _named(text: str, name: str) -> bool:
    """The text names this (one of them, or several: "wolf", "wolves")."""
    forms = {re.escape(name.lower()) + "s?", re.escape(_plural(name))}
    return re.search(rf"\b(?:{'|'.join(forms)})\b", text.lower()) is not None


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


_COUNT_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "a pair of": 2,
    "a couple of": 2,
    "both": 2,
}
_MAX_OPENED = 6


def _plural(name: str) -> str:
    low = name.lower()
    if low.endswith("f"):
        return low[:-1] + "ves"
    if low.endswith("y") and low[-2:-1] not in "aeiou":
        return low[:-1] + "ies"
    if low.endswith(("s", "x", "ch", "sh")):
        return low + "es"
    return low + "s"


def group_size(texts: list[str], name: str) -> int:
    """How many of a creature the words count ("two goblins", "a pair of
    wolves", "3 bandits"); 1 when they do not say."""
    counted = "|".join(sorted((re.escape(w) for w in _COUNT_WORDS), key=len, reverse=True))
    pattern = re.compile(
        rf"\b({counted}|\d+)\s+(?:[a-z'-]+\s+){{0,2}}?{re.escape(_plural(name))}\b", re.IGNORECASE
    )
    best = 1
    for text in texts:
        for found in pattern.finditer(text):
            word = found.group(1).lower()
            size = int(word) if word.isdigit() else _COUNT_WORDS.get(word, 1)
            best = max(best, min(size, _MAX_OPENED))
    return best


def opening_lines(
    text: str,
    deeds: list[Deed],
    order: list[Sheet],
    tables: DataTables,
    fallen: set[str],
) -> list[str]:
    """ENCOUNTER lines for a fight the scene starts without one: no fight is
    on and no ENCOUNTER was written, yet the storyteller's tags strike a
    creature, or a party member's words attack one the prose names. The
    group is as large as the words count ("two goblins": Goblin 1 and 2), so
    "the second goblin" is a real foe. A kind already slain opens nothing."""
    if _ENCOUNTER_RE.search(text):
        return []
    monsters = table(tables, "monsters")
    party = {sheet.name.lower() for sheet in order}
    kinds: list[tuple[str, str]] = []
    #: Kinds the storyteller struck: a lone one needs no opening (the engine
    #: meets it as it is struck), a group does.
    struck: set[str] = set()
    for match in _SHEET_TAG_RE.finditer(text):
        kind_word, inner = match.group(1).upper(), match.group(2)
        tag = parse_attack_tag(inner, tables) if kind_word == "ATTACK" else None
        target = tag.target if tag is not None else None
        if kind_word == "CAST":
            cast_tag = parse_cast_tag(inner, tables)
            target = cast_tag.target if cast_tag is not None else None
        if not target or target.strip().lower() in party:
            continue
        found = find_entry(monsters, re.sub(r"\s*(?:#|no\.?\s*)?\d+$", "", target))
        if found is not None:
            kinds.append((found.index, str_field(found.entry, "name") or found.index))
            struck.add(found.index)
    for deed in deeds:
        if _ATTACK_RE.search(deed.text) and not _STAND_DOWN_RE.search(deed.text):
            named = _creature_named(deed.text, text, tables)
            if named is not None:
                kinds.append(named)
                struck.discard(named[0])
    words = [text, *(deed.text for deed in deeds)]
    lines: list[str] = []
    for kind, name in dict.fromkeys(kinds):
        if kind in fallen:
            continue
        size = group_size(words, name)
        if size == 1 and kind in struck:
            continue
        count = f"{size}x " if size > 1 else ""
        lines.append(f"ENCOUNTER[{count}{name}]: {name} turns on the party.")
    return lines


def deed_lines(
    text: str,
    deeds: list[Deed],
    order: list[Sheet],
    keys: list[str],
    tables: DataTables,
    foes: list[tuple[str, str]],
    fallen: set[str] | None = None,
) -> tuple[str, int]:
    """The narration with the deeds' tag lines added, and how many were.

    ``foes`` are the kinds standing in the fight that is on or opened in
    this scene, as (kind, name), in order. ``fallen`` are kinds already
    slain in this story: the words alone never bring one back (only the
    storyteller's ENCOUNTER does). Lines go right after the scene's first
    ENCOUNTER line (else at the start)."""
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
        down = sheet.hp is not None and sheet.hp.current <= 0
        if down or sheet.name in acted or _STAND_DOWN_RE.search(words):
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
            if found is None or found[0] in (fallen or set()):
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


def after_encounter(text: str, lines: list[str]) -> str:
    """The narration with tag lines put right after its first ENCOUNTER line
    (else at the start), where the scene's fight begins."""
    if not lines:
        return text
    block = "\n".join(lines) + "\n"
    first = _ENCOUNTER_RE.search(text)
    if first is None:
        return block + text
    cut = first.end()
    head = text[:cut] if text[:cut].endswith("\n") else text[:cut] + "\n"
    return head + block + text[cut:]


def helper_lines(
    text: str,
    order: list[Sheet],
    keys: list[str],
    helpers: set[str],
    deed_keys: set[str],
    foes: list[tuple[str, str]],
    tables: DataTables,
) -> list[str]:
    """Companions here fight beside the party (companions-001): each one
    standing whom neither the storyteller nor their own words had act
    strikes the first foe standing, with their first weapon (a caster
    without one, their first damaging cantrip)."""
    if not foes or not helpers:
        return []
    acted = tagged_members(text, order, tables)
    spells = table(tables, "spells")
    target = foes[0][1]
    lines: list[str] = []
    for key in keys:
        sheet = order[keys.index(key)]
        down = sheet.hp is not None and sheet.hp.current <= 0
        if key not in helpers or key in deed_keys or down or sheet.name in acted:
            continue
        if sheet.weapons:
            lines.append(f"ATTACK[{sheet.weapons[0]} at {target}]: {sheet.name} fights on.")
            continue
        cantrip = next(
            (
                spell
                for spell in sheet.spells
                if (row := entry(spells, spell)).get("damage") and not row.get("level")
            ),
            None,
        )
        if cantrip is not None:
            lines.append(f"CAST[{cantrip} at {target}]: {sheet.name} fights on.")
    return lines
