"""A character's current intention: one canonical line, rewritten as plans change.

Decisions and reactions may state what the character means to do next
("walk to the market with Wren"). The latest statement replaces the
previous one, so the next decision sees the plan it agreed to instead of
re-deriving it from raw observations.
"""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from worldsim.domain.ids import CharacterId, WorldId
from worldsim.domain.time import utcnow

MAX_INTENTION_CHARS = 200


class CharacterIntention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: CharacterId
    world_id: WorldId
    text: str = Field(min_length=1, max_length=MAX_INTENTION_CHARS)
    set_phase_index: int = Field(ge=0)
    updated_at: AwareDatetime = Field(default_factory=utcnow)


def extract_intention(raw: str | None) -> str | None:
    """The optional ``intention`` field of a decision or reaction output."""
    if not raw:
        return None
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    value = cast("dict[str, Any]", parsed).get("intention")
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:MAX_INTENTION_CHARS] or None


def card_drives(personality: str) -> list[str]:
    """Studio drive lines ("Wants: ...", "Avoids: ...") packed into a card."""
    prefixes = ("Wants:", "Avoids:", "Under pressure:")
    return [
        line.strip()
        for line in personality.splitlines()
        if line.strip().startswith(prefixes) and len(line.strip()) > len("Wants:") + 1
    ]


__all__ = ["CharacterIntention", "card_drives", "extract_intention"]


#: How many of a character's own latest turns a streak note looks at.
STREAK_TURNS = 3
_TALK = frozenset({"communicate"})
_IDLE = frozenset({"wait", "observe", "rest"})


def streak_note(families: list[str], intention: str | None) -> str | None:
    """A nudge when a character's own last turns were all talk or all idling.

    Characters coordinating a job ("heave on three") kept telling each
    other to do it, turn after turn, and nobody did: only 3% of their
    choices acted on the world. Families are newest first.
    """
    recent = families[:STREAK_TURNS]
    if len(recent) < STREAK_TURNS:
        return None
    if all(f in _TALK for f in recent):
        return (
            f"You have only talked for your last {STREAK_TURNS} turns. Talking about a job "
            "does not do it: if something needs doing, do it now (interact, move, take or "
            "transfer), or talk about something new."
        )
    if intention and all(f in _IDLE for f in recent):
        return (
            f"You have waited or watched for your last {STREAK_TURNS} turns while you mean "
            f"to: {intention} Act on it now if you can."
        )
    return None
