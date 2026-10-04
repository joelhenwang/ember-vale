"""Reactions run concurrently across reactors yet keep a stable order."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

from worldsim.application.orchestration.stage1 import Stage1Orchestrator


def test_reactors_run_concurrently_and_results_keep_attempt_order() -> None:
    wren, ash, marlow, player = (uuid.uuid4() for _ in range(4))
    scene = SimpleNamespace(
        participants=[SimpleNamespace(character_id=c) for c in (wren, ash, marlow, player)]
    )
    attempts = [
        SimpleNamespace(id=uuid.uuid4(), actor_character_id=wren),
        SimpleNamespace(id=uuid.uuid4(), actor_character_id=marlow),
    ]
    runtime = SimpleNamespace(controlled_character_id=player)
    in_flight = 0
    peak = 0
    per_reactor: dict[uuid.UUID, list[Any]] = {}

    async def fake_react_one(
        _world: Any,
        _run: Any,
        _sealed: Any,
        _scene: Any,
        attempt: Any,
        reactor_id: uuid.UUID,
        *_rest: Any,
    ) -> tuple[Any, uuid.UUID]:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        per_reactor.setdefault(reactor_id, []).append(attempt.id)
        return (attempt.id, reactor_id)

    orchestrator: Any = object.__new__(Stage1Orchestrator)
    orchestrator._react_one = fake_react_one
    result = asyncio.run(
        orchestrator._react_all(uuid.uuid4(), uuid.uuid4(), None, scene, attempts, {}, runtime)
    )

    # Player never reacts; actors never react to themselves.
    assert result == [
        (attempts[0].id, ash),
        (attempts[0].id, marlow),
        (attempts[1].id, wren),
        (attempts[1].id, ash),
    ]
    assert peak >= 2
    # Each reactor still handles its attempts in order.
    assert per_reactor[ash] == [attempts[0].id, attempts[1].id]
