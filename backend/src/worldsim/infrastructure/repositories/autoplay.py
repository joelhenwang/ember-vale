"""Autoplay state adapter (E5 observatory)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.autoplay import AutoplayState, AutoplayStatus, StopReason, paused_default
from worldsim.infrastructure.models.autoplay import AutoplayRow


class SqlAlchemyAutoplayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: AutoplayRow) -> AutoplayState:
        return AutoplayState(
            world_id=row.world_id,
            status=AutoplayStatus(row.status),
            delay_seconds=row.delay_seconds,
            beats_left=row.beats_left,
            beats_run=row.beats_run,
            stop_reason=StopReason(row.stop_reason) if row.stop_reason else None,
            stop_detail=row.stop_detail,
            last_seen_at=row.last_seen_at,
            next_due_at=row.next_due_at,
            version=row.version,
        )

    async def get(self, world_id: UUID, *, for_update: bool = False) -> AutoplayState:
        """The story's state; a never-played story reads as paused."""
        query = select(AutoplayRow).where(AutoplayRow.world_id == world_id)
        if for_update:
            query = query.with_for_update()
        row = (await self._session.execute(query)).scalar_one_or_none()
        return self._to_domain(row) if row is not None else paused_default(world_id)

    async def save(self, state: AutoplayState) -> AutoplayState:
        """Write the state and bump its version (callers hold the row lock)."""
        row = await self._session.get(AutoplayRow, state.world_id)
        if row is None:
            row = AutoplayRow(world_id=state.world_id, version=0)
            self._session.add(row)
        else:
            row.version = row.version + 1
        row.status = state.status.value
        row.delay_seconds = state.delay_seconds
        row.beats_left = state.beats_left
        row.beats_run = state.beats_run
        row.stop_reason = state.stop_reason.value if state.stop_reason else None
        row.stop_detail = state.stop_detail
        row.last_seen_at = state.last_seen_at
        row.next_due_at = state.next_due_at
        await self._session.flush()
        return self._to_domain(row)

    async def due(self, now: datetime, limit: int = 50) -> list[UUID]:
        """Playing stories whose next beat is due, oldest first."""
        rows = await self._session.execute(
            select(AutoplayRow.world_id)
            .where(AutoplayRow.status == AutoplayStatus.PLAYING.value)
            .where(AutoplayRow.next_due_at <= now)
            .order_by(AutoplayRow.next_due_at)
            .limit(limit)
        )
        return list(rows.scalars())
