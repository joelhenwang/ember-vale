"""A place everyone keeps naming opens when someone sets out for it."""

from __future__ import annotations

import asyncio
import uuid

from test_stage1_orchestration import _orchestrator, _role_gateways, _seed

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.domain.commands import InteractAction
from worldsim.domain.ids import derive_intent_id
from worldsim.domain.narrative import NarrativeHook
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


async def _talk_of_the_mill_road(world: uuid.UUID, times: int) -> None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            for n in range(times):
                await uow.narrative.add_hook(
                    NarrativeHook(
                        id=uuid.uuid4(),
                        world_id=world,
                        title=f"Word of Old Bram {n}",
                        purpose="Old Bram lives past the mill road and mends wagons.",
                    )
                )
            await uow.commit()
    finally:
        await engine.dispose()


def _set_out(ids: dict[str, uuid.UUID]) -> dict[uuid.UUID, InteractAction]:
    return {
        ids["wren"]: InteractAction(
            character_id=ids["wren"],
            snapshot_id=derive_snapshot_id(derive_run_id(ids["world"], 1)),
            attempt="set out down the mill road to find Old Bram",
        )
    }


def test_setting_out_for_a_much_named_place_opens_it_and_goes(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()  # Wren at the Hearth
        await _talk_of_the_mill_road(ids["world"], 2)  # + the attempt itself: 3 mentions
        orch = _orchestrator(_role_gateways(ids))
        report = await orch.advance_phase(ids["world"], 1, _set_out(ids), submitter_id=ids["wren"])
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                places = {p.name: p for p in await uow.locations.list_for_world(ids["world"])}
                # "Mill" from the noun list; "Mill Road" when GLiNER has read the lines.
                opened = next(p for name, p in places.items() if name.startswith("Mill"))
                hearth = places["Hearth"]
                assert any(r.destination_location_id == opened.id for r in hearth.routes)
                intent = await uow.scenes.get_intent(
                    derive_intent_id(ids["world"], report.snapshot_id, ids["wren"])
                )
                assert intent.action.family.value == "move"  # the words became the move
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_a_place_named_once_stays_talk(migrated_db: None) -> None:
    async def _inner() -> None:
        ids = await _seed()
        orch = _orchestrator(_role_gateways(ids))
        await orch.advance_phase(ids["world"], 1, _set_out(ids), submitter_id=ids["wren"])
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                names = {p.name for p in await uow.locations.list_for_world(ids["world"])}
                assert names == {"Hearth", "Market"}
        finally:
            await engine.dispose()

    asyncio.run(_inner())
