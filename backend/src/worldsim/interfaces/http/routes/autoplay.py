"""Server-side autoplay for the observatory (E5).

Play admits one beat at a time on the server, up to a beat limit, with
an optional delay between committed beats. The observing page reports
presence; autoplay pauses itself once nobody has been seen for the
grace period, so a closed tab never keeps spending.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application.autoplay import (
    pause_autoplay,
    read_autoplay,
    report_presence,
    start_autoplay,
)
from worldsim.application.capabilities import Capability, parse_role, require_capability
from worldsim.application.stories.guards import require_unarchived
from worldsim.domain.autoplay import AutoplayState
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.interfaces.http.routes.roles import effective_role
from worldsim.interfaces.http.schemas import AutoplayPlayRequest, AutoplayView

router = APIRouter(tags=["autoplay"])


def _view(state: AutoplayState, request: Request) -> AutoplayView:
    return AutoplayView(
        world_id=state.world_id,
        status=state.status.value,
        delay_seconds=state.delay_seconds,
        beats_left=state.beats_left,
        beats_run=state.beats_run,
        stop_reason=state.stop_reason.value if state.stop_reason else None,
        stop_detail=state.stop_detail,
        next_due_at=state.next_due_at,
        last_seen_at=state.last_seen_at,
        runner_enabled=request.app.state.app_state.settings.autoplay.enabled,
        version=state.version,
    )


async def _require_operator(request: Request, story_id: UUID) -> None:
    """Autoplay drives the whole cast: watchers and director seats only.

    A Player's character waits for its player's attempt, so autoplay
    cannot run a player story without deciding for them.
    """
    role, _viewer = await effective_role(request, story_id)
    require_capability(parse_role(role), Capability.ADVANCE)
    if role == "player":
        raise DomainError(
            ErrorCode.FORBIDDEN,
            "autoplay is for watching; a Player story advances on its player's attempts",
        )


@router.get("/stories/{story_id}/autoplay", response_model=AutoplayView)
async def get_autoplay(story_id: UUID, request: Request) -> AutoplayView:
    factory = request.app.state.app_state.uow_factory()
    return _view(await read_autoplay(factory, story_id), request)


@router.post("/stories/{story_id}/autoplay/play", response_model=AutoplayView)
async def play_autoplay(
    story_id: UUID, body: AutoplayPlayRequest, request: Request
) -> AutoplayView:
    await _require_operator(request, story_id)
    factory = request.app.state.app_state.uow_factory()
    async with factory() as uow:
        await require_unarchived(uow, story_id)
    state = await start_autoplay(
        factory, story_id, delay_seconds=body.delay_seconds, beat_limit=body.beat_limit
    )
    return _view(state, request)


@router.post("/stories/{story_id}/autoplay/pause", response_model=AutoplayView)
async def pause_route(story_id: UUID, request: Request) -> AutoplayView:
    await _require_operator(request, story_id)
    factory = request.app.state.app_state.uow_factory()
    return _view(await pause_autoplay(factory, story_id), request)


@router.post("/stories/{story_id}/autoplay/presence", response_model=AutoplayView)
async def presence_route(story_id: UUID, request: Request) -> AutoplayView:
    """An observer is looking at this story; keeps autoplay from pausing."""
    factory = request.app.state.app_state.uow_factory()
    return _view(await report_presence(factory, story_id), request)
