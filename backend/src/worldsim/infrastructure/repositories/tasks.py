"""Task-run and lease adapter (owned by S0-UOW-001).

Claim checks eligibility under a row lock, so two workers racing for one
task serialize: the loser sees the winner's state and gets nothing.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import TaskRunState
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.tasks import Lease, TaskRun
from worldsim.infrastructure.models.stories import StoryCatalogRow
from worldsim.infrastructure.models.tasks import TaskRunRow
from worldsim.infrastructure.repositories._common import missing


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _to_domain(row: TaskRunRow) -> TaskRun:
    lease = None
    if row.owner is not None:
        assert row.claimed_at is not None and row.expires_at is not None
        lease = Lease(
            owner=row.owner,
            claimed_at=row.claimed_at,
            expires_at=row.expires_at,
            attempt=row.attempt,
            max_attempts=row.max_attempts,
            input_version=row.input_version,
            idempotency_key=row.idempotency_key,
        )
    return TaskRun(
        id=row.id,
        world_id=row.world_id,
        kind=row.kind,
        state=TaskRunState(row.state),
        lease=lease,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyTaskRepository:
    _TERMINAL = ("succeeded", "dead_letter", "cancelled")

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        task_id: UUID,
        world_id: UUID,
        kind: str,
        key: str,
        max_attempts: int = 3,
    ) -> TaskRun:
        row = TaskRunRow(
            id=task_id,
            world_id=world_id,
            kind=kind,
            state="pending",
            max_attempts=max_attempts,
            idempotency_key=key,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def get(self, task_id: UUID) -> TaskRun:
        row = await self._session.get(TaskRunRow, task_id)
        if row is None:
            raise missing("task", task_id)
        return _to_domain(row)

    async def claim(self, task_id: UUID, owner: str, lease: Lease) -> TaskRun | None:
        row = (
            await self._session.execute(
                select(TaskRunRow).where(TaskRunRow.id == task_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("task", task_id)
        now = _utcnow()
        eligible = row.state == "pending" or (
            row.state in ("running", "retry_wait")
            and row.expires_at is not None
            and row.expires_at <= now
        )
        if not eligible or row.state in self._TERMINAL:
            return None
        await self._reject_archived(row.world_id)
        row.state = "running"
        row.owner = owner
        row.claimed_at = lease.claimed_at
        row.expires_at = lease.expires_at
        row.attempt = lease.attempt
        row.max_attempts = lease.max_attempts
        await self._session.flush()
        return _to_domain(row)

    async def start_running(self, task_id: UUID, world_id: UUID, kind: str, lease: Lease) -> bool:
        """Create a task already claimed by ``lease``, in one statement.

        For audit-only rows a turn writes as it goes (a character's
        decision): create plus claim took five statements and two
        transactions each (perf-turn-001). False when the row exists
        already (a resumed turn); callers then claim it the usual way.
        No archive check: admission refuses an archived story and a story
        cannot be archived while a turn is open.
        """
        now = _utcnow()
        created = (
            await self._session.execute(
                pg_insert(TaskRunRow)
                .values(
                    id=task_id,
                    world_id=world_id,
                    kind=kind,
                    state="running",
                    owner=lease.owner,
                    claimed_at=lease.claimed_at,
                    expires_at=lease.expires_at,
                    attempt=lease.attempt,
                    max_attempts=lease.max_attempts,
                    input_version=lease.input_version,
                    idempotency_key=lease.idempotency_key,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing()
                .returning(TaskRunRow.id)
            )
        ).scalar_one_or_none()
        return created is not None

    async def _reject_archived(self, world_id: UUID) -> None:
        catalog = (
            await self._session.execute(
                select(StoryCatalogRow.archived_at)
                .where(StoryCatalogRow.world_id == world_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if catalog:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "story is archived; unarchive it before changing the world",
            )

    async def _archived_worlds(self, world_ids: set[UUID]) -> set[UUID]:
        if not world_ids:
            return set()
        rows = (
            await self._session.execute(
                select(StoryCatalogRow.world_id).where(
                    StoryCatalogRow.world_id.in_(world_ids),
                    StoryCatalogRow.archived_at.is_not(None),
                )
            )
        ).scalars()
        return set(rows)

    async def heartbeat(self, task_id: UUID, owner: str, expires_at: datetime) -> bool:
        row = (
            await self._session.execute(
                select(TaskRunRow).where(TaskRunRow.id == task_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("task", task_id)
        if (
            row.owner != owner
            or row.state != "running"
            or (row.expires_at is not None and row.expires_at <= _utcnow())
        ):
            return False
        row.expires_at = expires_at
        await self._session.flush()
        return True

    async def finish(self, task_id: UUID, owner: str, state: str) -> bool:
        # One guarded UPDATE does it when the owner still runs it (the usual
        # case); otherwise the row is read to tell missing from not ours.
        done = (
            await self._session.execute(
                update(TaskRunRow)
                .where(
                    TaskRunRow.id == task_id,
                    TaskRunRow.owner == owner,
                    TaskRunRow.state == "running",
                )
                .values(
                    state=state,
                    owner=None,
                    claimed_at=None,
                    expires_at=None,
                    updated_at=_utcnow(),
                )
                .returning(TaskRunRow.id)
                .execution_options(synchronize_session=False)
            )
        ).scalar_one_or_none()
        if done is not None:
            return True
        row = (
            await self._session.execute(
                select(TaskRunRow).where(TaskRunRow.id == task_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("task", task_id)
        if row.owner != owner or row.state != "running":
            return False
        row.state = state
        row.owner = None
        row.claimed_at = None
        row.expires_at = None
        await self._session.flush()
        return True

    async def fail(
        self, task_id: UUID, owner: str, state: str, expires_at: datetime | None
    ) -> bool:
        row = (
            await self._session.execute(
                select(TaskRunRow).where(TaskRunRow.id == task_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("task", task_id)
        if row.owner != owner or row.state != "running":
            return False
        row.state = state
        row.expires_at = expires_at
        if state in self._TERMINAL:
            row.owner = None
            row.claimed_at = None
            row.expires_at = None
        await self._session.flush()
        return True

    async def reset(self, task_id: UUID, owner: str) -> bool:
        """Recycle a terminal slot, or release one the owner still holds."""
        row = (
            await self._session.execute(
                select(TaskRunRow).where(TaskRunRow.id == task_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("task", task_id)
        if row.state in self._TERMINAL or (row.state == "running" and row.owner == owner):
            row.state = "pending"
            row.owner = owner
            row.attempt = 0
            await self._session.flush()
            return True
        return False

    async def find_by_key(self, world_id: UUID, key: str) -> TaskRun | None:
        row = (
            await self._session.execute(
                select(TaskRunRow).where(
                    TaskRunRow.world_id == world_id,
                    TaskRunRow.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def claim_due(
        self, kind: str | None, owner: str, lease_s: float, limit: int
    ) -> list[TaskRun]:
        now = _utcnow()
        filters: list[Any] = [
            TaskRunRow.state.not_in(self._TERMINAL),
            (TaskRunRow.state == "pending")
            | (
                (TaskRunRow.state.in_(("running", "retry_wait")))
                & (TaskRunRow.expires_at.is_not(None))
                & (TaskRunRow.expires_at <= now)
            ),
        ]
        if kind is not None:
            filters.append(TaskRunRow.kind == kind)
        rows = (
            await self._session.execute(
                select(TaskRunRow)
                .where(*filters)
                .order_by(TaskRunRow.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
        claimed = list(rows)
        archived = await self._archived_worlds({row.world_id for row in claimed})
        claimed = [row for row in claimed if row.world_id not in archived]
        for row in claimed:
            row.state = "running"
            row.owner = owner
            row.claimed_at = now
            row.expires_at = now + timedelta(seconds=lease_s)
            row.attempt = row.attempt + 1
        await self._session.flush()
        return [_to_domain(row) for row in claimed]

    async def requeue_expired(self, now: datetime) -> int:
        rows = (
            await self._session.execute(
                select(TaskRunRow)
                .where(
                    TaskRunRow.state == "running",
                    TaskRunRow.expires_at.is_not(None),
                    TaskRunRow.expires_at <= now,
                )
                .with_for_update()
            )
        ).scalars()
        stale = list(rows)
        for row in stale:
            row.state = "pending"
            row.owner = None
        await self._session.flush()
        return len(stale)
