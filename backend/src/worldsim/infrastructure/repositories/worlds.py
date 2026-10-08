"""World, clock, and config adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import PhaseName, WorldStatus
from worldsim.domain.time import absolute_index
from worldsim.domain.world import World
from worldsim.infrastructure.models.world import WorldClockRow, WorldConfigRow, WorldRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


def _to_domain(row: WorldRow, clock: WorldClockRow) -> World:
    return World(
        id=row.id,
        name=row.name,
        status=WorldStatus(row.status),
        day=clock.day,
        phase=PhaseName(clock.phase),
        seed_version=row.seed_version,
        version=row.version,
    )


class SqlAlchemyWorldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, world_id: UUID) -> World:
        row = await self._session.get(WorldRow, world_id)
        if row is None:
            raise missing("world", world_id)
        clock = await self._session.get(WorldClockRow, world_id)
        if clock is None:
            raise missing("world clock", world_id)
        return _to_domain(row, clock)

    async def get_many(self, world_ids: list[UUID]) -> dict[UUID, World]:
        """Many worlds with their clocks in one query (missing ids left out)."""
        if not world_ids:
            return {}
        rows = await self._session.execute(
            select(WorldRow, WorldClockRow)
            .join(WorldClockRow, WorldClockRow.world_id == WorldRow.id)
            .where(WorldRow.id.in_(world_ids))
        )
        return {row.id: _to_domain(row, clock) for row, clock in rows.all()}

    async def lock(self, world_id: UUID) -> World:
        """Load the world locked for update within this transaction.

        Serializes per-world admission: concurrent advancers queue
        on the world row instead of interleaving open-run checks.
        """
        row = (
            await self._session.execute(
                select(WorldRow).where(WorldRow.id == world_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("world", world_id)
        clock = await self._session.get(WorldClockRow, world_id)
        if clock is None:
            raise missing("world clock", world_id)
        return _to_domain(row, clock)

    async def list_worlds(self) -> list[World]:
        rows = (await self._session.execute(select(WorldRow).order_by(WorldRow.id))).scalars()
        worlds: list[World] = []
        for row in rows:
            clock = await self._session.get(WorldClockRow, row.id)
            if clock is None:
                raise missing("world clock", row.id)
            worlds.append(_to_domain(row, clock))
        return worlds

    async def add(self, world: World) -> None:
        self._session.add(
            WorldRow(
                id=world.id,
                name=world.name,
                status=world.status.value,
                seed_version=world.seed_version,
                version=world.version,
            )
        )
        await self._session.flush()
        self._session.add(
            WorldClockRow(
                world_id=world.id,
                day=world.day,
                phase=world.phase.value,
                absolute_index=absolute_index(world.day, world.phase),
            )
        )
        await self._session.flush()

    async def save(self, world: World, expected_version: int) -> World:
        row = (
            await self._session.execute(
                select(WorldRow).where(WorldRow.id == world.id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("world", world.id)
        if row.version != expected_version:
            raise version_conflict("world", world.id, expected_version, row.version)
        row.name = world.name
        row.status = world.status.value
        row.seed_version = world.seed_version
        row.version = expected_version + 1
        await self._session.flush()
        return world.model_copy(update={"version": expected_version + 1})

    async def get_clock(self, world_id: UUID) -> tuple[int, str, int]:
        clock = await self._session.get(WorldClockRow, world_id)
        if clock is None:
            raise missing("world clock", world_id)
        return clock.day, clock.phase, clock.absolute_index

    async def set_clock(self, world_id: UUID, day: int, phase: str, absolute_index: int) -> None:
        clock = await self._session.get(WorldClockRow, world_id)
        if clock is None:
            raise missing("world clock", world_id)
        clock.day = day
        clock.phase = phase
        clock.absolute_index = absolute_index
        await self._session.flush()

    async def get_config(self, world_id: UUID) -> dict[str, object]:
        rows = (
            await self._session.execute(
                select(WorldConfigRow).where(WorldConfigRow.world_id == world_id)
            )
        ).scalars()
        return {row.key: row.value for row in rows}

    async def presentation_fingerprint(self, world_id: UUID) -> str:
        """One statement that changes whenever anything the presentation shows does."""
        row = (await self._session.execute(_FINGERPRINT, {"w": world_id})).scalar_one()
        return str(row)

    async def put_config(self, world_id: UUID, key: str, value: object) -> None:
        await self._session.execute(
            pg_insert(WorldConfigRow)
            .values(world_id=world_id, key=key, value=value)
            .on_conflict_do_update(index_elements=["world_id", "key"], set_={"value": value})
        )
        await self._session.flush()


#: Every input of ``queries.presentation.presentation`` in one round trip:
#: versions only grow, so count + sum(version) moves on any insert, update
#: or delete; small or unversioned tables are hashed whole (perf-reads-001).
#: A new input of the presentation MUST be added here and to
#: tests/test_presentation_fingerprint.py, or fingerprint mode shows it stale.
_FINGERPRINT = text(
    """
    select concat_ws('|',
      (select version || ':' || status || ':' || coalesce(updated_at::text, '')
         from world where id = :w),
      (select absolute_index from world_clock where world_id = :w),
      (select count(*) || ':' || coalesce(max(updated_at)::text, '')
              || ':' || coalesce(string_agg(state, '' order by created_at desc), '')
         from phase_run where world_id = :w),
      (select count(*) || ':' || coalesce(sum(version), 0) from location where world_id = :w),
      (select md5(coalesce(string_agg(id::text || name, ',' order by id), ''))
         from character where world_id = :w),
      (select count(*) || ':' || coalesce(sum(version), 0)
         from character_state where world_id = :w),
      (select count(*) || ':' || coalesce(sum(version), 0) from activity where world_id = :w),
      (select count(*) || ':' || coalesce(sum(version), 0)
         from narrative_hook where world_id = :w),
      (select coalesce(max(sequence), 0) from world_event where world_id = :w),
      (select count(*) || ':' || coalesce(sum(version), 0)
         from asset_record where world_id = :w),
      (select md5(coalesce(string_agg(key || value::text, ',' order by key), ''))
         from world_config where world_id = :w),
      (select md5(coalesce(string_agg(id::text || job_id::text
                  || coalesce(repaint_job_id::text, '') || coalesce(title, '')
                  || coalesce(caption, ''), ',' order by id), ''))
         from scene_picture where world_id = :w),
      (select count(*) || ':' || coalesce(sum(version), 0)
              || ':' || md5(coalesce(string_agg(status, '' order by id), ''))
         from image_job where world_id = :w)
    )
    """
)
