"""Time a model call's trace writes, the old four statements against the new two
(perf-turn-002): start (call row + manifest) then finish (result + cost), each in
its own transaction as TraceService does. Needs WORLDSIM_DATABASE__URL; writes
rows with no world into model_call, context_manifest and model_cost, and deletes
them at the end.

  python scripts/trace_write_bench.py [rounds]
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from uuid import uuid4

from sqlalchemy import text

from worldsim.application.ports.traces import StoredCompletion
from worldsim.domain.costs import ModelCost
from worldsim.domain.enums import Visibility
from worldsim.domain.tracing import ContextManifest, ManifestSource, ModelCall
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

PROMPT = "You decide what to do next. " * 120


def _parts() -> tuple[ModelCall, ContextManifest, StoredCompletion, ModelCost]:
    call = ModelCall(
        id=uuid4(),
        world_id=None,
        profile_name="bench",
        profile_version="1",
        role="character_decision",
        prompt_hash="0" * 64,
    )
    manifest = ContextManifest(
        id=uuid4(),
        call_id=call.id,
        world_id=None,
        role="character_decision",
        profile_name="bench",
        profile_version="1",
        prompt_version="bench.v1",
        sources=[
            ManifestSource(
                source_id=f"obs:{i}", kind="observation", visibility=Visibility.PUBLIC, score=1.0
            )
            for i in range(12)
        ],
        budgets={"observations": 6000},
        tokens={"prompt": 900},
        dropped=[],
        rendered_hash="1" * 64,
    )
    done = StoredCompletion(
        text='{"family": "wait"}' * 4,
        model="bench",
        profile_version="1",
        prompt_tokens=900,
        completion_tokens=40,
        latency_ms=12,
    )
    cost = ModelCost(
        call_id=call.id,
        pricing_version="bench",
        model="bench",
        prompt_tokens=900,
        completion_tokens=40,
        prompt_cost_usd=0.0001,
        completion_cost_usd=0.00001,
    )
    return call, manifest, done, cost


async def main(rounds: int) -> None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await uow.traces.ensure_profile("bench", "1", "fake", "bench", 8000, [])
            await uow.commit()
        timings: dict[str, list[float]] = {"old": [], "new": []}
        ids = []
        for round_ in range(rounds):
            for way in ("old", "new") if round_ % 2 == 0 else ("new", "old"):
                call, manifest, done, cost = _parts()
                ids.append(call.id)
                started = time.perf_counter()
                async with create_unit_of_work(engine) as uow:
                    if way == "old":
                        await uow.traces.start_call(call, PROMPT, "bench.v1", 512, {})
                        await uow.traces.save_manifest(manifest)
                    else:
                        await uow.traces.start_call_with_manifest(
                            call, PROMPT, "bench.v1", 512, {}, manifest
                        )
                    await uow.commit()
                async with create_unit_of_work(engine) as uow:
                    if way == "old":
                        await uow.traces.finish_call(call.id, done)
                        await uow.costs.add(cost, None)
                    else:
                        await uow.traces.finish_call_with_cost(call.id, done, cost, None)
                    await uow.commit()
                timings[way].append((time.perf_counter() - started) * 1000)
        for way, values in timings.items():
            values = values[5:]
            print(
                f"{way}: median {statistics.median(values):.2f} ms, "
                f"mean {statistics.mean(values):.2f} ms over {len(values)} calls"
            )
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM model_cost WHERE call_id = ANY(:ids)"), {"ids": ids}
            )
            await conn.execute(
                text("DELETE FROM context_manifest WHERE call_id = ANY(:ids)"), {"ids": ids}
            )
            await conn.execute(text("DELETE FROM model_call WHERE id = ANY(:ids)"), {"ids": ids})
    finally:
        await engine.dispose()


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 200))
