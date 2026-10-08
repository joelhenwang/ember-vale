"""Old salient observations and memories a context considers are capped (perf-reads-001)."""

from __future__ import annotations

import asyncio

from sqlalchemy import update
from test_s3_memory import WREN_ID, _advance, _route_for
from test_s3_memory import mem as mem  # the fixture
from test_stage1_api import ApiClient

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.models.perception import ObservationRow, RecentMemoryRow
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def test_older_salient_rows_are_capped_and_recent_ones_kept(
    mem: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = mem
    gateway.route = _route_for(probe_on_first=True)
    headers = {"X-Worldsim-Role": "watcher"}
    client.post("/api/v1/world/seed", headers=headers)
    _advance(client, headers, 1, 8)
    since = 6

    async def _check() -> None:
        engine = create_engine(Settings())
        try:
            async with engine.begin() as conn:
                # Every row salient, so all older rows compete for the cap.
                await conn.execute(
                    update(ObservationRow)
                    .where(ObservationRow.observer_character_id == WREN_ID)
                    .values(salience=3.0)
                )
                await conn.execute(
                    update(RecentMemoryRow)
                    .where(RecentMemoryRow.owner_character_id == WREN_ID)
                    .values(salience=3.0)
                )
            async with create_unit_of_work(engine) as uow:
                perception = uow.perception
                every = await perception.observations_for_observer(
                    WREN_ID, 100000, since_phase_index=since, min_salience=2.0
                )
                capped = await perception.observations_for_observer(
                    WREN_ID, 100000, since_phase_index=since, min_salience=2.0, older_limit=2
                )
                recent = [o for o in every if o.created_phase_index >= since]
                older = [o for o in every if o.created_phase_index < since]
                assert recent and len(older) > 2
                kept = {o.id for o in capped}
                assert {o.id for o in recent} <= kept
                assert len(kept) == len(recent) + 2
                newest_older = sorted(o.created_phase_index for o in older)[-2:]
                assert (
                    sorted(o.created_phase_index for o in capped if o.created_phase_index < since)
                    == newest_older
                )
                indexes = [o.created_phase_index for o in capped]
                assert indexes == sorted(indexes, reverse=True)  # newest first, as before

                memories = await perception.memories_for_owner(
                    WREN_ID, since_phase_index=since, min_salience=2.0, older_limit=1
                )
                all_memories = await perception.memories_for_owner(
                    WREN_ID, since_phase_index=since, min_salience=2.0
                )
                older_memories = [m for m in all_memories if m.created_phase_index < since]
                assert len(memories) == len(all_memories) - max(0, len(older_memories) - 1)
                order = [m.created_phase_index for m in memories]
                assert order == sorted(order)  # oldest first, as before
                # Without a cap nothing changes.
                assert [o.id for o in every] == [
                    o.id
                    for o in await perception.observations_for_observer(
                        WREN_ID, 100000, since_phase_index=since, min_salience=2.0
                    )
                ]
        finally:
            await engine.dispose()

    asyncio.run(_check())
