"""Shared phase reads never change a prompt (phase_reads, perf-beat-001 addendum)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from worldsim.application.orchestration import phase_reads

BENCH = Path(__file__).resolve().parents[1] / "scripts" / "beat_bench.py"


def _bench() -> Any:
    spec = importlib.util.spec_from_file_location("beat_bench", BENCH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("beat_bench", module)  # its dataclasses look themselves up
    spec.loader.exec_module(module)
    return module


def test_shared_reads_build_the_same_contexts_as_fresh_ones(
    migrated_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Beats with a director, several scenes and a day's end, every context
    built twice (shared and fresh) and compared byte for byte."""
    monkeypatch.setattr(phase_reads, "VERIFY", True)
    bench = _bench()

    async def _inner() -> None:
        from worldsim.application.orchestration.stage1 import Stage1Orchestrator
        from worldsim.application.tasks.service import TaskService
        from worldsim.application.tracing.service import TraceService
        from worldsim.application.transactions.canonical import CanonicalTransaction
        from worldsim.infrastructure.db.engine import create_engine
        from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
        from worldsim.infrastructure.settings import Settings
        from worldsim.infrastructure.tracing.langsmith import NullExporter

        engine = create_engine(Settings())
        try:
            seeded = await bench.seed(engine, 6, 3)
            script = bench.Script(seeded)
            gateway_for, profiles = bench.gateways(script)

            def factory() -> Any:
                return create_unit_of_work(engine)

            orchestrator = Stage1Orchestrator(
                factory,
                CanonicalTransaction(factory),
                TaskService(factory),
                TraceService(factory, NullExporter()),
                gateway_for,
                profiles,
            )
            for index in range(1, 7):
                await orchestrator.advance_phase(seeded.world, index, {}, drain_queue=True)
            assert script.calls.get("reaction", 0) > 0 and script.calls.get("director", 0) > 0
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_a_phase_read_is_loaded_once_and_forgotten_when_dropped() -> None:
    async def _inner() -> None:
        reads = phase_reads.PhaseReads()
        loads = 0

        async def load() -> int:
            nonlocal loads
            loads += 1
            await asyncio.sleep(0)
            return loads

        assert await asyncio.gather(*(reads.get("k", load) for _ in range(5))) == [1] * 5
        reads.drop()
        assert await reads.get("k", load) == 2

    asyncio.run(_inner())
