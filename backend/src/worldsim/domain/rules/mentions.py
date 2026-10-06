"""Places people talk about that are not on the map.

Characters invent destinations in conversation ("Dryden's mill", "the old
forge") and then try to go there; with no such place they wander or
stall. This finds place words in recent speech, attempts and intentions,
keeps the ones no existing place matches, and counts them, so the
director can decide whether to make one real. Pure and deterministic.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

#: Nouns that name a place someone could walk to.
PLACE_NOUNS = frozenset(
    {
        "mill", "forge", "smithy", "cave", "caves", "shrine", "temple", "chapel",
        "tavern", "inn", "dock", "docks", "harbor", "harbour", "bridge", "well",
        "farm", "orchard", "tower", "ruins", "bakery", "stable", "stables", "barn",
        "quarry", "mine", "woods", "forest", "grove", "lake", "river", "stream",
        "crossroads", "square", "keep", "castle", "manor", "library", "workshop",
        "warehouse", "camp", "hut", "cottage", "lighthouse", "graveyard",
        "cemetery", "field", "fields", "pasture", "spring", "falls", "glade",
        "fountain", "plaza", "gate", "gates", "pier", "hall", "garden", "gardens",
        "bathhouse", "guildhall", "watchtower", "ford", "hill", "meadow",
    }
)  # fmt: skip
#: Words that may sit in front of a place noun as part of its name.
_DESCRIPTORS = frozenset(
    {
        "old", "new", "north", "south", "east", "west", "northern", "southern",
        "eastern", "western", "upper", "lower", "little", "great", "abandoned",
        "ruined", "broken", "burned", "hidden", "haunted", "high", "far", "near",
    }
)  # fmt: skip
_WORD = re.compile(r"[A-Za-z][A-Za-z']*")


def _phrases(text: str) -> list[str]:
    words = _WORD.findall(text)
    found: list[str] = []
    for index, word in enumerate(words):
        if word.lower() not in PLACE_NOUNS:
            continue
        name = [word.lower()]
        cursor = index - 1
        while cursor >= 0 and len(name) < 3:
            prior = words[cursor]
            lower = prior.lower()
            if lower.endswith("'s") or lower in _DESCRIPTORS:
                name.insert(0, prior if lower.endswith("'s") else lower)
                cursor -= 1
                continue
            break
        found.append(" ".join(name))
    return found


def _known(phrase: str, place_names: Iterable[str]) -> bool:
    noun = phrase.split()[-1].rstrip("s")
    for place in place_names:
        lowered = place.lower()
        if noun in lowered or lowered in phrase.lower():
            return True
    return False


def unmapped_places(
    texts: Iterable[str], place_names: Iterable[str], limit: int = 3
) -> list[tuple[str, int]]:
    """Most-mentioned place phrases with no matching place, with counts."""
    names = list(place_names)
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for text in texts:
        for phrase in _phrases(text):
            if _known(phrase, names):
                continue
            key = phrase.lower()
            counts[key] += 1
            display.setdefault(key, phrase)
    return [(display[key], count) for key, count in counts.most_common(limit)]
