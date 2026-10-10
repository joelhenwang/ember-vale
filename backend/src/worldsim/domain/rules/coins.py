"""Gold coins: one counted stack per holder, spent by plain words (coins-001).

A fallen foe may leave a handful of gold coins. Whoever picks them up adds
them to the purse they already carry, and a successful attempt that pays
("I pay the innkeeper 3 gold coins", "hand her a coin") takes that many from
the purse: to the person it is aimed at, else spent.
"""

from __future__ import annotations

import re

#: The catalog-free key every purse shares, so stacks can merge.
COINS_KEY = "gold-coins"
COINS_NAME = "gold coins"

_NUMBERS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "twenty": 20,
}
_PAY = re.compile(
    r"\b(?:pay|pays|paying|paid|give|gives|giving|hand|hands|handing|spend|spends|"
    r"spending|toss|tosses|slide|slides|count out|press|presses|buy|buys)\b"
    r"(?:[^.;!?]*?)\b(\d{1,3}|"
    + "|".join(_NUMBERS)
    + r")\s+(?:gold\s+|silver\s+|copper\s+)?(?:coins?|gold pieces?|gp)\b",
    re.IGNORECASE,
)
_NOT_PAYING = re.compile(
    r"\b(?:don'?t|do not|won'?t|will not|refuse|pretend|if you|would you|promise)\b",
    re.IGNORECASE,
)


def coins_paid(words: str) -> int | None:
    """How many coins the words pay, or None when they pay none."""
    found = _PAY.search(words)
    if found is None or _NOT_PAYING.search(words):
        return None
    said = found.group(1).lower()
    count = int(said) if said.isdigit() else _NUMBERS[said]
    return count if count > 0 else None
