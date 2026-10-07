"""Scene pictures: key moments worth painting, suggested prompts, queuing.

Once a beat's narration is written, ``plan_moments`` gathers the
player's scenes and a small writing model reads the narration
(``MOMENT_PROMPT``): how much the turn is worth a picture, a headline,
one line for under it and what a painter should show. ``queue_moment``
then queues at most one picture: a turning point the model picked out,
a rumour settled, arriving somewhere new or a first meeting, at most one
every few beats (a turning point or a settled rumour skips the wait). The player
can also ask for any scene ("Paint this scene") with a prompt they may
edit. The people in a picture keep their faces: the image runner
registers their portraits with the image service and draws them as
references, with the place's own art as a further reference.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from worldsim.application.ports.images import CharacterCard
from worldsim.application.ports.writer import Writer, WritingError
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import AssetKind, AssetRecord, ImageJob
from worldsim.domain.effects import HookSettledEffect, MoveEntityEffect
from worldsim.domain.ids import new_job_id
from worldsim.domain.pictures import (
    MAX_PICTURE_CHARACTERS,
    MOMENT_COOLDOWN_BEATS,
    PictureMoment,
    ScenePicture,
)
from worldsim.domain.scenes import Scene

#: Words of narration a suggested prompt keeps (the service reads 512 tokens).
_SUGGESTION_SENTENCES = 2
_LOOKS_CHARS = 220
#: Studio fields hold the whole look (clothes included), so they keep more.
_STUDIO_LOOKS_CHARS = 360


@dataclass(frozen=True)
class Suggestion:
    """What "Paint this scene" offers: editable words plus who keeps a face."""

    prompt: str
    caption: str
    character_ids: list[UUID]
    location_id: UUID | None


def service_character_id(character_id: UUID, portrait_version: int) -> str:
    """The image service's id for one portrait of a character (≤ 40 chars)."""
    return f"ev-{character_id.hex[:24]}-v{portrait_version}"


async def newest_asset(
    uow: UnitOfWork, world_id: UUID, kind: AssetKind, subject_id: UUID
) -> AssetRecord | None:
    assets = await uow.assets.list_assets_for_subject(world_id, kind.value, subject_id)
    return max(assets, key=lambda a: a.subject_visual_version) if assets else None


async def character_card(
    uow: UnitOfWork, world_id: UUID, character_id: UUID, image: bytes, version: int
) -> CharacterCard:
    """The card the image service keeps; its first clause names the look."""
    character = await uow.characters.get(character_id)
    card = await uow.characters.get_card(character.id, character.card_version)
    looks = _clip(card.appearance or card.personality, _LOOKS_CHARS)
    return CharacterCard(
        id=service_character_id(character_id, version),
        name=card.name,
        description=f"{card.name}, {looks}" if looks else card.name,
        image=image,
    )


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _sentences(text: str, count: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return " ".join(parts[:count])


#: Where a description turns from looks to backstory (", who ran away...").
_BACKSTORY = re.compile(r",\s+(?:who|which|whose)\b")
#: Quote marks: sentences with speech in them are left out of pictures.
_QUOTE = re.compile(r"[\"“”]")


def without_speech(text: str) -> str:
    """Narration without the sentences that carry speech.

    A painter cannot draw words, and a half-kept quote ("she says, and
    sits") reads badly in a caption.
    """
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return " ".join(part for part in parts if part and not _QUOTE.search(part))


#: The character studio's appearance fields, one "Label: value" per line.
_LOOK_FIELDS = ("Age", "Race", "Sex", "Height", "Build", "Hair", "Eyes", "Marks", "Wears")
_LOOK_LINE = re.compile(rf"^({'|'.join(_LOOK_FIELDS)}):\s*(.*)$", re.IGNORECASE)


def plain_looks(appearance: str) -> str | None:
    """Studio fields as a painter's phrase, or None when not in that form.

    'Age: 17\\nRace: Human\\nSex: Female\\nHair: a dark braid\\nWears: oilskin'
    -> '17-year-old human female, a dark braid, wearing oilskin'.
    Backstory-ish fields (Condition) are left out; average heights too.
    """
    found: dict[str, str] = {}
    for line in appearance.splitlines():
        match = _LOOK_LINE.match(line.strip())
        if match and match.group(2).strip():
            found[match.group(1).capitalize()] = match.group(2).strip().rstrip(".")
    if not found:
        return None
    age = found.get("Age", "")
    who = " ".join(
        part
        for part in (
            f"{age}-year-old" if age.isdigit() else age.lower(),
            found.get("Race", "").lower(),
            found.get("Sex", "").lower(),
        )
        if part
    )
    height = found.get("Height", "").lower()
    hair, eyes, wears = found.get("Hair", ""), found.get("Eyes", ""), found.get("Wears", "")
    parts = [
        who,
        height if height != "average" else "",
        found.get("Build", ""),
        hair if not hair or "hair" in hair.lower() else f"{hair} hair",
        eyes if not eyes or "eye" in eyes.lower() else f"{eyes} eyes",
        f"wearing {wears}" if wears else "",
    ]
    return ", ".join(part for part in parts if part)


def look_of(name: str, appearance: str) -> str:
    """'Tobin: a young cartwright's apprentice with sawdust in his hair'.

    Only the first sentence: appearances often go on into backstory,
    which a painter cannot draw. Studio fields become one phrase.
    """
    plain = plain_looks(appearance)
    if plain is not None:
        return f"{name}: {_clip(plain, _STUDIO_LOOKS_CHARS)}"
    first = _sentences(appearance, 1)
    first = _BACKSTORY.split(first, maxsplit=1)[0].rstrip(" .")
    if not first:
        return name
    opening = first.split()[0]
    if not (len(opening) > 1 and opening.isupper()):  # keep acronyms as written
        first = first[0].lower() + first[1:]
    return f"{name}: {_clip(first, _LOOKS_CHARS)}"


async def _scene_place(uow: UnitOfWork, scene: Scene) -> UUID | None:
    if scene.event_id is None:
        return None
    raw = (await uow.events.get_event(scene.event_id)).summary.get("location_id")
    try:
        return UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _people(scene: Scene, first: UUID | None) -> list[UUID]:
    """Who keeps a face: the player first, then the others in the scene."""
    ids = [p.character_id for p in scene.participants]
    lead = [i for i in ids if i == first]
    return (lead + [i for i in ids if i != first])[:MAX_PICTURE_CHARACTERS]


async def suggest(
    uow: UnitOfWork,
    world_id: UUID,
    scene_id: UUID,
    player_id: UUID | None,
    happening: str | None = None,
) -> Suggestion:
    """Plain words for a scene's picture: who, what happens, and where.

    ``happening`` replaces the narration's first sentences when a writer
    already said what to show.
    """
    scene = await uow.scenes.get_scene(scene_id)
    if scene.world_id != world_id:
        raise ValueError("scene belongs to another world")
    people = _people(scene, player_id)
    lines: list[str] = []
    names: list[str] = []
    for character_id in people:
        character = await uow.characters.get(character_id)
        card = await uow.characters.get_card(character.id, character.card_version)
        names.append(card.name)
        lines.append(look_of(card.name, card.appearance))
    if happening is None:
        beats = await uow.scenes.narrations_for_event(scene.event_id) if scene.event_id else []
        happening = _sentences(
            without_speech(" ".join(b.text for b in beats)), _SUGGESTION_SENTENCES
        )
    location_id = await _scene_place(uow, scene)
    place = ""
    if location_id is not None:
        location = await uow.locations.get(location_id)
        place = location.name + (f", in {location.region}" if location.region else "")
    prompt = " ".join(
        part
        for part in (
            "; ".join(lines) + "." if lines else "",
            happening,
            f"Setting: {place}." if place else "",
        )
        if part
    )
    caption = happening or (f"{' and '.join(names)} at {place}." if place else "A moment.")
    return Suggestion(
        prompt=_clip(prompt, 1800),
        caption=_clip(caption, 400),
        character_ids=people,
        location_id=location_id,
    )


async def queue_picture(
    uow: UnitOfWork,
    world_id: UUID,
    scene_id: UUID,
    moment: PictureMoment,
    caption: str,
    *,
    index: int,
    character_ids: list[UUID],
    location_id: UUID | None,
    style_pack: str,
    prompt: str | None = None,
    key: str | None = None,
    title: str | None = None,
) -> ScenePicture | None:
    """Queue one picture; None when ``key`` was used before (a moment paints once)."""
    key = key or f"scene:manual:{uuid4().hex}"
    if await uow.assets.find_job_by_key(world_id, key) is not None:
        return None
    picture_id = uuid4()
    job = ImageJob(
        id=new_job_id(),
        world_id=world_id,
        kind=AssetKind.SCENE,
        subject_id=picture_id,
        style_pack_version=style_pack,
        idempotency_key=key,
    )
    await uow.assets.add_job(job)
    picture = ScenePicture(
        id=picture_id,
        world_id=world_id,
        scene_id=scene_id,
        job_id=job.id,
        moment=moment,
        title=_clip(title, 80) if title else None,
        caption=_clip(caption, 400),
        prompt=prompt,
        character_ids=character_ids[:MAX_PICTURE_CHARACTERS],
        location_id=location_id,
        created_phase_index=index,
    )
    await uow.pictures.add(picture)
    return picture


@dataclass(frozen=True)
class _Moment:
    moment: PictureMoment
    caption: str
    key: str
    character_ids: list[UUID]
    location_id: UUID | None
    scene_id: UUID


async def _moments(uow: UnitOfWork, scene: Scene, player_id: UUID) -> list[_Moment]:
    """This scene's key moments for the player, most notable first."""
    if scene.event_id is None or player_id not in {p.character_id for p in scene.participants}:
        return []
    people = _people(scene, player_id)
    place = await _scene_place(uow, scene)
    player = await uow.characters.get(player_id)
    me = (await uow.characters.get_card(player.id, player.card_version)).name
    found: list[_Moment] = []
    for committed in await uow.events.list_effects(scene.event_id):
        effect = committed.effect
        if isinstance(effect, HookSettledEffect):
            found.append(
                _Moment(
                    PictureMoment.SETTLED,
                    effect.ending,
                    f"scene:settled:{effect.hook_id}",
                    people,
                    place,
                    scene.id,
                )
            )
        elif isinstance(effect, MoveEntityEffect) and player_id in effect.affected_ids:
            location = await uow.locations.get(effect.to_location_id)
            found.append(
                _Moment(
                    PictureMoment.ARRIVAL,
                    f"{me} arrives at {location.name}.",
                    f"scene:arrival:{player_id}:{effect.to_location_id}",
                    [player_id],
                    effect.to_location_id,
                    scene.id,
                )
            )
    for other in people[1:]:
        character = await uow.characters.get(other)
        name = (await uow.characters.get_card(character.id, character.card_version)).name
        found.append(
            _Moment(
                PictureMoment.MEETING,
                f"{me} meets {name}.",
                f"scene:meeting:{player_id}:{other}",
                [player_id, other],
                place,
                scene.id,
            )
        )
    order = [PictureMoment.SETTLED, PictureMoment.ARRIVAL, PictureMoment.MEETING]
    return sorted(found, key=lambda m: order.index(m.moment))


#: What the writing model is asked after a turn (one call per beat, at most).
MOMENT_PROMPT = """You choose the pictures for an illustrated story. Read one turn and answer \
with JSON only, no other text:
{{"worth": 0, "title": "", "line": "", "picture": ""}}

- worth: 3 for a turning point (a discovery, a confrontation, a reveal, danger, a farewell, \
something found or lost); 2 for a vivid moment worth remembering; 1 for an ordinary moment; \
0 when nothing happens.
- title: a storybook chapter headline of 2 to 6 words, no full stop ("A bell beneath the tide").
- line: one sentence of at most 20 words saying what happened, in the present tense, naming \
{me}.
- picture: one or two sentences for a painter: who does what, holding or touching what, in \
what light. Only what can be seen: no speech, no thoughts, no backstory, no place names.

Who is there: {people}
Where: {place}

The turn:
{narration}"""
#: Narration characters sent to the writer (a turn is 600-1,500).
_MOMENT_NARRATION_CHARS = 3000
#: A turn worth this much is painted even without an arrival or meeting.
WORTH_PAINTING = 2
#: A turn worth this much skips the cooldown, as a settled rumour does.
TURNING_POINT = 3


@dataclass(frozen=True)
class MomentWords:
    """The writer's reading of one turn."""

    worth: int
    title: str
    line: str
    picture: str


def parse_moment(text: str) -> MomentWords | None:
    """The writer's JSON answer, or None when it is not usable."""
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
    worth = fields.get("worth")
    title, line, picture = (
        " ".join(str(fields.get(name) or "").split()) for name in ("title", "line", "picture")
    )
    if not isinstance(worth, int) or isinstance(worth, bool) or not title or not picture:
        return None
    return MomentWords(
        worth=max(0, min(3, worth)),
        title=_clip(title.rstrip("."), 80),
        line=_clip(line, 400),
        picture=_clip(without_speech(picture) or picture, 700),
    )


@dataclass(frozen=True)
class MomentPlan:
    """One of the player's scenes this beat, ready to judge and queue."""

    scene: Scene
    moments: list[_Moment]
    me: str
    people: list[str]
    place: str
    narration: str

    def prompt(self) -> str:
        return MOMENT_PROMPT.format(
            me=self.me,
            people=", ".join(self.people) or self.me,
            place=self.place or "unknown",
            narration=_clip(self.narration, _MOMENT_NARRATION_CHARS),
        )


async def plan_moments(uow: UnitOfWork, player_id: UUID, scenes: list[Scene]) -> list[MomentPlan]:
    """The player's scenes of a beat, with their narration and key moments."""
    plans: list[MomentPlan] = []
    player = await uow.characters.get(player_id)
    me = (await uow.characters.get_card(player.id, player.card_version)).name
    for scene in scenes:
        if scene.event_id is None or player_id not in {p.character_id for p in scene.participants}:
            continue
        names: list[str] = []
        for participant in scene.participants:
            character = await uow.characters.get(participant.character_id)
            names.append((await uow.characters.get_card(character.id, character.card_version)).name)
        place_id = await _scene_place(uow, scene)
        place = (await uow.locations.get(place_id)).name if place_id is not None else ""
        beats = await uow.scenes.narrations_for_event(scene.event_id)
        plans.append(
            MomentPlan(
                scene=scene,
                moments=await _moments(uow, scene, player_id),
                me=me,
                people=names,
                place=place,
                narration=" ".join(b.text for b in beats),
            )
        )
    return plans


async def judge_moment(writer: Writer, plan: MomentPlan) -> tuple[MomentWords | None, float]:
    """The writer's reading of a scene, and what it cost (None when it failed)."""
    if not plan.narration.strip():
        return None, 0.0
    try:
        written = await writer.write(plan.prompt())
    except WritingError:
        return None, 0.0
    return parse_moment(written.text), written.cost_usd


async def queue_moment(
    uow: UnitOfWork,
    world_id: UUID,
    index: int,
    player_id: UUID,
    plans: list[MomentPlan],
    style_pack: str,
    words: dict[UUID, MomentWords] | None = None,
) -> ScenePicture | None:
    """At most one key-moment picture per beat, a few beats apart.

    ``words`` holds the writer's reading per scene. A turning point (worth
    3) and a settled rumour are never held back by the cooldown: they are
    rare and the heart of the story. A vivid turn (worth 2) is painted
    like an arrival or a first meeting. Moments skipped for the cooldown
    are tried again later (their key is still unused).
    """
    words = words or {}
    latest = await uow.pictures.latest_moment_index(world_id)
    cooling = latest is not None and index - latest < MOMENT_COOLDOWN_BEATS
    for plan in plans:
        said = words.get(plan.scene.id)
        candidates = list(plan.moments)
        if said is not None and said.worth >= WORTH_PAINTING:
            people = _people(plan.scene, player_id)
            turning = _Moment(
                PictureMoment.TURNING,
                said.line or said.title,
                f"scene:turning:{plan.scene.id}",
                people,
                await _scene_place(uow, plan.scene),
                plan.scene.id,
            )
            # A turning point leads; a merely vivid turn comes after the
            # fixed moments, which keep their own once-only keys.
            candidates = (
                [turning, *candidates] if said.worth >= TURNING_POINT else [*candidates, turning]
            )
        for moment in candidates:
            urgent = moment.moment == PictureMoment.SETTLED or (
                moment.moment == PictureMoment.TURNING
                and said is not None
                and said.worth >= TURNING_POINT
            )
            if cooling and not urgent:
                continue
            prompt = None
            if said is not None:
                prompt = (
                    await suggest(uow, world_id, plan.scene.id, player_id, happening=said.picture)
                ).prompt
            picture = await queue_picture(
                uow,
                world_id,
                moment.scene_id,
                moment.moment,
                said.line if said is not None and said.line else moment.caption,
                index=index,
                character_ids=moment.character_ids,
                location_id=moment.location_id,
                style_pack=style_pack,
                prompt=prompt,
                key=moment.key,
                title=said.title if said is not None else None,
            )
            if picture is not None:
                return picture
    return None
