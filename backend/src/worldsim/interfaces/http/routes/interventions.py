"""Natural-language intervention queue (owned by REVAMP-P07)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application import interventions as service
from worldsim.application.capabilities import parse_role
from worldsim.application.interventions import INTERPRET_PROMPT_VERSION, Scope
from worldsim.application.ports.model_gateway import ModelGateway
from worldsim.application.settings.resolution import PinnedRuntime, resolve_pin
from worldsim.application.stories.guards import require_unarchived
from worldsim.application.tracing.gateway import TracedGateway
from worldsim.application.tracing.service import ManifestSpec
from worldsim.domain.enums import UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.interventions import (
    Intervention,
    InterventionMode,
    InterventionStep,
)
from worldsim.infrastructure.model_gateway.selection import (
    gateway_for_pin,
    gateways_for_settings,
)
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role
from worldsim.interfaces.http.state import stage0_gateway

router = APIRouter(tags=["interventions"])


@dataclass(frozen=True)
class InterpretRuntime:
    """The gateway one interpretation executes through, plus the pin it honors.

    `pin` is None for environment execution; otherwise it is the requested
    profile revision the gateway was built from.
    """

    gateway: ModelGateway
    pin: PinnedRuntime | None


async def _interpret_runtime(request: Request, world_id: UUID) -> InterpretRuntime:
    """Story-pinned interpretation gateway; environment fallback when unpinned.

    The director gateway interprets for every operating role. Reusing the
    runtime-selection mechanism the beats execute (`gateway_for_pin` over
    the resolved revision plus connection) means a story's pin governs
    direction interpretation exactly as it governs beats. A broken
    explicit pin raises before any generation.
    """
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        pin = await resolve_pin(uow, world_id)
    if state.gateway_factory is stage0_gateway:
        gateways, _ = gateways_for_settings(state.settings, None)
        env = gateways["director"]
    else:
        env = state.gateway_factory()
    if pin is None:
        return InterpretRuntime(env, None)
    return InterpretRuntime(
        gateway_for_pin("director", pin.profile, pin.connection, env_gateway=env),
        pin,
    )


def _traced_interpret(state: Any, runtime: InterpretRuntime, world_id: UUID) -> TracedGateway:
    """Audited interpretation gateway: the manifest records the requested
    pin, the executed model, and the interpretation outcome.
    """
    pin = runtime.pin
    return TracedGateway(
        runtime.gateway,
        state.traces(),
        ManifestSpec(
            role="interpret",
            profile=runtime.gateway.profile,
            prompt_version=INTERPRET_PROMPT_VERSION,
            world_id=world_id,
            pin_profile_id=str(pin.profile.id) if pin is not None else None,
            pin_profile_revision=pin.profile.revision if pin is not None else None,
        ),
    )


def _view(intervention: Intervention, steps: list[InterventionStep]) -> api.InterventionView:
    return api.InterventionView(
        id=intervention.id,
        world_id=intervention.world_id,
        client_request_id=intervention.client_request_id,
        status=intervention.status.value,
        mode=intervention.mode.value,
        role=intervention.role,
        text=intervention.text,
        steps=[
            api.InterventionStepView(
                id=step.id,
                seq=step.seq,
                kind=step.kind.value,
                status=step.status.value,
                result_event_id=step.result_event_id,
                result_activity_id=step.result_activity_id,
                result_hook_id=step.result_hook_id,
                failure_reason=step.failure_reason,
                version=step.version,
            )
            for step in steps
        ],
        failure_reason=intervention.failure_reason,
        version=intervention.version,
    )


async def _detail(request: Request, intervention_id: UUID) -> api.InterventionView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        intervention = await uow.interventions.get_intervention(intervention_id)
        steps = await uow.interventions.list_steps(intervention_id)
    return _view(intervention, steps)


@router.post("/interventions", response_model=api.InterventionView)
async def submit_intervention(
    body: api.InterventionRequest, request: Request
) -> api.InterventionView:
    """Interpret and queue a direction; same key replays the same item."""
    role, viewer = await effective_role(request, body.world_id)
    parsed = parse_role(role)
    try:
        mode = InterventionMode(body.mode)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown mode: {body.mode}") from exc
    if body.effective_at != "next_boundary":
        raise DomainError(ErrorCode.VALIDATION_FAILED, "effective_at must be next_boundary")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await require_unarchived(uow, body.world_id)
    runtime = await _interpret_runtime(request, body.world_id)
    intervention = await service.submit(
        state.uow_factory(),
        _traced_interpret(state, runtime, body.world_id),
        body.world_id,
        parsed,
        mode,
        body.text,
        Scope(
            kind=body.scope.kind,
            character_ids=list(body.scope.character_ids),
            location_ids=list(body.scope.location_ids),
        ),
        body.client_request_id,
        viewer=viewer,
    )
    return await _detail(request, intervention.id)


@router.get("/interventions", response_model=list[api.InterventionView])
async def list_interventions(world_id: UUID, request: Request) -> list[api.InterventionView]:
    """Queued and recent queue items with their step states."""
    role, _ = await effective_role(request, world_id)
    parsed = parse_role(role)
    if parsed not in (UserRole.WATCHER, UserRole.DIRECTOR, UserRole.DEITY):
        raise DomainError(ErrorCode.FORBIDDEN, "the queue is an operator surface")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        queued = await uow.interventions.list_queued_for_world(world_id)
        views: list[api.InterventionView] = []
        for intervention in queued:
            steps = await uow.interventions.list_steps(intervention.id)
            views.append(_view(intervention, steps))
    return views


@router.get("/interventions/{intervention_id}", response_model=api.InterventionView)
async def read_intervention(intervention_id: UUID, request: Request) -> api.InterventionView:
    """Reconcile one queued command by id."""
    return await _detail(request, intervention_id)


@router.patch("/interventions/{intervention_id}", response_model=api.InterventionView)
async def edit_intervention(
    intervention_id: UUID, body: api.InterventionEditRequest, request: Request
) -> api.InterventionView:
    """Reinterpret before claim; version-checked with restarted history."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        current = await uow.interventions.get_intervention(intervention_id)
    _, viewer = await effective_role(request, current.world_id)
    runtime = await _interpret_runtime(request, current.world_id)
    updated = await service.edit_text(
        state.uow_factory(),
        _traced_interpret(state, runtime, current.world_id),
        intervention_id,
        body.expected_version,
        body.text,
        Scope(
            kind=body.scope.kind,
            character_ids=list(body.scope.character_ids),
            location_ids=list(body.scope.location_ids),
        ),
        viewer=viewer,
    )
    return await _detail(request, updated.id)


@router.post("/interventions/{intervention_id}/cancel", response_model=api.InterventionView)
async def cancel_intervention(
    intervention_id: UUID, body: api.InterventionCancelRequest, request: Request
) -> api.InterventionView:
    """Cancel before application; executing work cannot stop."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        current = await uow.interventions.get_intervention(intervention_id)
    await effective_role(request, current.world_id)
    await service.cancel(state.uow_factory(), intervention_id, body.expected_version)
    return await _detail(request, intervention_id)

