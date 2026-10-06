"""Scene pictures: key moments worth painting, suggested prompts, queuing.

After a beat commits, ``queue_moment`` looks at the player's scenes for
one key moment (a rumour settled, arriving somewhere new, a first
meeting) and queues one picture, at most one every few beats. The player
can also ask for any scene ("Paint this scene") with a prompt they may
edit. The people in a picture keep their faces: the image runner
registers their portraits with the image service and draws them as
references, with the place's own art as a further reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from worldsim.application.ports.images import CharacterCard
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


def look_of(name: str, appearance: str) -> str:
    """'Tobin: a young cartwright's apprentice with sawdust in his hair'.

    Only the first sentence: appearances often go on into backstory,
    which a painter cannot draw.
    """
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
    uow: UnitOfWork, world_id: UUID, scene_id: UUID, player_id: UUID | None
) -> Suggestion:
    """Plain words for a scene's picture: who, what happens, and where."""
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
    beats = await uow.scenes.narrations_for_event(scene.event_id) if scene.event_id else []
    happening = _sentences(without_speech(" ".join(b.text for b in beats)), _SUGGESTION_SENTENCES)
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


async def queue_moment(
    uow: UnitOfWork,
    world_id: UUID,
    index: int,
    player_id: UUID,
    scenes: list[Scene],
    style_pack: str,
) -> ScenePicture | None:
    """At most one key-moment picture per beat, a few beats apart.

    A settled rumour is never held back by the cooldown: it is rare and
    the end of something the player did. Moments skipped for the
    cooldown are tried again later (their key is still unused).
    """
    latest = await uow.pictures.latest_moment_index(world_id)
    cooling = latest is not None and index - latest < MOMENT_COOLDOWN_BEATS
    for scene in scenes:
        for moment in await _moments(uow, scene, player_id):
            if cooling and moment.moment != PictureMoment.SETTLED:
                continue
            picture = await queue_picture(
                uow,
                world_id,
                moment.scene_id,
                moment.moment,
                moment.caption,
                index=index,
                character_ids=moment.character_ids,
                location_id=moment.location_id,
                style_pack=style_pack,
                key=moment.key,
            )
            if picture is not None:
                return picture
    return None
