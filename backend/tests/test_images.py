"""Image jobs: queued where the world gains someone or somewhere, worked by the runner."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient
from test_story_travel import MIGRATIONS, SEED_DIR, _create, _draft

from worldsim.application.images import compose_prompt, load_style_pack, provider_ratio
from worldsim.application.ports.images import (
    GeneratedImage,
    ImageGenerationError,
    ImageRequest,
)
from worldsim.domain.assets import MAX_JOB_ATTEMPTS, AssetKind, ImageJob, JobStatus
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.images.krea import KreaImageGenerator
from worldsim.infrastructure.images.runner import ImageJobRunner
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http.app import create_app


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw)


PACKS = Path(__file__).resolve().parents[2] / "content" / "visual-styles"
PNG = b"\x89PNG\r\n\x1a\nfake"


def test_pack_aspects_map_to_provider_ratios() -> None:
    assert provider_ratio("16:9") == "16:9"
    assert provider_ratio("1.6:1") == "3:2"
    assert provider_ratio("nonsense") == "1:1"


def test_both_pack_layouts_load() -> None:
    anime = load_style_pack(PACKS, "anime-saga-v1")
    pixel = load_style_pack(PACKS, "pixel-saga-v1")
    assert not anime.pixel_art and pixel.pixel_art
    prompt, ratio = compose_prompt(anime, AssetKind.BACKGROUND, "Hearth. No people.")
    assert prompt.startswith("Hearth. No people. ") and ratio == "16:9"
    _, portrait_ratio = compose_prompt(pixel, AssetKind.PORTRAIT, "Portrait of Wren.")
    assert portrait_ratio == "1:1"


def test_krea_client_sends_fields_and_reads_headers() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            content=PNG,
            headers={"content-type": "image/png", "x-size": "1360x768", "x-seed": "7"},
        )

    async def run() -> GeneratedImage:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            krea = KreaImageGenerator("http://krea.test:7860/", client=http)
            return await krea.generate(
                ImageRequest(prompt="a tavern", ratio="16:9", style="kreanima-lora-r32", seed=7)
            )

    image = asyncio.run(run())
    assert seen == [
        {"prompt": "a tavern", "ratio": "16:9", "style": "kreanima-lora-r32", "seed": 7}
    ]
    assert (image.width, image.height, image.seed, image.data) == (1360, 768, 7, PNG)


def test_krea_client_reports_a_loading_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "model is still loading"})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            await KreaImageGenerator("http://krea.test", client=http).generate(
                ImageRequest(prompt="x", ratio="1:1")
            )

    with pytest.raises(ImageGenerationError, match="503"):
        asyncio.run(run())


class _Painter:
    """Stand-in generator: records prompts, can fail the first calls."""

    def __init__(self, failures: int = 0) -> None:
        self.requests: list[ImageRequest] = []
        self._failures = failures

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        self.requests.append(request)
        if self._failures:
            self._failures -= 1
            raise ImageGenerationError("krea HTTP 503: model is still loading")
        return GeneratedImage(data=PNG, mime="image/png", width=1024, height=1024, seed=1)


def _story(client: ApiClient) -> UUID:
    created = _create(client, _draft(client), "images-key")
    assert created.status_code == 200, created.text
    return UUID(created.json()["world_id"])


def _work(world_id: UUID, painter: _Painter, root: Path) -> list[ImageJob]:
    """Run the runner over one world until it is idle; return every job after."""

    async def run() -> list[ImageJob]:
        engine = create_engine(Settings())
        try:
            runner = ImageJobRunner(
                lambda: create_unit_of_work(engine),
                painter,
                LocalStorage(root),
                PACKS,
                style="kreanima-lora-r32",
                world_id=world_id,
            )
            while await runner.run_once():
                pass
            async with create_unit_of_work(engine) as uow:
                characters = await uow.characters.list_for_world(world_id)
                return [
                    job
                    for c in characters
                    if (job := await uow.assets.find_job_by_key(world_id, f"portrait:{c.id}"))
                ]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _pending(world_id: UUID) -> list[ImageJob]:
    async def run() -> list[ImageJob]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return await uow.assets.list_pending_jobs(50, world_id)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_story_creation_queues_one_portrait_per_cast_member(client: ApiClient) -> None:
    world_id = _story(client)
    jobs = _pending(world_id)
    assert jobs and all(job.kind == AssetKind.PORTRAIT for job in jobs)
    assert len({job.subject_id for job in jobs}) == len(jobs)
    assert {job.style_pack_version for job in jobs} == {"anime-saga-v1"}


def test_runner_paints_portraits_that_presentation_shows(
    client: ApiClient,
    tmp_path: Path,
) -> None:
    world_id = _story(client)
    painter = _Painter()
    jobs = _work(world_id, painter, tmp_path)
    assert jobs and all(job.status == JobStatus.READY for job in jobs)
    assert len(painter.requests) == len(jobs)
    assert all(r.ratio == "1:1" and r.prompt.startswith("Portrait of ") for r in painter.requests)
    assert all(r.style == "kreanima-lora-r32" and r.pixel is None for r in painter.requests)
    stored = list((tmp_path / "generated" / str(world_id)).iterdir())
    assert len(stored) == len(jobs) and all(f.read_bytes() == PNG for f in stored)
    cast = client.get(
        "/api/v1/world/presentation",
        params={"world_id": str(world_id)},
        headers={"X-Worldsim-Role": "watcher"},
    ).json()["cast"]
    assert cast and all(member["portrait_asset_id"] for member in cast)


def test_a_failed_attempt_is_retried_then_succeeds(
    client: ApiClient,
    tmp_path: Path,
) -> None:
    world_id = _story(client)
    painter = _Painter(failures=1)
    jobs = _work(world_id, painter, tmp_path)
    assert all(job.status == JobStatus.READY for job in jobs)
    assert sum(job.attempt_count for job in jobs) == 1
    # A retry asks for the same picture.
    seeds = [r.seed for r in painter.requests]
    assert len(seeds) == len(jobs) + 1 and len(set(seeds)) == len(jobs)


def test_jobs_fail_terminally_and_keep_the_error(
    client: ApiClient,
    tmp_path: Path,
) -> None:
    world_id = _story(client)
    painter = _Painter(failures=1_000)
    jobs = _work(world_id, painter, tmp_path)
    assert jobs and all(job.status == JobStatus.FAILED for job in jobs)
    assert all(job.attempt_count == MAX_JOB_ATTEMPTS and "503" in job.error for job in jobs)
    assert len(painter.requests) == len(jobs) * MAX_JOB_ATTEMPTS
