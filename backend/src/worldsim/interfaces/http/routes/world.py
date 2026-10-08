"""World reads, seed, and phase advancement (owned by S0-API-001)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from worldsim.application.capabilities import is_omniscient, parse_role
from worldsim.application.commands.seed_world import SeedService
from worldsim.application.library.builtins import ensure_builtin_presets
from worldsim.application.queries import presentation as presentation_module
from worldsim.application.queries.presentation import (
    chronicle as chronicle_query,
)
from worldsim.application.queries.presentation import (
    presentation as presentation_query,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.stories import SetupProvenance, StoryCatalogEntry, StoryInitialSetup
from worldsim.domain.time import absolute_index, utcnow
from worldsim.domain.world import World
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.etag import VARY
from worldsim.interfaces.http.routes.roles import effective_role
from worldsim.interfaces.http.schemas import (
    ClockResponse,
    CurrentPhaseResponse,
    EventEntry,
    EventsResponse,
    SeedResponse,
    WorldResponse,
)

router = APIRouter(tags=["world"])


def _world_dto(world: World) -> WorldResponse:
    return WorldResponse(
        id=world.id,
        name=world.name,
        status=world.status.value,
        day=world.day,
        phase=world.phase,
        absolute_index=absolute_index(world.day, world.phase),
        seed_version=world.seed_version,
        version=world.version,
    )


async def _selected_world(request: Request, world_id: UUID | None) -> World:
    """Explicit world selection; the single-world shortcut needs exactly one."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        if world_id is not None:
            return await uow.worlds.get(world_id)
        worlds = await uow.worlds.list_worlds()
    if not worlds:
        raise DomainError(ErrorCode.NOT_FOUND, "no world has been seeded yet")
    if len(worlds) > 1:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "multiple worlds exist; pass an explicit world_id",
            {"code": "WORLD_SELECTION_REQUIRED"},
        )
    return worlds[0]


@router.get("/world", response_model=WorldResponse)
async def get_world(request: Request, world_id: UUID | None = None) -> WorldResponse:
    return _world_dto(await _selected_world(request, world_id))


@router.get("/world/clock", response_model=ClockResponse)
async def get_clock(request: Request, world_id: UUID | None = None) -> ClockResponse:
    world = await _selected_world(request, world_id)
    return ClockResponse(
        day=world.day, phase=world.phase, absolute_index=absolute_index(world.day, world.phase)
    )


@router.get("/world/phases/current", response_model=CurrentPhaseResponse)
async def get_current_phase(request: Request, world_id: UUID | None = None) -> CurrentPhaseResponse:
    state = request.app.state.app_state
    world = await _selected_world(request, world_id)
    async with state.uow_factory()() as uow:
        run = await uow.phases.find_open_run(world.id)
    return CurrentPhaseResponse(
        absolute_index=absolute_index(world.day, world.phase),
        day=world.day,
        phase=world.phase,
        run_id=run.id if run is not None else None,
        run_state=run.state.value if run is not None else None,
    )


@router.get("/world/events", response_model=EventsResponse)
async def list_events(
    request: Request, world_id: UUID | None = None, after: int = 0, limit: int = 50
) -> EventsResponse:
    if after < 0:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "after cursor must be >= 0")
    if not 1 <= limit <= 100:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "limit must be 1..100")
    state = request.app.state.app_state
    world = await _selected_world(request, world_id)
    async with state.uow_factory()() as uow:
        events = await uow.events.list_range(world.id, after, limit)
        entries = [
            EventEntry(
                sequence=event.sequence,
                id=event.id,
                event_type=event.event_type.value,
                absolute_index=event.absolute_index,
                phase_run_id=event.phase_run_id,
                effect_count=len(await uow.events.list_effects(event.id)),
            )
            for event in events
        ]
    return EventsResponse(entries=entries, next_after=entries[-1].sequence if entries else after)


@router.post("/world/seed", response_model=SeedResponse)
async def seed_world(request: Request) -> SeedResponse:
    state = request.app.state.app_state
    result = await SeedService(state.uow_factory(), state.seed_dir).import_seed()
    async with state.uow_factory()() as uow:
        world = await uow.worlds.get(result.world_id)
        try:
            await uow.stories.get_catalog(result.world_id)
        except DomainError as exc:
            if exc.code != ErrorCode.NOT_FOUND:
                raise
            now = utcnow()
            await uow.stories.put_catalog(
                StoryCatalogEntry(
                    world_id=result.world_id,
                    title=world.name,
                    created_at=now,
                )
            )
            await uow.stories.put_setup(
                StoryInitialSetup(
                    world_id=result.world_id,
                    payload={"schema_version": 1, "provenance": "legacy_unknown"},
                    content_hash="legacy-unknown",
                    created_at=now,
                    provenance=SetupProvenance.LEGACY_UNKNOWN,
                )
            )
        await ensure_builtin_presets(uow)
        await uow.commit()
    return SeedResponse(
        world_id=result.world_id,
        seed_version=result.seed_version,
        content_hash=result.content_hash,
        duplicate=result.duplicate,
    )


#: The presentation's code, so a deploy that changes what it shows never
#: matches a tag from before (fingerprint mode).
_CODE_TAG = hashlib.blake2b(
    b"".join(Path(m.__file__ or "").read_bytes() for m in (presentation_module, api)),
    digest_size=8,
).hexdigest()


@router.get("/world/presentation", response_model=api.PresentationResponse)
async def get_presentation(world_id: UUID, request: Request) -> api.PresentationResponse | Response:
    """One coherent snapshot for the new Adventure and World surfaces."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        role, viewer = await effective_role(request, world_id, uow)
        tag: str | None = None
        if state.settings.app.presentation_fingerprint:
            # An unchanged poll is a 304 from one query, not 16 (perf-reads-001).
            seen = await uow.worlds.presentation_fingerprint(world_id)
            digest = hashlib.blake2b(
                f"{seen}|{role}|{viewer}|{_CODE_TAG}".encode(), digest_size=12
            ).hexdigest()
            tag = f'W/"fp-{digest}"'
            headers = {"ETag": tag, "Cache-Control": "private, no-cache", "Vary": VARY}
            sent = request.headers.get("if-none-match", "")
            if tag in {t.strip() for t in sent.split(",")}:
                return Response(status_code=304, headers=headers)
        root = state.seed_dir.parent.parent / "assets"
        built = await presentation_query(
            uow, world_id, parse_role(role), viewer, root, state.journeys
        )
    if tag is None:
        return built
    return Response(
        content=built.model_dump_json(),
        media_type="application/json",
        headers={"ETag": tag, "Cache-Control": "private, no-cache", "Vary": VARY},
    )


@router.get("/world/chronicle", response_model=api.ChronicleResponse)
async def get_chronicle(
    world_id: UUID,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> api.ChronicleResponse:
    """Visible events with structured identity and an advancing cursor."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        role, viewer = await effective_role(request, world_id, uow)
        return await chronicle_query(uow, world_id, parse_role(role), viewer, after, limit)


@router.get("/world/conditions", response_model=api.ConditionsResponse)
async def get_conditions(world_id: UUID, request: Request) -> api.ConditionsResponse:
    """Active and past conditions; players see public labels only."""
    role, _ = await effective_role(request, world_id)
    parsed = parse_role(role)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        conditions = await uow.conditions.list_for_world(world_id)
    views: list[api.ConditionView] = []
    for condition in conditions:
        detail = condition.detail if is_omniscient(parsed) else ""
        views.append(
            api.ConditionView(
                id=condition.id,
                world_id=condition.world_id,
                kind=condition.kind.value,
                public_label=condition.public_label,
                detail=detail,
                scope_location_ids=list(condition.scope_location_ids),
                severity=condition.severity,
                started_absolute=condition.started_absolute,
                ends_absolute=condition.ends_absolute,
                status=condition.status.value,
                version=condition.version,
            )
        )
    return api.ConditionsResponse(world_id=world_id, conditions=views)
