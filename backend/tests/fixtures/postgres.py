"""PostgreSQL test helpers (owned by S0-QA-001; scratch support added by S0-UOW-001)."""

from __future__ import annotations

import os
import re
import time
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
    # The creation time in the name lets a later run sweep leftovers safely.
    return f"{base}_{worker}_t{int(time.time())}_{uuid4().hex[:8]}"


#: Scratch databases of killed runs are swept once they are this old.
STALE_AFTER_S = 6 * 3600
_STAMP = re.compile(r"^worldsim_stage0_(?:template|test)_[A-Za-z0-9]+_t(\d{10})_[0-9a-f]{8}$")


def sweep_stale_scratch(settings: Settings, now: float | None = None) -> list[str]:
    """Drop scratch databases left by killed runs; returns the names dropped.

    Only names carrying a creation stamp older than STALE_AFTER_S, and only
    databases nobody is connected to: a concurrent run (another session,
    another agent) is never touched.
    """
    cutoff = (now if now is not None else time.time()) - STALE_AFTER_S
    dropped: list[str] = []
    admin = connect(_maintenance_dsn(settings), autocommit=True)
    try:
        rows = admin.execute(
            "SELECT d.datname FROM pg_database d WHERE d.datname LIKE 'worldsim_stage0_%' "
            "AND NOT EXISTS (SELECT 1 FROM pg_stat_activity a WHERE a.datname = d.datname)"
        ).fetchall()
        for (name,) in rows:
            match = _STAMP.match(name)
            if match is None or int(match.group(1)) > cutoff:
                continue
            try:
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
            except Exception:  # someone connected meanwhile: leave it
                continue
            dropped.append(name)
    finally:
        admin.close()
    return dropped


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
