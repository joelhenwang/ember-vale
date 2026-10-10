"""Ability checks outside fights (combat-depth-003).

In a combat story a party member's uncertain attempt that is no blow ("I
climb the wall", "I sneak past the guard", "I pick the lock") is rolled:
the words name a skill, the skill an ability, and a d20 plus that ability's
modifier meets a difficulty read from the words (easy 10, plain 12, hard
15). The roll decides: success, partial when it missed by four or less,
failure otherwise; a natural 20 always succeeds and a natural 1 fails. The
resolver is told the roll and its outcome follows it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from worldsim.domain.rules.dnd.core import ability_mod
from worldsim.domain.rules.dnd.sheets import Sheet

#: (skill, ability, words that call for it), first match wins.
SKILLS: tuple[tuple[str, str, str], ...] = (
    ("Thieves' tools", "dex", r"pick (?:the |a )?lock|lockpick|disarm (?:the |a )?trap|jimmy"),
    ("Stealth", "dex", r"sneak|creep|hide|slip past|sneaking|unseen|tiptoe"),
    (
        "Sleight of Hand",
        "dex",
        r"pickpocket|pick (?:his|her|their) pocket|palm|lift (?:the|a) purse",
    ),
    ("Acrobatics", "dex", r"balance|tumble|leap across|vault|somersault|squeeze through"),
    (
        "Athletics",
        "str",
        r"climb|lift|heave|shove|push|force (?:the |a )?(?:door|gate|lid)"
        r"|swim|jump|break down|pull (?:the|a)",
    ),
    ("Persuasion", "cha", r"persuade|convince|bargain|haggle|plead|talk (?:him|her|them) into"),
    ("Deception", "cha", r"\blie\b|bluff|deceive|trick (?:him|her|them)|pretend to be|disguise"),
    ("Intimidation", "cha", r"intimidate|threaten|scare (?:him|her|them)|menace"),
    ("Perception", "wis", r"search|look for|spot|listen|keep watch|scan the|notice"),
    ("Investigation", "int", r"examine|inspect|investigate|study the|decipher|piece together"),
    ("Insight", "wis", r"read (?:his|her|their) face|tell if .* lying|sense (?:his|her|their)"),
    ("Survival", "wis", r"track|forage|follow the trail|find the way|navigate"),
    (
        "Medicine",
        "wis",
        r"tend (?:to )?(?:the |his |her |their )?wound|bandage|treat (?:the )?wound|stabili[sz]e",
    ),
    ("Animal Handling", "wis", r"calm the (?:horse|dog|beast|animal)|soothe the|tame"),
    ("Arcana", "int", r"runes?|arcane|magic(?:al)? (?:seal|ward|symbol)"),
    ("Nature", "int", r"herbs?|identify the plant|which plants"),
    ("History", "int", r"recall the history|remember the legend|old lore"),
)
_HARD = re.compile(
    r"\b(?:sheer|steep|heavy|locked tight|well guarded|guarded|iron|stubborn|raging|"
    r"impossible|without a sound|in plain sight)\b",
    re.IGNORECASE,
)
_EASY = re.compile(r"\b(?:easy|easily|simple|gently|low|small|loose)\b", re.IGNORECASE)
PLAIN_DC, EASY_DC, HARD_DC = 12, 10, 15
#: Missed by this much or less: partial.
PARTIAL_BY = 4


@dataclass(frozen=True)
class Check:
    """One rolled ability check."""

    actor: str
    skill: str
    ability: str
    dc: int
    natural: int
    modifier: int
    total: int
    outcome: str  # success, partial, failure

    @property
    def text(self) -> str:
        return (
            f"{self.actor}'s {self.skill} check: {self.total} against DC {self.dc}, {self.outcome}."
        )


def skill_for(words: str) -> tuple[str, str] | None:
    """The skill and ability the words call for, or None (no check)."""
    for skill, ability, pattern in SKILLS:
        if re.search(pattern, words, re.IGNORECASE):
            return skill, ability
    return None


def dc_for(words: str) -> int:
    """How hard the words make it: hard 15, easy 10, else 12."""
    if _HARD.search(words):
        return HARD_DC
    if _EASY.search(words):
        return EASY_DC
    return PLAIN_DC


def roll_check(sheet: Sheet, words: str, rng: Callable[[], float]) -> Check | None:
    """Roll the check the words call for (None when they call for none)."""
    called = skill_for(words)
    if called is None:
        return None
    skill, ability = called
    dc = dc_for(words)
    natural = min(20, int(rng() * 20) + 1)
    modifier = ability_mod(sheet.stats.get(ability, 10))
    total = natural + modifier
    if natural == 20 or (natural != 1 and total >= dc):
        outcome = "success"
    elif natural != 1 and total >= dc - PARTIAL_BY:
        outcome = "partial"
    else:
        outcome = "failure"
    return Check(sheet.name, skill, ability, dc, natural, modifier, total, outcome)


def check_line(check: Check) -> str:
    """What the resolver hears: the roll, and that the outcome follows it."""
    return (
        f"Dice: {check.text} This attempt's outcome follows the roll: "
        f"{check.outcome} (success when it meets the DC, partial when it misses by "
        f"{PARTIAL_BY} or less, failure otherwise)."
    )


_RANK = {"impossible": 0, "failure": 1, "partial": 2, "success": 3}


def scene_outcome(resolver: str, checks: list[Check]) -> str:
    """How the scene's effort went once its checks are rolled.

    The dice decide (the best roll of the scene: the party helps each other),
    but the resolver can still hold it lower (what they reach for is not
    there, so it is at most partial).
    """
    if not checks:
        return resolver
    best = max(checks, key=lambda c: _RANK[c.outcome]).outcome
    return min(resolver, best, key=lambda o: _RANK.get(o, 0))
