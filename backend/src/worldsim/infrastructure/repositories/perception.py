"""Observation and memory adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import Visibility
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.perception import Observation, ObservationFact, RecentMemory
from worldsim.infrastructure.models.perception import ObservationRow, RecentMemoryRow


def _facts_to_domain(raw: list[object]) -> list[ObservationFact]:
    facts: list[ObservationFact] = []
    for item in raw:
        if not isinstance(item, dict):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "fact must be an object")
        mapping = cast("dict[str, Any]", item)
        key, value = mapping["key"], mapping["value"]
        if not isinstance(key, str) or not isinstance(value, str):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "fact parts must be strings")
        facts.append(ObservationFact(key=key, value=value))
    return facts


class SqlAlchemyPerceptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_observation(self, observation: Observation) -> None:
        self._session.add(
            ObservationRow(
                id=observation.id,
                world_id=observation.world_id,
                event_id=observation.event_id,
                observer_character_id=observation.observer_character_id,
                facts=[{"key": fact.key, "value": fact.value} for fact in observation.facts],
                source_id=observation.source_id,
                created_phase_index=observation.created_phase_index,
                salience=observation.salience,
                content_hash=observation.content_hash or None,
            )
        )
        # No flush per row: a commit writes every observer's row of an event
        # in one batched INSERT, not one round trip each (perf-reads-001).

    async def observations_for_event(self, event_id: UUID) -> list[Observation]:
        rows = (
            await self._session.execute(
                select(ObservationRow)
                .where(ObservationRow.event_id == event_id)
                .order_by(ObservationRow.observer_character_id)
            )
        ).scalars()
        return [
            Observation(
                id=row.id,
                world_id=row.world_id,
                event_id=row.event_id,
                observer_character_id=row.observer_character_id,
                facts=_facts_to_domain(row.facts),
                created_phase_index=row.created_phase_index,
                salience=row.salience,
                content_hash=row.content_hash or "",
                source_id=row.source_id,
            )
            for row in rows
        ]

    async def observations_for_events(self, event_ids: list[UUID]) -> dict[UUID, list[Observation]]:
        """Observations of many events in one query, each in observer order."""
        if not event_ids:
            return {}
        rows = (
            await self._session.execute(
                select(ObservationRow)
                .where(ObservationRow.event_id.in_(event_ids))
                .order_by(ObservationRow.event_id, ObservationRow.observer_character_id)
            )
        ).scalars()
        out: dict[UUID, list[Observation]] = {}
        for row in rows:
            out.setdefault(row.event_id, []).append(
                Observation(
                    id=row.id,
                    world_id=row.world_id,
                    event_id=row.event_id,
                    observer_character_id=row.observer_character_id,
                    facts=_facts_to_domain(row.facts),
                    created_phase_index=row.created_phase_index,
                    salience=row.salience,
                    content_hash=row.content_hash or "",
                    source_id=row.source_id,
                )
            )
        return out

    async def observations_for_observer(
        self,
        observer_id: UUID,
        limit: int = 20,
        since_phase_index: int = 0,
        min_salience: float = 0.0,
        older_limit: int | None = None,
    ) -> list[Observation]:
        mine = ObservationRow.observer_character_id == observer_id
        recent = ObservationRow.created_phase_index >= since_phase_index
        salient = ObservationRow.salience >= min_salience
        if older_limit is None:
            query = select(ObservationRow).where(mine, recent | salient)
        else:
            # Every recent row, plus only the newest ``older_limit`` salient
            # rows from before the window (perf-reads-001).
            older = (
                select(ObservationRow.id)
                .where(mine, ~recent, salient)
                .order_by(ObservationRow.created_phase_index.desc())
                .limit(older_limit)
            )
            query = select(ObservationRow).where(
                mine, recent | ObservationRow.id.in_(older.scalar_subquery())
            )
        rows = (
            await self._session.execute(
                query.order_by(ObservationRow.created_phase_index.desc()).limit(limit)
            )
        ).scalars()
        return [
            Observation(
                id=row.id,
                world_id=row.world_id,
                event_id=row.event_id,
                observer_character_id=row.observer_character_id,
                facts=_facts_to_domain(row.facts),
                created_phase_index=row.created_phase_index,
                salience=row.salience,
                content_hash=row.content_hash or "",
                source_id=row.source_id,
            )
            for row in rows
        ]

    async def add_memory(self, memory: RecentMemory) -> None:
        self._session.add(
            RecentMemoryRow(
                id=memory.id,
                world_id=memory.world_id,
                owner_character_id=memory.owner_character_id,
                event_id=memory.event_id,
                observation_id=memory.observation_id,
                text=memory.text,
                visibility=memory.visibility.value,
                created_phase_index=memory.created_phase_index,
                salience=memory.salience,
                content_hash=memory.content_hash or None,
            )
        )

    async def memories_for_owner(
        self,
        owner_id: UUID,
        since_phase_index: int = 0,
        min_salience: float = 0.0,
        older_limit: int | None = None,
    ) -> list[RecentMemory]:
        mine = RecentMemoryRow.owner_character_id == owner_id
        recent = RecentMemoryRow.created_phase_index >= since_phase_index
        salient = RecentMemoryRow.salience >= min_salience
        if older_limit is None:
            query = select(RecentMemoryRow).where(mine, recent | salient)
        else:
            older = (
                select(RecentMemoryRow.id)
                .where(mine, ~recent, salient)
                .order_by(RecentMemoryRow.created_phase_index.desc())
                .limit(older_limit)
            )
            query = select(RecentMemoryRow).where(
                mine, recent | RecentMemoryRow.id.in_(older.scalar_subquery())
            )
        rows = (
            await self._session.execute(query.order_by(RecentMemoryRow.created_phase_index))
        ).scalars()
        return [
            RecentMemory(
                id=row.id,
                world_id=row.world_id,
                owner_character_id=row.owner_character_id,
                event_id=row.event_id,
                observation_id=row.observation_id,
                text=row.text,
                visibility=Visibility(row.visibility),
                created_phase_index=row.created_phase_index,
                salience=row.salience,
                content_hash=row.content_hash or "",
            )
            for row in rows
        ]

    async def bump_salience(
        self,
        observation_ids: list[UUID],
        memory_ids: list[UUID],
        amount: float,
        cap: float,
    ) -> None:
        """Raise persisted salience for cited rows; citations are code-scored."""
        if observation_ids:
            rows = (
                await self._session.execute(
                    select(ObservationRow).where(ObservationRow.id.in_(observation_ids))
                )
            ).scalars()
            for row in rows:
                row.salience = min(cap, row.salience + amount)
        if memory_ids:
            rows = (
                await self._session.execute(
                    select(RecentMemoryRow).where(RecentMemoryRow.id.in_(memory_ids))
                )
            ).scalars()
            for row in rows:
                row.salience = min(cap, row.salience + amount)
        await self._session.flush()
