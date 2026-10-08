"""Scratch databases left by killed runs are swept; live ones never are."""

from __future__ import annotations

import time

from fixtures.postgres import (
    STALE_AFTER_S,
    create_scratch_database,
    drop_scratch_database,
    sweep_stale_scratch,
)
from psycopg import connect

from worldsim.infrastructure.settings import Settings


def _exists(settings: Settings, name: str) -> bool:
    from fixtures.postgres import replace_database, sync_dsn

    with connect(replace_database(sync_dsn(settings), "postgres"), autocommit=True) as admin:
        return (
            admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
            is not None
        )


def test_only_old_unconnected_scratch_databases_are_swept() -> None:
    settings = Settings()
    now = time.time()
    old = f"worldsim_stage0_test_sweep_t{int(now - STALE_AFTER_S - 60)}_0000beef"
    fresh = f"worldsim_stage0_test_sweep_t{int(now)}_0000cafe"
    for name in (old, fresh):
        create_scratch_database(settings, name)
    try:
        dropped = sweep_stale_scratch(settings, now=now)
        assert old in dropped and fresh not in dropped
        assert not _exists(settings, old)
        assert _exists(settings, fresh)
    finally:
        for name in (old, fresh):
            drop_scratch_database(settings, name)
