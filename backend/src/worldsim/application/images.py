"""What to draw for an image job: style packs, ratios, subject prompts, queuing.

Jobs are queued where the world changes (story creation, a director
adding someone or somewhere), never on read. Without a live image
provider they stay pending, which is how a missing provider shows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from worldsim.application.ports.images import ImageRequest
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import DEFAULT_STYLE_PACK, AssetKind, ImageJob
from worldsim.domain.ids import new_job_id
from worldsim.domain.jsonvalues import json_object
from worldsim.domain.settings import ImagePrefs

#: Krea 2 Studio aspect ratios, as width / height.
_RATIOS: dict[str, float] = {
    "1:1": 1.0,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
}
#: Which pack wording each kind uses, best first (packs name scenes differently).
_WORDING_FOR: dict[AssetKind, tuple[str, ...]] = {
    AssetKind.SCENE: ("scene", "event", "background"),
}
#: Prompt text kept per subject; the provider reads at most 512 tokens.
_SUBJECT_CHARS = 700


@dataclass(frozen=True)
class PackKind:
    """One image kind of a style pack: shape and wording."""

    aspect: str
    positive: str


@dataclass(frozen=True)
class StylePack:
    version: str
    kinds: dict[str, PackKind]

    @property
    def pixel_art(self) -> bool:
        return "pixel" in self.version


def load_style_pack(packs_dir: Path, version: str) -> StylePack:
    """Read content/visual-styles/<version>.json (either file layout)."""
    raw = json_object(json.loads((packs_dir / f"{version}.json").read_text(encoding="utf-8")))
    if raw is None:
        raise ValueError(f"style pack {version} is not a JSON object")
    section = json_object(raw.get("categories")) or raw
    kinds: dict[str, PackKind] = {}
    for name, value in section.items():
        body = json_object(value)
        if body is not None and "positive" in body:
            kinds[name] = PackKind(
                aspect=str(body.get("aspect", "1:1")), positive=str(body["positive"])
            )
    return StylePack(version=str(raw.get("version", version)), kinds=kinds)


def provider_ratio(aspect: str) -> str:
    """The provider ratio closest to a pack's aspect ("1.6:1" -> "3:2")."""
    if aspect in _RATIOS:
        return aspect
    try:
        width, height = (float(part) for part in aspect.split(":"))
        wanted = width / height
    except ValueError:
        return "1:1"
    return min(_RATIOS, key=lambda name: abs(_RATIOS[name] - wanted))


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _SUBJECT_CHARS else text[: _SUBJECT_CHARS - 1].rstrip() + "…"


async def subject_text(uow: UnitOfWork, job: ImageJob) -> str:
    """Who or what the image shows, from the world's own records."""
    if job.kind == AssetKind.PORTRAIT and job.subject_id is not None:
        character = await uow.characters.get(job.subject_id)
        card = await uow.characters.get_card(character.id, character.card_version)
        looks = card.appearance or card.personality
        named = f"{card.name} ({card.pronouns})" if card.pronouns else card.name
        return _clip(f"Portrait of {named}, head and shoulders. {looks}")
    if job.kind == AssetKind.BACKGROUND and job.subject_id is not None:
        place = await uow.locations.get(job.subject_id)
        region = f", in {place.region}" if place.region else ""
        return _clip(f"{place.name}{region}. No people.")
    if job.kind == AssetKind.MAP and job.world_id is not None:
        world = await uow.worlds.get(job.world_id)
        places = ", ".join(loc.name for loc in await uow.locations.list_for_world(world.id))
        return _clip(f"Map of {world.name}, showing {places}.")
    raise ValueError(f"nothing to draw for a {job.kind.value} job without a subject")


def image_request(
    prompt: str,
    ratio: str,
    kind: AssetKind,
    prefs: ImagePrefs,
    *,
    pixel: str | None = None,
    stable_seed: int | None = None,
    characters: tuple[str, ...] = (),
    references: tuple[str, ...] = (),
) -> ImageRequest:
    """One provider request from a composed prompt and the operator's choices.

    Pixel packs draw with the pixel LoRA instead of a style; the ratio
    preference for portraits and places wins over the pack's own shape.
    """
    chosen_ratio = {
        AssetKind.PORTRAIT: prefs.portrait_ratio,
        AssetKind.BACKGROUND: prefs.place_ratio,
        AssetKind.SCENE: prefs.scene_ratio,
    }.get(kind)
    seed = {"stable": stable_seed, "random": None, "fixed": prefs.seed}[prefs.seed_mode]
    return ImageRequest(
        prompt=prompt,
        ratio=chosen_ratio or ratio,
        style=None if pixel else prefs.style,
        style_scale=prefs.style_scale,
        pixel=pixel,
        seed=seed,
        checkpoint=prefs.checkpoint,
        mode=prefs.mode,
        detail=prefs.detail,
        detail_scale=prefs.detail_scale,
        turbo=prefs.turbo,
        steps=prefs.steps,
        characters=characters,
        references=references,
    )


def compose_prompt(pack: StylePack, kind: AssetKind, subject: str) -> tuple[str, str]:
    """(prompt, provider ratio) for one job."""
    names = _WORDING_FOR.get(kind, (kind.value, "portrait"))
    wording = next((pack.kinds[n] for n in names if n in pack.kinds), None)
    if wording is None:
        raise ValueError(f"style pack {pack.version} has no {kind.value} wording")
    return f"{subject} {wording.positive}", provider_ratio(wording.aspect)


async def queue_image(
    uow: UnitOfWork,
    world_id: UUID,
    kind: AssetKind,
    subject_id: UUID,
    style_pack: str = DEFAULT_STYLE_PACK,
) -> ImageJob:
    """Queue one image for a subject, once per subject and kind."""
    key = f"{kind.value}:{subject_id}"
    existing = await uow.assets.find_job_by_key(world_id, key)
    if existing is not None:
        return existing
    job = ImageJob(
        id=new_job_id(),
        world_id=world_id,
        kind=kind,
        subject_id=subject_id,
        style_pack_version=style_pack,
        idempotency_key=key,
    )
    await uow.assets.add_job(job)
    return job


async def world_style_pack(uow: UnitOfWork, world_id: UUID) -> str:
    """The pack a world's images were first queued with, else the default."""
    return await uow.assets.style_pack_for_world(world_id) or DEFAULT_STYLE_PACK
