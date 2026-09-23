import asyncio
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.db.verify import (
    MigrationReport,
    database_current,
    detect_multiple_heads,
    script_heads,
    verify,
)
from worldsim.infrastructure.settings import Settings


def _head() -> str:
    """Current single script head; lanes advance it without re-pinning tests."""
    heads = script_heads(_config())
    assert len(heads) == 1
    return heads[0]


def _migrations_dir() -> Path:
    return Path(__file__).parent.parent / "migrations"


def _replace_database(url: str, database: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{database}"))


@pytest.fixture
def scratch_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Create an invocation-unique scratch database; drop it after."""
    from fixtures.postgres import (
        create_scratch_database,
        drop_scratch_database,
        scratch_name,
    )

    name = scratch_name("worldsim_migtest")
    settings = Settings()
    create_scratch_database(settings, name)
    scratch_async = _replace_database(settings.database.url, name)
    monkeypatch.setenv("WORLDSIM_DATABASE__URL", scratch_async)
    yield scratch_async
    drop_scratch_database(Settings(), name)


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(_migrations_dir()))
    return config


async def _current() -> str | None:
    engine = create_engine(Settings())
    try:
        return await database_current(engine)
    finally:
        await engine.dispose()


async def _extension_present() -> int:
    engine = create_engine(Settings())
    try:
        async with engine.connect() as connection:
            value = (
                await connection.execute(
                    text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
                )
            ).scalar_one()
            assert isinstance(value, int)
            return value
    finally:
        await engine.dispose()


async def _report() -> MigrationReport:
    engine = create_engine(Settings())
    try:
        return await verify(engine, _config())
    finally:
        await engine.dispose()


def test_single_head_in_history() -> None:
    assert len(script_heads(_config())) == 1


def test_upgrade_downgrade_reupgrade_cycle(scratch_env: str) -> None:
    config = _config()
    alembic_command.downgrade(config, "base")
    assert asyncio.run(_current()) is None
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current()) == _head()
    assert asyncio.run(_extension_present()) == 1
    report = asyncio.run(_report())
    assert report.current == _head()
    assert report.heads == [_head()]
    assert not report.multiple_heads
    assert report.up_to_date
    alembic_command.downgrade(config, "base")
    assert asyncio.run(_current()) is None
    alembic_command.upgrade(config, "head")
    assert asyncio.run(_current()) == _head()


def test_detect_multiple_heads_in_tmp_dir(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    for revision in ("aaa", "bbb"):
        (versions / f"{revision}.py").write_text(
            f'revision = "{revision}"\ndown_revision = None\n\n'
            "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
            encoding="utf-8",
        )
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    heads = detect_multiple_heads(ScriptDirectory.from_config(config))
    assert sorted(heads) == ["aaa", "bbb"]
    assert len(detect_multiple_heads(ScriptDirectory.from_config(_config()))) == 1
