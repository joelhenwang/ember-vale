"""Stage 0 deterministic test harness (owned by S0-QA-001)."""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterator
from typing import Any, cast

import pytest

from worldsim.infrastructure.settings import Settings

# No background autoplay runner in test apps: it would poll every scratch
# database each second. Autoplay tests drive AutoplayRunner.tick directly.
os.environ.setdefault("WORLDSIM_AUTOPLAY__ENABLED", "false")


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


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Long simulations get a longer per-test timeout than the 120 s default."""
    for item in items:
        if item.get_closest_marker("sim_gate") or item.get_closest_marker("soak"):
            item.add_marker(pytest.mark.timeout(900))
