"""A joining companion's people and calling, suggested by the writing model.

The keywords in ``companion_description`` find a calling only when the card
names one, so the built-in Ash ("Steady stance, weather-worn cloak. Patient,
dry-witted, dependable.") was always a human fighter, beside a fighter hero.
The small writing model reads the card and the party and names one race and
one class from the SRD tables that fit the character and, all else equal,
fill a gap in the party (about $0.0001 a join). Anything unusable (no
writer, a failed call, an answer outside the tables) falls back to the
keywords: a join never fails for want of a suggestion. The player may
still change it before the companion's first fight (``change_calling``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from worldsim.application.ports.writer import Writer, WritingError
from worldsim.domain.characters import CharacterCard
from worldsim.domain.party import PartyMember
from worldsim.domain.rules.dnd import DataTables
from worldsim.domain.rules.dnd.data import table
from worldsim.domain.rules.dnd.invites import companion_description

_log = logging.getLogger("worldsim.callings")

#: What the writing model is asked when someone joins the party.
CALLING_PROMPT = """Someone is joining an adventuring party in a fantasy story. Choose their \
people and calling. Answer with JSON only, no other text:
{{"race": "", "class": ""}}

- race: one of {races}. What the card says or suggests; human when nothing does.
- class: one of {classes}. What fits their looks, temper and past. When several fit \
equally, choose one the party lacks.

The party now: {party}

{name}{pronouns}
Looks: {appearance}
Temper: {personality}
Past: {background}"""

#: Card characters sent per field (cards run 50-600).
_FIELD_CHARS = 500


@dataclass(frozen=True)
class Calling:
    race: str
    character_class: str

    @property
    def description(self) -> str:
        """'elf ranger': what ``recruit_companion`` builds the sheet from."""
        return f"{self.race} {self.character_class}"


def _clip(text: str, limit: int = _FIELD_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def calling_prompt(card: CharacterCard, party: Sequence[PartyMember], tables: DataTables) -> str:
    members = ", ".join(
        f"{m.name} ({m.sheet.race + ' ' if m.sheet.race else ''}{m.sheet.character_class})"
        for m in party
    )
    return CALLING_PROMPT.format(
        races=", ".join(sorted(table(tables, "races"))),
        classes=", ".join(sorted(table(tables, "classes"))),
        party=members or "nobody yet",
        name=card.name,
        pronouns=f" ({card.pronouns})" if card.pronouns.strip() else "",
        appearance=_clip(card.appearance) or "unknown",
        personality=_clip(card.personality) or "unknown",
        background=_clip(card.background) or "unknown",
    )


def parse_calling(text: str, tables: DataTables) -> Calling | None:
    """The writer's JSON answer, or None unless both keys are in the tables."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        raw: object = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    fields: dict[str, object] = {str(k): v for k, v in raw.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    race = str(fields.get("race") or "").strip().lower().replace(" ", "-")
    calling = str(fields.get("class") or fields.get("character_class") or "").strip().lower()
    if race not in table(tables, "races") or calling not in table(tables, "classes"):
        return None
    return Calling(race=race, character_class=calling)


def _card_words(card: CharacterCard) -> str:
    return " ".join([card.appearance, card.personality, card.background])


async def suggest_calling(
    writer: Writer | None,
    card: CharacterCard,
    party: Sequence[PartyMember],
    tables: DataTables,
) -> str:
    """'elf ranger' for a joining companion: the writer's choice, else the
    race and calling their card names (else human fighter)."""
    fallback = companion_description(_card_words(card), tables)
    if writer is None:
        return fallback
    try:
        written = await writer.write(calling_prompt(card, party, tables))
    except WritingError:
        _log.info("calling suggestion failed", extra={"companion": card.name})
        return fallback
    chosen = parse_calling(written.text, tables)
    _log.info(
        "calling suggested",
        extra={
            "companion": card.name,
            "calling": chosen.description if chosen else None,
            "cost_usd": written.cost_usd,
        },
    )
    return chosen.description if chosen is not None else fallback
