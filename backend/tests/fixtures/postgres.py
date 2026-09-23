"""PostgreSQL test helpers (owned by S0-QA-001; scratch support added by S0-UOW-001)."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from alembic import command as alembic_command
from alembic.config import Config
from psycopg import connect, sql

from worldsim.infrastructure.db.urls import to_sync_url
from worldsim.infrastructure.settings import Settings


def sync_dsn(settings: Settings) -> str:
    """Convert the async SQLAlchemy URL into a sync psycopg DSN."""
    return to_sync_url(settings.database.url)


def replace_database(url: str, database: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{database}"))


def _maintenance_dsn(settings: Settings) -> str:
    return replace_database(sync_dsn(settings), "postgres")


def create_scratch_database(settings: Settings, name: str) -> None:
    admin = connect(_maintenance_dsn(settings), autocommit=True)
    try:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    finally:
        admin.close()


def drop_scratch_database(settings: Settings, name: str) -> None:
    admin = connect(_maintenance_dsn(settings), autocommit=True)
    try:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
    finally:
        admin.close()


def scratch_name(base: str) -> str:
    """Invocation-unique scratch database name.

    Namespaces by pytest-xdist worker (when present) plus a random
    suffix so parallel workers and overlapping agent sessions never
    share or drop each other's databases.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    return f"{base}_{worker}_{uuid4().hex[:8]}"


def clone_database(settings: Settings, template: str, name: str) -> None:
    """Create a scratch database as a file-level copy of a template.

    ``CREATE DATABASE ... WITH TEMPLATE`` avoids replaying the full
    migration history per test; the copy carries seed rows, triggers,
    indexes, and extensions. The template must have no open
    connections (alembic uses NullPool and disposes its engine).
    """
    admin = connect(_maintenance_dsn(settings), autocommit=True)
    try:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin.execute(
            sql.SQL("CREATE DATABASE {} WITH TEMPLATE {}").format(
                sql.Identifier(name), sql.Identifier(template)
            )
        )
    finally:
        admin.close()


def upgrade_head() -> None:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parent.parent.parent / "migrations")
    )
    alembic_command.upgrade(config, "head")
