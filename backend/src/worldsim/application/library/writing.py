"""Writing help for the library studios: prompts in, checked answers out.

A player sketches a character or a world in an overview, maybe only a
few key points. The writer can make that overview fuller (enhance), and
fill the fields the player left empty from it (fill), never touching
what the player already wrote. Pure: the model call is the Writer port.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, cast

Kind = Literal["character", "world"]

#: An enhanced overview stays readable at a glance.
OVERVIEW_MAX = 2000


class WritingAnswerError(ValueError):
    """The model's answer could not be read."""


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    hint: str
    value: str
    max_length: int


@dataclass(frozen=True)
class Place:
    name: str
    description: str


@dataclass(frozen=True)
class FilledPlace:
    name: str
    description: str
    #: True for a place the writer added; False fills an existing one.
    new: bool
    #: What sort of place it is, from the kinds the studio offers ("" if none fit).
    kind: str = ""


_WHAT = {
    "character": "a character for a fantasy storytelling game",
    "world": "a setting (a world with its places) for a fantasy storytelling game",
}

ENHANCE_PROMPT = """You are helping someone write {what}.
{named}Here is their overview, perhaps only rough notes:

<overview>
{overview}
</overview>

Rewrite it as a fuller overview: two or three short paragraphs of plain, vivid prose,
at most 180 words. Keep every fact they gave, and their names and tone. Where they left
gaps, add a few specific, plausible details in the same spirit; do not change anything
they decided. No headings, no lists, no quotation marks around the whole text.

Answer with JSON only: {{"text": "..."}}"""

FILL_PROMPT = """You are helping someone write {what}.
{named}Their overview:

<overview>
{overview}
</overview>
{decided}
Write the fields below that are still empty. Base them on the overview and keep them
consistent with everything already decided; never contradict it. Be concrete and brief:
each answer should fit its hint, in plain words, without repeating the field's name.

Fields to write:
{wanted}
{places}
Answer with JSON only: {{"fields": {{"key": "text", ...}}{places_shape}}}"""

PLACES_PART = """
Places{have}:
{listed}
{add}Each place gets one or two sentences: what it is and what a visitor notices there.{kinds}
"""


def _named(name: str) -> str:
    return f"It is called {name.strip()}.\n" if name.strip() else ""


def enhance_prompt(kind: Kind, overview: str, name: str = "") -> str:
    return ENHANCE_PROMPT.format(what=_WHAT[kind], named=_named(name), overview=overview.strip())


def fill_prompt(
    kind: Kind,
    overview: str,
    fields: list[Field],
    name: str = "",
    places: list[Place] | None = None,
    add_places: int = 0,
    place_kinds: list[str] | None = None,
) -> str:
    decided_fields = [f for f in fields if f.value.strip()]
    decided = ""
    if decided_fields:
        lines = "\n".join(f"- {f.label}: {f.value.strip()}" for f in decided_fields)
        decided = f"\nAlready decided (keep these as they are):\n{lines}\n"
    wanted = "\n".join(f'- "{f.key}" ({f.label}): {f.hint}' for f in fields if not f.value.strip())
    places_text, places_shape = "", ""
    places = places or []
    unwritten = [p for p in places if not p.description.strip()]
    if unwritten or add_places > 0:
        listed = "\n".join(
            f"- {p.name}: {p.description.strip() or '(not described yet: describe it)'}"
            for p in places
        )
        add = (
            f"Add {add_places} new place{'s' if add_places != 1 else ''} that belong in this "
            "world and differ from the ones above, each with a short proper name.\n"
            if add_places > 0
            else ""
        )
        kinds = (
            "\nGive each place a kind, one of: " + ", ".join(place_kinds) + "."
            if place_kinds
            else ""
        )
        places_text = PLACES_PART.format(
            have=" so far" if places else " (none yet)",
            listed=listed or "(none)",
            add=add,
            kinds=kinds,
        )
        kind_shape = ', "kind": "..."' if place_kinds else ""
        places_shape = (
            f', "places": [{{"name": "...", "description": "..."{kind_shape}}}] '
            "(the places not described yet, by their names, and any new ones)"
        )
    return FILL_PROMPT.format(
        what=_WHAT[kind],
        named=_named(name),
        overview=overview.strip() or "(none given: invent freely, in a classic fantasy spirit)",
        decided=decided,
        wanted=wanted or "(none)",
        places=places_text,
        places_shape=places_shape,
    )


def _json(text: str) -> dict[str, object]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise WritingAnswerError("the writer answered without JSON")
    try:
        data: object = json.loads(text[start : end + 1])
    except ValueError as exc:
        raise WritingAnswerError(f"the writer's JSON is broken: {exc}") from exc
    if not isinstance(data, dict):
        raise WritingAnswerError("the writer's JSON is not an object")
    return cast("dict[str, object]", data)


def _clean(value: object, limit: int) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in cast("list[object]", value))
    if not isinstance(value, str | int | float):
        return ""
    return str(value).strip()[:limit].strip()


def parse_enhanced(text: str) -> str:
    found = _clean(_json(text).get("text"), OVERVIEW_MAX)
    if not found:
        raise WritingAnswerError("the writer returned an empty overview")
    return found


def parse_filled(
    text: str,
    fields: list[Field],
    places: list[Place] | None = None,
    add_places: int = 0,
    place_kinds: list[str] | None = None,
) -> tuple[dict[str, str], list[FilledPlace]]:
    """Answers for the empty fields only, and the places' descriptions.

    Keys the player already filled, or never asked for, are dropped; so
    are new places beyond the number asked for or named like an old one.
    """
    data = _json(text)
    raw = data.get("fields")
    answers = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    values: dict[str, str] = {}
    for f in fields:
        if f.value.strip() or f.key not in answers:
            continue
        written = _clean(answers[f.key], f.max_length)
        if written:
            values[f.key] = written

    known = {p.name.strip().lower(): p for p in places or []}
    filled: list[FilledPlace] = []
    added = 0
    seen: set[str] = set()
    raw_places = data.get("places")
    listed = cast("list[object]", raw_places) if isinstance(raw_places, list) else []
    for item in listed:
        if not isinstance(item, dict):
            continue
        entry = cast("dict[str, object]", item)
        name = _clean(entry.get("name"), 64)
        description = _clean(entry.get("description"), 2000)
        said = _clean(entry.get("kind"), 40).lower()
        kind = next((k for k in place_kinds or [] if k.lower() == said), "")
        key = name.lower()
        if not name or not description or key in seen:
            continue
        seen.add(key)
        old = known.get(key)
        if old is not None:
            if not old.description.strip():
                filled.append(FilledPlace(old.name, description, new=False, kind=kind))
        elif added < add_places:
            added += 1
            filled.append(FilledPlace(name, description, new=True, kind=kind))
    return values, filled


#: Lines in a voice sample: someone speaks, the character answers.
SAMPLE_LINES = (3, 6)

SAMPLE_PROMPT = """You are helping someone hear how a character they are writing speaks.
Write a short exchange, {least} to {most} lines, in this situation: {situation}

Someone else ({other}) speaks first; {name} answers in their own voice. Keep {name} \
exactly as described below: their tone, how they treat strangers, the kind of things \
they say. Do not reuse their example lines word for word. Spoken words only: no \
narration, no stage directions, no quotation marks.

{name}:
{about}

Answer with JSON only:
{{"other": "{other}", "lines": [{{"who": "other", "text": "..."}}, \
{{"who": "them", "text": "..."}}]}}"""


@dataclass(frozen=True)
class SampleLine:
    #: "them" (the character) or "other".
    who: str
    text: str


def sample_prompt(name: str, fields: list[Field], situation: str, other: str) -> str:
    about = "\n".join(f"- {f.label}: {f.value.strip()}" for f in fields if f.value.strip())
    return SAMPLE_PROMPT.format(
        least=SAMPLE_LINES[0],
        most=SAMPLE_LINES[1],
        situation=situation.strip().rstrip(".") + ".",
        other=other,
        name=name.strip() or "The character",
        about=about or "- (only a name so far)",
    )


def parse_sample(text: str) -> list[SampleLine]:
    """The exchange, at most the longest asked for; quotes trimmed."""
    raw = _json(text).get("lines")
    listed = cast("list[object]", raw) if isinstance(raw, list) else []
    lines: list[SampleLine] = []
    for item in listed:
        if not isinstance(item, dict):
            continue
        entry = cast("dict[str, object]", item)
        who = "them" if _clean(entry.get("who"), 10).lower() == "them" else "other"
        said = _clean(entry.get("text"), 400).strip("\"“”' ")
        if said:
            lines.append(SampleLine(who, said))
    if not any(line.who == "them" for line in lines):
        raise WritingAnswerError("the writer's sample has no line for the character")
    return lines[: SAMPLE_LINES[1]]
