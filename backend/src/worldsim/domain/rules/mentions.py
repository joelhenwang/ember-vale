"""Places people talk about that are not on the map.

Characters invent destinations in conversation ("Dryden's mill", "the old
forge") and then try to go there; with no such place they wander or
stall. This finds place words in recent speech, attempts and intentions,
keeps the ones no existing place matches, and counts them, so the
director can decide whether to make one real. Pure and deterministic.

When the local model service has read a line (GLiNER2.5, see
``MENTION_LABELS``), its place spans decide: a noun-list word counts
only inside a span ("keep an eye" and "forge mark" drop out). A span
also adds names the noun list cannot build ("the north road", "the
wheelwright's shop") when its last word is a kind of place
(``_PLACE_HEADS``); a bare one-word span needs a place noun, so "stall"
or "shelf" alone never becomes a new place, and "coin's edge" never
does. Lines it has not read yet use the noun list alone.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence

#: Labels sent to GLiNER. Person, item and event compete with place, so
#: names, objects and bells stop passing as places. Changing these
#: changes what is cached: bump MENTION_MODEL with them.
MENTION_LABELS: dict[str, str] = {
    "place": "A location someone could walk to: a building, landmark, stall, mill, road or area",
    "person": "A person, by name or by role",
    "item": "A physical object someone could carry, give or examine",
    "event": "Something that happens or a time, like a bell, a festival or dawn",
}
MENTION_MODEL = "gliner2.5-multi-v1/labels-1"

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
        "ridge", "cliff", "cliffs", "ravine", "valley", "marsh", "swamp", "hollow",
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
#: Last words of a named place in a model span ("the north road", "the
#: dye stalls"). Broader than PLACE_NOUNS, which also drives the plain
#: noun list, where words like "road" or "stall" alone are too common.
_PLACE_HEADS = PLACE_NOUNS | frozenset(
    {
        "road", "roads", "trail", "path", "lane", "street", "row", "alley", "way",
        "stall", "stalls", "shop", "store", "yard", "house", "market", "wharf",
    }
)  # fmt: skip


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


#: Words that open a span but are not part of a place's name.
_LEADING = frozenset(
    {
        "the",
        "a",
        "an",
        "that",
        "this",
        "my",
        "our",
        "your",
        "his",
        "her",
        "their",
        "open",
        "nearest",
    }
)


def _span_phrase(span: str, people: Sequence[str]) -> str | None:
    """A model-found place span as a phrase, or None when it is not one."""
    words = _WORD.findall(span)
    while words and words[0].lower() in _LEADING:
        words = words[1:]
    if not words:
        return None
    phrase = " ".join(w if w.lower().endswith("'s") else w.lower() for w in words)
    if any(person.lower() == phrase.lower() for person in people):
        return None
    head = words[-1].lower()
    if head not in (PLACE_NOUNS if len(words) == 1 else _PLACE_HEADS):
        return None
    return phrase


def _read_phrases(text: str, spans: Sequence[str], people: Sequence[str]) -> list[str]:
    """Place phrases in a line the model has read."""
    inside = " ".join(spans).lower()
    found = [p for p in _phrases(text) if p.split()[-1].lower() in _WORD.findall(inside.lower())]
    for span in spans:
        phrase = _span_phrase(span, people)
        if phrase is not None and phrase.lower() not in {f.lower() for f in found}:
            found.append(phrase)
    return found


def _known(phrase: str, place_names: Iterable[str]) -> bool:
    noun = phrase.split()[-1].rstrip("s")
    for place in place_names:
        lowered = place.lower()
        if noun in lowered or lowered in phrase.lower():
            return True
    return False


def unmapped_places(
    texts: Iterable[str],
    place_names: Iterable[str],
    limit: int = 3,
    *,
    read: Mapping[str, Sequence[str]] | None = None,
    people: Sequence[str] = (),
) -> list[tuple[str, int]]:
    """Most-mentioned place phrases with no matching place, with counts.

    ``read`` maps a line to the place spans the model found in it; lines
    missing from it fall back to the noun list.
    """
    names = list(place_names)
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for text in texts:
        spans = read.get(text) if read is not None else None
        phrases = _phrases(text) if spans is None else _read_phrases(text, spans, people)
        for phrase in phrases:
            if _known(phrase, names):
                continue
            key = phrase.lower()
            counts[key] += 1
            display.setdefault(key, phrase)
    return [(display[key], count) for key, count in counts.most_common(limit)]
