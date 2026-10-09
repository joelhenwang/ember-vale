"""Background runner that turns pending image jobs into stored assets.

One job at a time, matching the image service's single GPU. A failed
attempt is recorded on the job; jobs fail terminally after
MAX_JOB_ATTEMPTS, so a broken prompt never loops forever.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy.orm.exc import StaleDataError

from worldsim.application.images import (
    compose_prompt,
    image_additions,
    image_request,
    load_style_pack,
    subject_text,
)
from worldsim.application.pictures import character_card, newest_asset, scene_words
from worldsim.application.ports.images import (
    CharacterCard,
    ImageGenerationError,
    ImageGenerator,
    ImageRequest,
)
from worldsim.application.ports.map_reader import MapReader, MapReadingError
from worldsim.application.ports.storage import StoragePort
from worldsim.application.stories.create import PORTRAIT_FRAMES
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import AssetKind, AssetRecord, ImageJob, JobStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.framing import Frame, as_list, framed_face
from worldsim.domain.geography import MAP_SPAN
from worldsim.domain.settings import ImagePrefs
from worldsim.infrastructure.assets.fixture import FixtureImageGateway
from worldsim.infrastructure.images.shrink import crop, shrink

_log = logging.getLogger(__name__)


def imported_portrait(raw: object, character_id: UUID, asset_id: UUID) -> Frame | None:
    """The portrait frame on an imported picture, while it is the portrait shown."""
    if not isinstance(raw, dict):
        return None
    entry = cast("dict[str, object]", raw).get(str(character_id))
    if not isinstance(entry, dict):
        return None
    framed = cast("dict[str, object]", entry)
    if framed.get("asset_id") != str(asset_id):
        return None
    try:
        x, y, w, h = cast("list[float]", framed["portrait"])
        return Frame(x=x, y=y, w=w, h=h)
    except (KeyError, TypeError, ValueError):
        return None


async def frame_face(
    factory: Callable[[], UnitOfWork], faces: MapReader, asset: AssetRecord, data: bytes
) -> Frame | None:
    """Note where the face is on a painted portrait, so round tokens show it.

    Returns the face frame; None (tokens keep their usual crop) when the
    reader fails or finds no face.
    """
    if asset.world_id is None or asset.subject_id is None:
        return None
    try:
        reading = await faces.face(data, asset.mime)
    except MapReadingError as exc:
        _log.warning("no face found on portrait %s: %s", asset.id, exc)
        return None
    if not reading.found:
        return None
    left, top, right, bottom = reading.found[0]
    box = Frame(
        x=left / MAP_SPAN,
        y=top / MAP_SPAN,
        w=(right - left) / MAP_SPAN,
        h=(bottom - top) / MAP_SPAN,
    )
    frames = framed_face(box, asset.width, asset.height)
    async with factory() as uow:
        raw = (await uow.worlds.get_config(asset.world_id)).get(PORTRAIT_FRAMES)
        by_character = dict(cast("dict[str, object]", raw)) if isinstance(raw, dict) else {}
        by_character[str(asset.subject_id)] = {
            "asset_id": str(asset.id),
            "portrait": as_list(frames.portrait),
            "face": as_list(frames.face),
        }
        await uow.worlds.put_config(asset.world_id, PORTRAIT_FRAMES, by_character)
        await uow.commit()
    return frames.face


def _job_gone(exc: Exception) -> bool:
    """True when finishing failed because the job was removed or changed meanwhile."""
    if isinstance(exc, StaleDataError):
        return True  # its row was deleted between reading and saving
    return isinstance(exc, DomainError) and exc.code in (
        ErrorCode.NOT_FOUND,
        ErrorCode.PRECONDITION_FAILED,
        ErrorCode.VERSION_CONFLICT,
    )


#: How long a claimed job is this runner's (a paint takes ~14 s; a runner
#: that dies mid-paint frees it after this).
CLAIM_LEASE_S = 600


class ImageJobRunner:
    def __init__(
        self,
        factory: Callable[[], UnitOfWork],
        generator: ImageGenerator,
        storage: StoragePort,
        packs_dir: Path,
        *,
        pixel: str = "64",
        operator: str = "local",
        poll_seconds: float = 2.0,
        world_id: UUID | None = None,
        faces: MapReader | None = None,
    ) -> None:
        self._factory = factory
        self._generator = generator
        self._storage = storage
        self._packs_dir = packs_dir
        self._pixel = pixel
        #: Whose image preferences shape every request.
        self._operator = operator
        self._poll_seconds = poll_seconds
        #: Work only this world's jobs (None: every world).
        self._world_id = world_id
        #: Finds the face on a painted portrait, for round tokens.
        self._faces = faces
        self._jobs = FixtureImageGateway(factory)
        self._stopping = asyncio.Event()

    async def run_once(self) -> bool:
        """Work one pending job; False when there was none (or images are off)."""
        async with self._factory() as uow:
            prefs = (await uow.settings.get_preferences(self._operator)).images
            job = (
                await uow.assets.claim_next_job(CLAIM_LEASE_S, self._world_id)
                if prefs.enabled
                else None
            )
            await uow.commit()
        if job is None:
            return False
        await self._work(job, prefs)
        return True

    async def _work(self, job: ImageJob, prefs: ImagePrefs) -> None:
        if await self._already_drawn(job):
            return
        try:
            request = await self._request_for(job, prefs)
            image = await self._generator.generate(request)
        except (ImageGenerationError, ValueError, OSError, DomainError) as exc:
            _log.warning("image job %s failed: %s", job.id, exc)
            try:
                await self._jobs.note_attempt(job.id, str(exc)[:1000])
            except (DomainError, StaleDataError) as gone:
                if not _job_gone(gone):
                    raise
                _log.info("image job %s was removed while it was being painted", job.id)
            return
        # Decode, resize and WebP-encode off the event loop: 80-220 ms of CPU
        # that otherwise stalled every request and beat in the process.
        image = await asyncio.to_thread(shrink, image, job.kind)
        extension = "webp" if image.mime == "image/webp" else "png"
        ref = f"generated/{job.world_id or 'shared'}/{job.kind.value}-{job.id}.{extension}"
        await self._storage.write(ref, image.data, image.mime)
        try:
            asset = await self._jobs.complete(
                job.id, self._storage, ref, image.mime, image.width, image.height
            )
        except (DomainError, StaleDataError) as exc:
            if not _job_gone(exc):
                raise
            # Removed while painting (going back to a turn, say): nothing is
            # recorded, and the file no row refers to is left for the sweep.
            _log.info("image job %s was removed while painting; %s left unused", job.id, ref)
            return
        if job.kind == AssetKind.PORTRAIT and self._faces is not None:
            await frame_face(self._factory, self._faces, asset, image.data)
        if job.kind == AssetKind.SCENE and job.subject_id is not None:
            async with self._factory() as uow:
                try:
                    picture = await uow.pictures.get(job.subject_id)
                except DomainError as exc:
                    if exc.code != ErrorCode.NOT_FOUND:
                        raise
                    return  # the picture went (a rewind) just as it was painted
                if picture.repaint_job_id == job.id:
                    await uow.pictures.update(
                        picture.model_copy(update={"job_id": job.id, "repaint_job_id": None})
                    )
                    await uow.commit()

    async def _already_drawn(self, job: ImageJob) -> bool:
        if job.idempotency_key.startswith("scene:repaint:"):
            return False  # asked for anew: never the old painting
        return await self._bound_to_existing(job)

    async def _bound_to_existing(self, job: ImageJob) -> bool:
        """Curated or earlier art for this subject wins: bind it, draw nothing.

        Built-in characters ship hand-made portraits; a generated one would
        replace them on the map (the newest asset is shown).
        """
        if job.world_id is None or job.subject_id is None:
            return False
        async with self._factory() as uow:
            existing = await uow.assets.list_assets_for_subject(
                job.world_id, job.kind.value, job.subject_id
            )
            if not existing:
                return False
            newest = max(existing, key=lambda asset: asset.subject_visual_version)
            await uow.assets.save_job(
                job.model_copy(update={"status": JobStatus.READY, "result_asset_id": newest.id}),
                job.version,
            )
            await uow.commit()
        return True

    async def _request_for(self, job: ImageJob, prefs: ImagePrefs) -> ImageRequest:
        pack = load_style_pack(self._packs_dir, job.style_pack_version)
        characters: tuple[str, ...] = ()
        references: tuple[str, ...] = ()
        people: list[UUID] = []
        raw = False
        if job.kind == AssetKind.SCENE:
            subject, characters, references, people, raw = await self._scene_parts(job)
        else:
            async with self._factory() as uow:
                subject = await subject_text(uow, job)
            if job.kind == AssetKind.PORTRAIT and job.subject_id is not None:
                people = [job.subject_id]
        async with self._factory() as uow:
            added = await image_additions(uow, job.world_id, people)
        prompt, ratio = compose_prompt(pack, job.kind, added.subject(subject))
        # A prompt the player edited whole is sent exactly as written.
        return image_request(
            subject if raw else added.whole(prompt),
            ratio,
            job.kind,
            prefs,
            pixel=self._pixel if pack.pixel_art else None,
            # Stable per job: a retried job asks for the same picture.
            stable_seed=job.id.int % 2**31,
            characters=characters,
            references=references,
        )

    async def _scene_parts(
        self, job: ImageJob
    ) -> tuple[str, tuple[str, ...], tuple[str, ...], list[UUID], bool]:
        """A scene picture's words, its people's faces, and its place's art.

        Each person with a portrait is registered with the image service
        (once per portrait version) and drawn as a reference; people
        without one yet are still described in the words.
        """
        if job.subject_id is None:
            raise ValueError("a scene job needs its picture")
        cards: list[CharacterCard] = []
        place_art: tuple[str, ...] = ()
        async with self._factory() as uow:
            picture = await uow.pictures.get(job.subject_id)
            words = await scene_words(uow, picture)
            raw = picture.raw_prompt
            for character_id in picture.character_ids:
                portrait = await newest_asset(
                    uow, picture.world_id, AssetKind.PORTRAIT, character_id
                )
                if portrait is None:
                    continue
                image = await self._storage.read(portrait.content_ref)
                framed = imported_portrait(
                    (await uow.worlds.get_config(picture.world_id)).get("portrait_frames"),
                    character_id,
                    portrait.id,
                )
                if framed is not None:
                    image = crop(image, framed)  # the portrait, not the whole picture
                cards.append(
                    await character_card(
                        uow, picture.world_id, character_id, image, portrait.subject_visual_version
                    )
                )
            if picture.location_id is not None:
                art = await newest_asset(
                    uow, picture.world_id, AssetKind.BACKGROUND, picture.location_id
                )
                if art is not None:
                    data = base64.b64encode(await self._storage.read(art.content_ref)).decode()
                    place_art = (f"data:{art.mime};base64,{data}",)
        for card in cards:
            await self._generator.ensure_character(card)
        return words, tuple(card.id for card in cards), place_art, picture.character_ids, raw

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            worked = False
            try:
                worked = await self.run_once()
            except Exception:  # keep polling through transient DB errors
                _log.exception("image runner tick failed")
            if worked:
                continue
            try:
                await asyncio.wait_for(self._stopping.wait(), self._poll_seconds)
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stopping.set()
