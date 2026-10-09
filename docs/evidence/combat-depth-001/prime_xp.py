"""Set a story's hero to a given XP total, so one goblin (50 XP) crosses the
level-2 threshold (300) in a short scripted run. Used only for the
screenshots; the README says so. Usage: python prime_xp.py <world_id> <xp>"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


async def main(world_id: UUID, xp: int) -> None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            for member in await uow.party.list_for_world(world_id):
                if member.character_id is None:
                    continue
                sheet = member.sheet.model_copy(deep=True)
                sheet.xp = xp
                await uow.party.save_sheet(member.id, sheet, member.version)
            await uow.commit()
    finally:
        await engine.dispose()


asyncio.run(main(UUID(sys.argv[1]), int(sys.argv[2])))
print("primed")
