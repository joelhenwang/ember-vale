import asyncio

from sqlalchemy import text

from worldsim.infrastructure.db.engine import (
    check_connectivity,
    create_engine,
    session_factory,
)
from worldsim.infrastructure.settings import Settings


def test_engine_connects_and_disposes_cleanly() -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            version = await check_connectivity(engine)
            assert int(version.split(".")[0]) >= 16  # the server the app needs, or newer
            sessions = session_factory(engine)
            async with sessions() as session:
                value = (await session.execute(text("SELECT 1"))).scalar_one()
                assert value == 1
        finally:
            await engine.dispose()
        fresh = create_engine(Settings())
        try:
            assert await check_connectivity(fresh)
        finally:
            await fresh.dispose()

    asyncio.run(_inner())
