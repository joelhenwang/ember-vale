import asyncio

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

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


def test_every_connection_carries_the_statement_timeout() -> None:
    async def _inner() -> None:
        settings = Settings()
        engine = create_engine(settings)
        try:
            async with engine.connect() as connection:
                shown = (await connection.execute(text("SHOW statement_timeout"))).scalar_one()
            assert shown == "1min"
        finally:
            await engine.dispose()
        quick = Settings.model_validate(
            {"database": {**settings.database.model_dump(), "statement_timeout_ms": 200}}
        )
        engine = create_engine(quick)
        try:
            async with engine.connect() as connection:
                try:
                    await connection.execute(text("SELECT pg_sleep(2)"))
                except DBAPIError as exc:
                    assert "statement timeout" in str(exc)
                else:
                    raise AssertionError("a 2 s statement outlived a 200 ms timeout")
        finally:
            await engine.dispose()

    asyncio.run(_inner())
