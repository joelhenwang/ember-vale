"""A character's journey: what they have seen and done, and the renown it earns.

Counted from the world's own records (scenes taken part in, attempts the
resolver judged, rumours settled), never invented. Renown is the game's
sense of progress: each new place, new face, deed and settled rumour
moves it, and levels come at growing intervals.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Renown per kind of milestone.
POINTS = {"places": 2, "people": 2, "deeds": 3, "settled": 5}
#: Level titles, from the first step onward; the last repeats.
TITLES = (
    "Newcomer",
    "Familiar face",
    "Trusted hand",
    "Name on every lip",
    "Hero of the vale",
    "Legend",
)


@dataclass(frozen=True)
class Journey:
    places: int
    people: int
    deeds: int
    settled: int

    @property
    def renown(self) -> int:
        return (
            self.places * POINTS["places"]
            + self.people * POINTS["people"]
            + self.deeds * POINTS["deeds"]
            + self.settled * POINTS["settled"]
        )


def level_floor(level: int) -> int:
    """Renown needed for a level: 0, 10, 30, 60, 100, ... (10 x triangular)."""
    return 10 * (level - 1) * level // 2


def level_for(renown: int) -> int:
    level = 1
    while renown >= level_floor(level + 1):
        level += 1
    return level


def title_for(level: int) -> str:
    return TITLES[min(level, len(TITLES)) - 1]
