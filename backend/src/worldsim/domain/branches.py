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

from worldsim.domain.time import phase_label

#: Bumped when the checkpoint document's shape changes incompatibly.
CHECKPOINT_SCHEMA_VERSION = 1

_FROM_SUFFIX = re.compile(r"\s+—\s+from Day \d+, \w+$")


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

    A branch of a branch keeps one "from" suffix, the newest.
    """
    base = _FROM_SUFFIX.sub("", source_title.strip()) or "Story"
    suffix = f" — from {phase_label(absolute_index)}"
    return base[: 128 - len(suffix)].rstrip() + suffix
