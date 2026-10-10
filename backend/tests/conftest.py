"""Stage 0 deterministic test harness (owned by S0-QA-001)."""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest

from worldsim.infrastructure.settings import Settings

# No background autoplay runner in test apps: it would poll every scratch
# database each second. Autoplay tests drive AutoplayRunner.tick directly.
os.environ.setdefault("WORLDSIM_AUTOPLAY__ENABLED", "false")
# Nor a picture sweep: test databases are scratch copies that know none of
# the files under content/assets/generated. Sweep tests drive it directly.
os.environ.setdefault("WORLDSIM_IMAGES__SWEEP_UNUSED", "false")
# Fights as written: tests check tags and dice; fair sizing has its own test.
os.environ.setdefault("WORLDSIM_APP__FAIR_FIGHTS", "false")


@pytest.fixture(autouse=True)
def _block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deny non-loopback TCP while letting localhost (PostgreSQL) through."""
    real_getaddrinfo: Any = socket.getaddrinfo
    real_connect: Any = socket.socket.connect

    def _guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        if (
            isinstance(host, str)
            and host != "localhost"
            and not host.startswith("127.")
            and host != "::1"
        ):
            raise socket.gaierror("external network blocked in tests")
        return real_getaddrinfo(host, port, *args, **kwargs)

    def _guarded_connect(sock: object, address: object, *args: object) -> Any:
        host: str | None = None
        if isinstance(address, tuple):
            parts = cast("tuple[object, ...]", address)
            if len(parts) > 0 and isinstance(parts[0], str):
                host = parts[0]
        elif isinstance(address, str):
            host = address
        if host is not None:
            try:
                if not ipaddress.ip_address(host).is_loopback:
                    raise OSError(f"external network blocked in tests: {host}")
            except ValueError:
                if host != "localhost":
                    raise OSError(f"external network blocked in tests: {host}") from None
        return real_connect(sock, address, *args)

    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


@pytest.fixture(scope="session")
def _db_template() -> Iterator[str]:
    """Fully migrated template database, built once per invocation.

    Application tests clone this template instead of replaying the
    migration history per test. Migration-history tests keep their
    own real upgrade/downgrade paths and never use this template.
    """
    import os

    from fixtures.postgres import (
        create_scratch_database,
        drop_scratch_database,
        replace_database,
        scratch_name,
        upgrade_head,
    )

    name = scratch_name("worldsim_stage0_template")
    settings = Settings()
    create_scratch_database(settings, name)
    previous = os.environ.get("WORLDSIM_DATABASE__URL")
    os.environ["WORLDSIM_DATABASE__URL"] = replace_database(settings.database.url, name)
    try:
        upgrade_head()
    finally:
        # Restore BEFORE yield: while tests run, the process environment
        # must never point at the template, or tests without migrated_db
        # (graph checkpointer, app defaults) open sessions on it and
        # block every later WITH TEMPLATE clone.
        if previous is None:
            os.environ.pop("WORLDSIM_DATABASE__URL", None)
        else:
            os.environ["WORLDSIM_DATABASE__URL"] = previous
    yield name
    drop_scratch_database(Settings(), name)


@pytest.fixture
def migrated_db(monkeypatch: pytest.MonkeyPatch, _db_template: str) -> Iterator[None]:
    """Scratch database cloned from the migration-head template."""
    from fixtures.postgres import (
        clone_database,
        drop_scratch_database,
        replace_database,
        scratch_name,
    )

    name = scratch_name("worldsim_stage0_test")
    settings = Settings()
    clone_database(settings, _db_template, name)
    monkeypatch.setenv(
        "WORLDSIM_DATABASE__URL",
        replace_database(settings.database.url, name),
    )
    yield
    drop_scratch_database(Settings(), name)


class DbSnapshots:
    """Databases holding a prepared story, built once per worker and cloned per test.

    Several tests start from the same played story (five turns take ~6 s);
    it is played once into its own database and every test gets a fresh
    copy of it (CREATE DATABASE ... TEMPLATE, as migrated_db), so tests
    still never share rows.
    """

    def __init__(self, template: str) -> None:
        self._template = template
        self._built: dict[str, tuple[str, Any]] = {}

    def get(self, key: str, build: Callable[[], Any]) -> tuple[str, Any]:
        if key not in self._built:
            from fixtures.postgres import clone_database, replace_database, scratch_name

            name = scratch_name("worldsim_stage0_template")
            settings = Settings()
            clone_database(settings, self._template, name)
            previous = os.environ.get("WORLDSIM_DATABASE__URL")
            os.environ["WORLDSIM_DATABASE__URL"] = replace_database(settings.database.url, name)
            try:
                # build must close every connection: clones need an idle source.
                self._built[key] = (name, build())
            finally:
                if previous is None:
                    os.environ.pop("WORLDSIM_DATABASE__URL", None)
                else:
                    os.environ["WORLDSIM_DATABASE__URL"] = previous
        return self._built[key]

    def names(self) -> list[str]:
        return [name for name, _ in self._built.values()]


@pytest.fixture(scope="session")
def _db_snapshots(_db_template: str) -> Iterator[DbSnapshots]:
    from fixtures.postgres import drop_scratch_database

    snapshots = DbSnapshots(_db_template)
    yield snapshots
    for name in snapshots.names():
        drop_scratch_database(Settings(), name)


@pytest.fixture
def snapshot_db(
    monkeypatch: pytest.MonkeyPatch, _db_snapshots: DbSnapshots
) -> Iterator[Callable[[str, Callable[[], Any]], Any]]:
    """``use(key, build)``: this test's database is a copy of the snapshot ``key``.

    ``build`` runs once per worker against a migrated database and returns
    what the tests need to know about it (ids, dumps); ``use`` returns that.
    The copy is dropped when the test ends, as migrated_db's is.
    """
    from fixtures.postgres import (
        clone_database,
        drop_scratch_database,
        replace_database,
        scratch_name,
    )

    names: list[str] = []

    def use(key: str, build: Callable[[], Any]) -> Any:
        source, value = _db_snapshots.get(key, build)
        name = scratch_name("worldsim_stage0_test")
        settings = Settings()
        clone_database(settings, source, name)
        names.append(name)
        monkeypatch.setenv("WORLDSIM_DATABASE__URL", replace_database(settings.database.url, name))
        return value

    yield use
    for name in names:
        drop_scratch_database(Settings(), name)


def pytest_sessionstart(session: pytest.Session) -> None:
    """Sweep scratch databases left by killed runs (controller only, best effort)."""
    if hasattr(session.config, "workerinput"):
        return
    try:
        from fixtures.postgres import sweep_stale_scratch

        sweep_stale_scratch(Settings())
    except Exception:  # no database configured or reachable: nothing to sweep
        return


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Long simulations get a longer per-test timeout than the 120 s default."""
    for item in items:
        if item.get_closest_marker("sim_gate") or item.get_closest_marker("soak"):
            item.add_marker(pytest.mark.timeout(900))
