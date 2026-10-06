"""Background runner that turns pending image jobs into stored assets.

One job at a time, matching the image service's single GPU. A failed
attempt is recorded on the job; jobs fail terminally after
MAX_JOB_ATTEMPTS, so a broken prompt never loops forever.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from worldsim.application.images import compose_prompt, load_style_pack, subject_text
from worldsim.application.ports.images import ImageGenerationError, ImageGenerator, ImageRequest
from worldsim.application.ports.storage import StoragePort
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import ImageJob, JobStatus
from worldsim.domain.errors import DomainError
from worldsim.infrastructure.assets.fixture import FixtureImageGateway
from worldsim.infrastructure.images.shrink import shrink

_log = logging.getLogger(__name__)


class ImageJobRunner:
    def __init__(
        self,
        factory: Callable[[], UnitOfWork],
        generator: ImageGenerator,
        storage: StoragePort,
        packs_dir: Path,
        *,
        style: str | None = None,
        pixel: str = "64",
        poll_seconds: float = 2.0,
        world_id: UUID | None = None,
    ) -> None:
        self._factory = factory
        self._generator = generator
        self._storage = storage
        self._packs_dir = packs_dir
        self._style = style
        self._pixel = pixel
        self._poll_seconds = poll_seconds
        #: Work only this world's jobs (None: every world).
        self._world_id = world_id
        self._jobs = FixtureImageGateway(factory)
        self._stopping = asyncio.Event()

    async def run_once(self) -> bool:
        """Work one pending job; False when there was none."""
        async with self._factory() as uow:
            pending = await uow.assets.list_pending_jobs(1, self._world_id)
        if not pending:
            return False
        await self._work(pending[0])
        return True

    async def _work(self, job: ImageJob) -> None:
        if await self._already_drawn(job):
            return
        try:
            request = await self._request_for(job)
            image = await self._generator.generate(request)
        except (ImageGenerationError, ValueError, OSError, DomainError) as exc:
            _log.warning("image job %s failed: %s", job.id, exc)
            await self._jobs.note_attempt(job.id, str(exc)[:1000])
            return
        image = shrink(image, job.kind)
        extension = "webp" if image.mime == "image/webp" else "png"
        ref = f"generated/{job.world_id or 'shared'}/{job.kind.value}-{job.id}.{extension}"
        await self._storage.write(ref, image.data, image.mime)
        await self._jobs.complete(job.id, self._storage, ref, image.mime, image.width, image.height)

    async def _already_drawn(self, job: ImageJob) -> bool:
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

    async def _request_for(self, job: ImageJob) -> ImageRequest:
        pack = load_style_pack(self._packs_dir, job.style_pack_version)
        async with self._factory() as uow:
            subject = await subject_text(uow, job)
        prompt, ratio = compose_prompt(pack, job.kind, subject)
        return ImageRequest(
            prompt=prompt,
            ratio=ratio,
            style=None if pack.pixel_art else self._style,
            pixel=self._pixel if pack.pixel_art else None,
            # Stable per job: a retried job asks for the same picture.
            seed=job.id.int % 2**31,
        )

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
