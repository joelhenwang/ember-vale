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
