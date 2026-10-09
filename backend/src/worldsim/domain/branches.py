"""Branching a story from an earlier turn (checkpoints and provenance).

A checkpoint is the story's changeable state at the end of one turn (where
people stand, stamina, items, rumours, relationships, intentions, the
clock...) plus the event cursor it pairs with. History that is only ever
added to (events, scenes, narration, observations, memories, summaries) is
not repeated in it: a branch copies that history up to the turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from worldsim.domain.time import PHASES_PER_DAY, phase_label

#: Bumped when the checkpoint document's shape changes incompatibly.
CHECKPOINT_SCHEMA_VERSION = 1

#: A story keeps the checkpoint of every one of its newest turns ...
KEEP_RECENT_TURNS = 200
# ... and, before those, only the turn that ends each day (rewind-001).

_FROM_SUFFIX = re.compile(r"\s+—\s+(from Day \d+, \w+|the path not taken \(Day \d+, \w+\))$")


def ends_a_day(absolute_index: int) -> bool:
    """The turn that ends a day (midnight): its checkpoint is always kept."""
    return absolute_index % PHASES_PER_DAY == PHASES_PER_DAY - 1


def keeps_turn(absolute_index: int, latest: int, recent: int | None = None) -> bool:
    """Whether a story whose newest kept turn is ``latest`` keeps this turn's checkpoint."""
    window = KEEP_RECENT_TURNS if recent is None else recent
    return absolute_index > latest - window or ends_a_day(absolute_index)


@dataclass(frozen=True)
class CheckpointHead:
    """One kept turn: its index and the last event sequence it covers."""

    absolute_index: int
    event_sequence: int
    schema_version: int


@dataclass(frozen=True)
class StoryBranchOrigin:
    """Where a branched story came from."""

    world_id: UUID
    source_world_id: UUID
    source_index: int
    source_title: str
    created_at: datetime


@dataclass(frozen=True)
class BranchCopy:
    """What a branch copy wrote: the new story and how ids were renamed."""

    world_id: UUID
    #: source id (str) -> branch id (str), for every renamed id
    remap: dict[str, str]
    rows: int


def branch_title(source_title: str, absolute_index: int) -> str:
    """A branch's title, e.g. The Saltreach — from Day 2, evening.

    A branch of a branch keeps one suffix, the newest.
    """
    return _titled(source_title, f" — from {phase_label(absolute_index)}")


def path_not_taken_title(source_title: str, latest_index: int) -> str:
    """The story that keeps the turns a rewind removes.

    e.g. The Saltreach — the path not taken (Day 3, dusk), named after the
    turn that path ends at.
    """
    return _titled(source_title, f" — the path not taken ({phase_label(latest_index)})")


def _titled(source_title: str, suffix: str) -> str:
    base = _FROM_SUFFIX.sub("", source_title.strip()) or "Story"
    return base[: 128 - len(suffix)].rstrip() + suffix
