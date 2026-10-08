"""FastAPI application factory (owned by S0-API-001).

``create_app`` wires routes, middleware, handlers, and startup
reconciliation. The lifespan never applies migrations: it verifies the
process against durable state, requeues expired work, and reports.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

import worldsim
from worldsim.application.autoplay import AutoplayRunner
from worldsim.application.orchestration.stage1 import Stage1PhaseReport
from worldsim.application.tasks.service import TaskService
from worldsim.domain.errors import DomainError
from worldsim.infrastructure.http_pool import aclose_pooled
from worldsim.infrastructure.images.runner import ImageJobRunner
from worldsim.infrastructure.local_models.indexer import MentionReader, RecallIndexer
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.ops.logging import install
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http.auth import ApiKeyMiddleware
from worldsim.interfaces.http.beats import run_beat
from worldsim.interfaces.http.errors import (
    RequestIdMiddleware,
    domain_error_handler,
    unhandled_error_handler,
)
from worldsim.interfaces.http.etag import JsonETagMiddleware
from worldsim.interfaces.http.routes import (
    activities,
    assets,
    autoplay,
    health,
    image_settings,
    interventions,
    knowledge,
    library,
    library_pictures,
    library_writing,
    macro,
    operations,
    pictures,
    progress,
    relationships,
    roles,
    stage1,
    stage2,
    stories,
    story_prompts,
    world,
    world_maps,
)
from worldsim.interfaces.http.routes import (
    settings as settings_routes,
)
from worldsim.interfaces.http.state import (
    MIGRATIONS_DIR,
    SEED_DIR,
    AppState,
    build_state,
    stage0_gateway,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    state: AppState = app.state.app_state
    install(state.settings)
    factory = state.uow_factory()
    report = await TaskService(factory).reconcile()
    app.state.startup_report = {
        "tasks_requeued": report.tasks_requeued,
        "outbox_requeued": report.outbox_requeued,
    }
    loops = start_loops(state) if state.settings.app.background_loops else BackgroundLoops()
    app.state.autoplay_runner = loops.autoplay
    app.state.image_runner = loops.images
    yield
    if state.narration is not None:
        await state.narration.drain()
    await loops.stop()
    await aclose_pooled()
    await state.engine.dispose()


@dataclass
class BackgroundLoops:
    """The long-running jobs beside the HTTP boundary (or in a worker)."""

    autoplay: AutoplayRunner | None = None
    images: ImageJobRunner | None = None
    tasks: list[tuple[Any, asyncio.Task[None]]] = field(default_factory=list)

    async def stop(self) -> None:
        for job, task in self.tasks:
            await job.stop()
            await task


def start_loops(state: AppState) -> BackgroundLoops:
    """Start autoplay, the image runner and local-model jobs.

    Every one is safe beside another copy in a second process: autoplay
    claims a story with a lease, image jobs are claimed with SKIP LOCKED.
    """
    loops = BackgroundLoops()
    if state.settings.autoplay.enabled:
        loops.autoplay = AutoplayRunner(
            state.uow_factory(),
            lambda world_id, index: _autoplay_beat(state, world_id, index),
            poll_seconds=state.settings.autoplay.poll_seconds,
        )
    loops.images = _image_runner(state)
    jobs: list[Any] = [loops.autoplay, loops.images, *_local_jobs(state)]
    loops.tasks = [(job, asyncio.create_task(job.run_forever())) for job in jobs if job]
    return loops


def _image_runner(state: AppState) -> ImageJobRunner | None:
    """The Krea job runner, when images are switched on."""
    images, generator = state.settings.images, state.images()
    if generator is None:
        return None
    content = state.seed_dir.parent.parent
    return ImageJobRunner(
        state.uow_factory(),
        generator,
        LocalStorage(content / "assets"),
        content / "visual-styles",
        pixel=images.krea_pixel,
        poll_seconds=images.poll_seconds,
        faces=state.map_reader(),
    )


def _local_jobs(state: AppState) -> list[RecallIndexer | MentionReader]:
    """Background work for the local model service, when one is set."""
    models = state.local_models()
    if models is None:
        return []
    local = state.settings.local_models
    return [
        RecallIndexer(
            state.uow_factory(),
            models,
            batch=local.index_batch,
            poll_seconds=local.index_poll_seconds,
        ),
        MentionReader(state.uow_factory(), models, poll_seconds=local.index_poll_seconds),
    ]


async def _autoplay_beat(state: AppState, world_id: UUID, index: int) -> Stage1PhaseReport:
    report, _claim_ms, _execution_ms = await run_beat(
        state, world_id, index, owner_prefix="autoplay"
    )
    return report


def create_app(
    settings: Settings | None = None,
    *,
    seed_dir: Path | None = None,
    migrations_dir: Path | None = None,
    gateway_factory: Callable[[], FakeGateway] | None = None,
) -> FastAPI:
    resolved = settings if settings is not None else Settings()
    state = build_state(
        resolved,
        seed_dir=seed_dir if seed_dir is not None else SEED_DIR,
        migrations_dir=migrations_dir if migrations_dir is not None else MIGRATIONS_DIR,
        gateway_factory=gateway_factory if gateway_factory is not None else stage0_gateway,
    )
    app = FastAPI(
        title="worldsim",
        version=worldsim.__version__,
        lifespan=lifespan,
    )
    app.state.app_state = state
    key = resolved.security.api_key
    # Innermost: hashes the plain JSON, so an unchanged poll answers 304.
    app.add_middleware(JsonETagMiddleware)
    app.add_middleware(ApiKeyMiddleware, expected_key=key.get_secret_value() if key else None)
    app.add_middleware(RequestIdMiddleware)
    # Outermost: JSON shrinks ~5-8x; pictures are already compressed.
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1024,
        exclude_content_types=(
            "text/event-stream",
            "image/webp",
            "image/png",
            "image/jpeg",
            "image/gif",
        ),
    )
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(world.router, prefix="/api/v1")
    app.include_router(operations.router, prefix="/api/v1")
    app.include_router(stage1.router, prefix="/api/v1")
    app.include_router(activities.router, prefix="/api/v1")
    app.include_router(relationships.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(progress.router, prefix="/api/v1")
    app.include_router(roles.router, prefix="/api/v1")
    app.include_router(settings_routes.router, prefix="/api/v1")
    app.include_router(image_settings.router, prefix="/api/v1")
    app.include_router(pictures.router, prefix="/api/v1")
    app.include_router(story_prompts.router, prefix="/api/v1")
    app.include_router(stage2.router, prefix="/api/v1")
    app.include_router(macro.router, prefix="/api/v1")
    app.include_router(assets.router, prefix="/api/v1")
    app.include_router(interventions.router, prefix="/api/v1")
    app.include_router(stories.router, prefix="/api/v1")
    app.include_router(library.router, prefix="/api/v1")
    app.include_router(world_maps.router, prefix="/api/v1")
    app.include_router(library_pictures.router, prefix="/api/v1")
    app.include_router(library_writing.router, prefix="/api/v1")
    app.include_router(autoplay.router, prefix="/api/v1")
    return app
