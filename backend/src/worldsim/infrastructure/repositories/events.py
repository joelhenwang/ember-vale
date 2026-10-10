"""World event and effect adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import EventType, Visibility
from worldsim.domain.events import CommittedEffect, WorldEvent
from worldsim.infrastructure.models.commands import UserCommandRow
from worldsim.infrastructure.models.events import EventEffectRow, WorldEventRow
from worldsim.infrastructure.repositories._common import missing

_effect_adapter: TypeAdapter[DomainEffect] = TypeAdapter(DomainEffect)


def _event_values(event: WorldEvent) -> dict[str, Any]:
    """An event's columns, as the ORM row and the one-statement insert take them."""
    return {
        "id": event.id,
        "world_id": event.world_id,
        "sequence": event.sequence,
        "event_type": event.event_type.value,
        "schema_version": event.schema_version,
        "absolute_index": event.absolute_index,
        "phase_run_id": event.phase_run_id,
        "source_command_id": event.source_command_id,
        "source_task_id": event.source_task_id,
        "participant_ids": [str(item) for item in event.participant_ids],
        "summary": dict(event.summary),
        "visibility": event.visibility.value,
        "random_seed": event.random_seed,
        "random_algorithm": event.random_algorithm,
        "random_result": event.random_result,
        "created_at": event.created_at,
    }


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def max_sequence(self, world_id: UUID) -> int:
        value = (
            await self._session.execute(
                select(func.max(WorldEventRow.sequence)).where(WorldEventRow.world_id == world_id)
            )
        ).scalar_one_or_none()
        return value if isinstance(value, int) else 0

    async def append_event(self, event: WorldEvent) -> None:
        self._session.add(WorldEventRow(**_event_values(event)))
        await self._session.flush()

    async def append_event_completing(self, event: WorldEvent, command_id: UUID) -> None:
        """Append the event and link it as its command's result in one
        statement (perf-turn-002): the command's ``result_event_id`` is set
        from the event insert's RETURNING. Same rows as append_event plus
        CommandRepository.set_result; the foreign key is checked at the end
        of the statement, when the event is there."""
        made = (
            insert(WorldEventRow)
            .values(**_event_values(event))
            .returning(WorldEventRow.id)
            .cte("made_event")
        )
        statement = (
            update(UserCommandRow)
            .where(UserCommandRow.id == command_id)
            .values(result_event_id=made.c.id)
            .add_cte(made)
            .returning(UserCommandRow.id)
        )
        if (await self._session.execute(statement)).first() is None:
            raise missing("command", command_id)

    async def append_effects(self, effects: list[CommittedEffect]) -> None:
        """Several effects in one multi-row insert (a commit's effects)."""
        if not effects:
            return
        await self._session.execute(
            insert(EventEffectRow),
            [
                {
                    "event_id": effect.event_id,
                    "ordinal": effect.ordinal,
                    "effect_type": effect.effect.effect_type.value,
                    "schema_version": effect.effect.schema_version,
                    "payload": effect.effect.model_dump(mode="json"),
                }
                for effect in effects
            ],
        )

    async def append_effect(self, effect: CommittedEffect) -> None:
        self._session.add(
            EventEffectRow(
                event_id=effect.event_id,
                ordinal=effect.ordinal,
                effect_type=effect.effect.effect_type.value,
                schema_version=effect.effect.schema_version,
                payload=effect.effect.model_dump(mode="json"),
            )
        )
        await self._session.flush()

    def _to_domain(self, row: WorldEventRow) -> WorldEvent:
        # Macro-period events belong to no phase run; the domain default is None.
        return WorldEvent(
            id=row.id,
            world_id=row.world_id,
            sequence=row.sequence,
            event_type=EventType(row.event_type),
            schema_version=row.schema_version,
            absolute_index=row.absolute_index,
            phase_run_id=row.phase_run_id,
            source_command_id=row.source_command_id,
            source_task_id=row.source_task_id,
            participant_ids=[UUID(item) for item in row.participant_ids],
            summary=dict(row.summary),
            visibility=Visibility(row.visibility),
            random_seed=row.random_seed,
            random_algorithm=row.random_algorithm,
            random_result=row.random_result,
            created_at=row.created_at,
        )

    async def get_event(self, event_id: UUID) -> WorldEvent:
        row = await self._session.get(WorldEventRow, event_id)
        if row is None:
            raise missing("world event", event_id)
        return self._to_domain(row)

    async def find_by_phase_run(self, world_id: UUID, phase_run_id: UUID) -> WorldEvent | None:
        row = (
            await self._session.execute(
                select(WorldEventRow).where(
                    WorldEventRow.world_id == world_id,
                    WorldEventRow.phase_run_id == phase_run_id,
                )
            )
        ).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def list_effects(self, event_id: UUID) -> list[CommittedEffect]:
        rows = (
            await self._session.execute(
                select(EventEffectRow)
                .where(EventEffectRow.event_id == event_id)
                .order_by(EventEffectRow.ordinal)
            )
        ).scalars()
        effects: list[CommittedEffect] = []
        for row in rows:
            payload: Any = row.payload
            effects.append(
                CommittedEffect(
                    event_id=row.event_id,
                    ordinal=row.ordinal,
                    effect=_effect_adapter.validate_python(payload),
                )
            )
        return effects

    async def list_range(self, world_id: UUID, after: int, limit: int) -> list[WorldEvent]:
        rows = (
            await self._session.execute(
                select(WorldEventRow)
                .where(WorldEventRow.world_id == world_id, WorldEventRow.sequence > after)
                .order_by(WorldEventRow.sequence)
                .limit(limit)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def latest_fight(self, world_id: UUID) -> WorldEvent | None:
        """The newest event that rolled a fight with foes (combat stories)."""
        row = (
            await self._session.execute(
                select(WorldEventRow)
                .where(
                    WorldEventRow.world_id == world_id,
                    WorldEventRow.summary.has_key("foes"),
                )
                .order_by(WorldEventRow.sequence.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def list_rolled(self, world_id: UUID) -> list[WorldEvent]:
        """Every event that rolled dice (fights, spars, settled rumours)."""
        rows = (
            await self._session.execute(
                select(WorldEventRow)
                .where(
                    WorldEventRow.world_id == world_id,
                    WorldEventRow.summary.has_key("rolls"),
                )
                .order_by(WorldEventRow.sequence)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def list_by_absolute(
        self, world_id: UUID, start_absolute: int, end_absolute: int
    ) -> list[WorldEvent]:
        rows = (
            await self._session.execute(
                select(WorldEventRow)
                .where(
                    WorldEventRow.world_id == world_id,
                    WorldEventRow.absolute_index >= start_absolute,
                    WorldEventRow.absolute_index < end_absolute,
                )
                .order_by(WorldEventRow.sequence)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def count_events(self, world_id: UUID) -> int:
        value = (
            await self._session.execute(
                select(func.count(WorldEventRow.id)).where(WorldEventRow.world_id == world_id)
            )
        ).scalar_one()
        assert isinstance(value, int)
        return value
