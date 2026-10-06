"""Ground a player's free-form "Do" in the rules when it plainly travels.

An interact attempt is judged, never executed: "carry two cups out toward
the market" succeeded, the narrator walked Wren to the Market, and the
map still had Wren at the Hearth. When the words head *to* a place one
route away, the attempt becomes that move, and the words ride along as
the move's note for the narrator. Anything less plain stays an attempt.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from uuid import UUID

from worldsim.domain.commands import InteractAction, MoveAction

#: Words that put a place after them as a destination.
_TOWARD = r"(?:to|toward|towards|into|for|back to|over to|down to|up to|down|along)"


def destination_named(attempt: str, reachable: Mapping[UUID, str]) -> UUID | None:
    """The one reachable place the words head toward, else None."""
    text = " ".join(attempt.lower().split())
    hits = [
        place_id
        for place_id, name in reachable.items()
        if re.search(rf"\b{_TOWARD}\s+(?:the\s+)?{re.escape(name.lower())}\b", text)
    ]
    return hits[0] if len(hits) == 1 else None


def grounded_move(action: InteractAction, reachable: Mapping[UUID, str]) -> MoveAction | None:
    """The move an attempt plainly describes, carrying the attempt as its note."""
    if action.target_character_id is not None or action.item_instance_id is not None:
        return None
    destination = destination_named(action.attempt, reachable)
    if destination is None:
        return None
    return MoveAction(
        character_id=action.character_id,
        snapshot_id=action.snapshot_id,
        destination_location_id=destination,
        note=action.attempt,
    )
