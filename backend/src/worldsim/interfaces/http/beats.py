"""One admitted beat: the path shared by manual Step and autoplay.

Both go through the same execution slot (scope ``phase:<index>``), so a
second tab, a manual step during autoplay, or a second runner can never
run two beats for one story at once.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from worldsim.application.conditions import tick_conditions
from worldsim.application.execution import guarded_timed, new_owner, phase_run_id, phase_scope
from worldsim.application.orchestration.stage1 import Stage1PhaseReport
from worldsim.application.stories.guards import require_unarchived
from worldsim.domain.commands import ActionIntent
from worldsim.interfaces.http.state import AppState


async def run_beat(
    state: AppState,
    world_id: UUID,
    index: int,
    player_intents: Mapping[UUID, ActionIntent] | None = None,
    *,
    submitter_id: UUID | None = None,
    owner_prefix: str = "http",
) -> tuple[Stage1PhaseReport, int, int]:
    """Run beat ``index``; returns (report, slot_claim_ms, execution_ms)."""
    factory = state.uow_factory()
    async with factory() as uow:
        await require_unarchived(uow, world_id)
    orchestrator = state.stage1()

    async def _run() -> Stage1PhaseReport:
        # The queue drains inside the beat (past its duplicate replay):
        # effects apply pre-decision, attempts merge into the decision and
        # complete only once their scenes commit.
        await tick_conditions(factory, world_id, index)
        return await orchestrator.advance_phase(
            world_id,
            index,
            dict(player_intents or {}),
            drain_queue=True,
            submitter_id=submitter_id,
        )

    return await guarded_timed(
        factory,
        world_id,
        phase_scope(index),
        new_owner(owner_prefix),
        phase_run_id(world_id, index),
        _run,
    )
