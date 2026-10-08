"""Background loops can run in their own process; the API can run without them."""

from __future__ import annotations

import argparse
import asyncio

import pytest

from worldsim.interfaces import cli
from worldsim.interfaces.worker import run


def test_the_worker_starts_its_loops_and_stops_cleanly(
    migrated_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORLDSIM_AUTOPLAY__ENABLED", "true")

    async def _inner() -> None:
        stop = asyncio.Event()
        worker = asyncio.create_task(run(stop))
        await asyncio.sleep(0.5)
        assert not worker.done()  # running its loops
        stop.set()
        await asyncio.wait_for(worker, timeout=20)

    asyncio.run(_inner())


def test_several_api_workers_need_the_loops_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_APP__WORKERS", "2")
    monkeypatch.setenv("WORLDSIM_APP__BACKGROUND_LOOPS", "true")
    assert cli._serve(argparse.Namespace(host=None, port=None)) == 2  # pyright: ignore[reportPrivateUsage]
