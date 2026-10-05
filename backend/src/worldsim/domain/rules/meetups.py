"""Meet-ups: two characters heading for each other should meet, not swap.

Decisions are made simultaneously from one snapshot. When A moves to
B's place while B moves to A's place, both arrive where the other used
to be and they pass each other on the road. This rule keeps one of
them in place, watching for the other's arrival, so they meet.

Only autonomous decisions are changed: a player's or a director's
directed attempt is never rewritten. Pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from worldsim.domain.commands import MoveAction, ObserveAction
from worldsim.domain.scenes import Intent

#: Idempotency-key prefix of a decision the character model made itself.
AUTONOMOUS_PREFIX = "character:"


def _autonomous(intent: Intent) -> bool:
    return intent.idempotency_key.startswith(AUTONOMOUS_PREFIX)


def resolve_meetups(
    intents: Sequence[Intent],
    locations: Mapping[UUID, UUID],
    names: Mapping[UUID, str],
) -> list[Intent]:
    """Intents with crossing moves turned into one move plus one wait-and-watch.

    The character who stays is the autonomous one when only one is
    autonomous, otherwise the one whose id sorts first. Each character
    is part of at most one meet-up.
    """
    by_actor = {i.author_character_id: i for i in intents}
    stays: dict[UUID, UUID] = {}  # stayer -> the one coming to them
    for actor in sorted(by_actor, key=lambda a: a.hex):
        mine = by_actor[actor]
        if actor in stays or actor in stays.values():
            continue
        if not isinstance(mine.action, MoveAction):
            continue
        for other in sorted(by_actor, key=lambda a: a.hex):
            if other == actor or other in stays or other in stays.values():
                continue
            theirs = by_actor[other]
            if not isinstance(theirs.action, MoveAction):
                continue
            here, there = locations.get(actor), locations.get(other)
            if here is None or there is None or here == there:
                continue
            if (
                mine.action.destination_location_id != there
                or theirs.action.destination_location_id != here
            ):
                continue
            candidates = [i for i in (mine, theirs) if _autonomous(i)]
            if not candidates:
                continue
            stayer = min(candidates, key=lambda i: i.author_character_id.hex)
            mover = theirs if stayer is mine else mine
            stays[stayer.author_character_id] = mover.author_character_id
            break
    result: list[Intent] = []
    for intent in intents:
        coming = stays.get(intent.author_character_id)
        if coming is None:
            result.append(intent)
            continue
        result.append(
            intent.model_copy(
                update={
                    "action": ObserveAction(
                        character_id=intent.author_character_id,
                        snapshot_id=intent.snapshot_id,
                        focus=f"watching for {names.get(coming, 'a companion')} to arrive",
                    )
                }
            )
        )
    return result
