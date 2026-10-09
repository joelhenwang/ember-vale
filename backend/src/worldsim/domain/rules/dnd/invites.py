"""Asking someone to join the party, and their answer (companions-001).

Live, the storyteller recruited no one: the hero asked Ash twice to "join me
as my companion" and Ash answered "I'll consider your offer" both times,
since nothing told Ash that joining was a real choice to make now. So an
invitation is read from the hero's own words, the invited character is told
to answer it plainly, and a plain yes is a join (the game recruits; the
storyteller's RECRUIT tag still works too). Anything hedged is not a yes.
"""

from __future__ import annotations

import re

from worldsim.domain.rules.dnd.data import DataTables, entry, table
from worldsim.domain.rules.dnd.sheets import Sheet

_INVITE_RE = re.compile(
    r"\b(?:join (?:me|us|my party|our party|the party|my company|my side)|"
    r"(?:be|become) (?:my|our) (?:companion|ally|comrade)|"
    r"(?:travel|come|ride|adventure|journey) (?:along )?with (?:me|us)|"
    r"fight (?:at|by|beside) (?:my|our) side|fight beside (?:me|us)|"
    r"(?:my|our|a) (?:travelling |traveling )?companion|share the road)\b",
    re.IGNORECASE,
)
_YES_RE = re.compile(
    r"\b(?:yes|aye|gladly|count me in|i(?:'m| am) with you|i accept|lead the way|"
    r"i(?:'ll| will) (?:come|join|go|travel|ride|fight)|very well|so be it|agreed|deal)\b",
    re.IGNORECASE,
)
_NOT_YET_RE = re.compile(
    r"\b(?:no|not|never|can'?t|cannot|won'?t|later|consider|think (?:it )?over|"
    r"think about|maybe|perhaps|first|unless|until|once i|after i|discuss)\b",
    re.IGNORECASE,
)

#: Plain callings in a character's card, mapped to a 5e class.
_CALLINGS: dict[str, tuple[str, ...]] = {
    "wizard": ("wizard", "mage", "scholar", "sorcer", "arcan", "alchemist"),
    "cleric": ("cleric", "priest", "priestess", "healer", "acolyte", "temple", "monk of"),
    "rogue": ("rogue", "thief", "pickpocket", "smuggler", "spy", "cutpurse", "scout"),
    "ranger": ("ranger", "hunter", "archer", "tracker", "woodsman", "trapper"),
    "bard": ("bard", "minstrel", "singer", "storyteller", "musician", "poet"),
    "druid": ("druid", "herbalist", "witch"),
    "paladin": ("paladin", "templar", "crusader"),
    "barbarian": ("barbarian", "berserker", "raider"),
    "monk": ("monk",),
    "warlock": ("warlock", "pact"),
    "fighter": ("fighter", "soldier", "guard", "knight", "warrior", "mercenary", "sword"),
}


def is_invitation(words: str) -> bool:
    """The hero's words ask someone to join the party."""
    return bool(_INVITE_RE.search(words))


def accepts(reply: str) -> bool:
    """A plain yes to an invitation (a hedged or conditional answer is not)."""
    return bool(_YES_RE.search(reply)) and not _NOT_YET_RE.search(reply)


def invitation_note(hero: str) -> str:
    """What the invited character is told about the question in front of them."""
    return (
        f"{hero} is asking you to join their party as a travelling companion, to share "
        "the road and its fights. Decide now and answer plainly: begin your reply with "
        '"Yes, I will come" if you join, or say no and why. Choose as your character '
        "truly would."
    )


def companion_description(card_text: str, tables: DataTables) -> str:
    """'elf ranger' from a character's card: a race and calling it names,
    else human fighter (the sheet the companion fights with)."""
    low = card_text.lower()
    race = next(
        (
            key
            # Longest first: "half-elf" is not an elf.
            for key in sorted(table(tables, "races"), key=len, reverse=True)
            if re.search(rf"\b{re.escape(key)}\b", low)
        ),
        "human",
    )
    calling = next(
        (cls for cls, words in _CALLINGS.items() if any(word in low for word in words)),
        "fighter",
    )
    return f"{race} {calling}"


def companion_attack(sheet: Sheet, foe: str, tables: DataTables) -> str | None:
    """A companion's own attempt in a fight, in their words: "I attack Goblin 2
    with my longsword" (or a damaging cantrip for a caster without a weapon)."""
    if sheet.hp is not None and sheet.hp.current <= 0:
        return None
    weapons, spells = table(tables, "weapons"), table(tables, "spells")
    if sheet.weapons:
        name = str(entry(weapons, sheet.weapons[0]).get("name", sheet.weapons[0]))
        return f"I attack {foe} with my {name.lower()}"
    for key in sheet.spells:
        row = entry(spells, key)
        if row.get("damage") and not row.get("level"):
            return f"I cast {str(row.get('name', key)).lower()} at {foe}"
    return None
