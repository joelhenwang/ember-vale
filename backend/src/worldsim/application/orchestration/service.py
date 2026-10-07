"""Phase identities and reconciliation (owned by S0-ORCH-001).

Beats are advanced by the Stage 1 orchestrator (stage1.py); this module
keeps what every phase shares: deterministic run, snapshot and task-key
identities, so a resumed or replayed phase finds the same rows, and the
reconciler that requeues expired work and reports a world's open run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from worldsim.application.tasks.service import TaskService
from worldsim.application.unit_of_work import UnitOfWork


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


def _derive(name: str, *parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, f"worldsim:{name}:{':'.join(str(part) for part in parts)}")


def derive_run_id(world_id: UUID, absolute_index: int) -> UUID:
    return _derive("phase_run", world_id.hex, absolute_index)


def derive_snapshot_id(run_id: UUID) -> UUID:
    return _derive("snapshot", run_id.hex)


def task_key_for(absolute_index: int) -> str:
    return f"phase_advance:{absolute_index}"


@dataclass(frozen=True)
class ReconcileWorldReport:
    tasks_requeued: int
    outbox_requeued: int
    open_run_id: UUID | None
    open_state: str | None


async def reconcile_world(
    uow_factory: UnitOfWorkFactory, tasks: TaskService, world_id: UUID
) -> ReconcileWorldReport:
    """Requeue expired tasks and outbox messages; report the world's open run."""
    reconcile = await tasks.reconcile()
    async with uow_factory() as uow:
        run = await uow.phases.find_open_run(world_id)
    return ReconcileWorldReport(
        tasks_requeued=reconcile.tasks_requeued,
        outbox_requeued=reconcile.outbox_requeued,
        open_run_id=run.id if run is not None else None,
        open_state=run.state.value if run is not None else None,
    )
