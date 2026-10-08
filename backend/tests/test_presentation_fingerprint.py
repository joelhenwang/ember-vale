"""The presentation fingerprint moves whenever the presentation does (perf-reads-001 §9).

A scripted story: turns across a day's end, a rumour opened and settled, a
config change, a portrait painted. After every step, for a watcher and for
a player, a presentation that changed must come with a changed fingerprint.
A miss here is a stale screen in fingerprint mode.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from test_s3_memory import WORLD_ID, WREN_ID, _advance, _route_for
from test_s3_memory import mem as mem  # the fixture
from test_stage1_api import ApiClient

from worldsim.application.capabilities import parse_role
from worldsim.application.queries.presentation import presentation
from worldsim.domain.enums import NarrativeStatus
from worldsim.domain.narrative import NarrativeHook
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

VIEWS = [("watcher", None), ("player", WREN_ID)]


async def _look() -> dict[str, tuple[str, str]]:
    engine = create_engine(Settings())
    try:
        out: dict[str, tuple[str, str]] = {}
        for role, viewer in VIEWS:
            async with create_unit_of_work(engine) as uow:
                body = await presentation(uow, WORLD_ID, parse_role(role), viewer)
                seen = await uow.worlds.presentation_fingerprint(WORLD_ID)
            out[role] = (seen, body.model_dump_json())
        return out
    finally:
        await engine.dispose()


async def _write(change: Callable[[Any], Awaitable[None]]) -> None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await change(uow)
            await uow.commit()
    finally:
        await engine.dispose()


def test_a_changed_presentation_always_changes_the_fingerprint(
    mem: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = mem
    gateway.route = _route_for(probe_on_first=True)
    headers = {"X-Worldsim-Role": "watcher"}
    client.post("/api/v1/world/seed", headers=headers)
    hook_id = uuid4()

    async def open_rumour(uow: Any) -> None:
        await uow.narrative.add_hook(
            NarrativeHook(
                id=hook_id,
                world_id=WORLD_ID,
                title="A lantern goes missing",
                purpose="Someone took the bridge lantern.",
                status=NarrativeStatus.ACTIVE,
                created_phase_index=3,
            )
        )

    async def settle_rumour(uow: Any) -> None:
        await uow.narrative.close_hook(hook_id, "It was found by the well.", 4)

    async def move_the_map(uow: Any) -> None:
        await uow.worlds.put_config(WORLD_ID, "portrait_frames", {"x": [0.1, 0.2]})

    steps: list[tuple[str, Callable[[], None]]] = [
        *[(f"turn {i}", lambda i=i: _advance(client, headers, i, i)) for i in range(1, 13)],
        ("rumour opened", lambda: asyncio.run(_write(open_rumour))),
        ("rumour settled", lambda: asyncio.run(_write(settle_rumour))),
        ("config changed", lambda: asyncio.run(_write(move_the_map))),
    ]
    before = asyncio.run(_look())
    changed_steps = 0
    for name, step in steps:
        step()
        after = asyncio.run(_look())
        for role, _viewer in VIEWS:
            (old_seen, old_body), (new_seen, new_body) = before[role], after[role]
            if new_body != old_body:
                changed_steps += 1
                assert new_seen != old_seen, (
                    f"{name}: {role}'s presentation changed, fingerprint did not"
                )
        before = after
    assert changed_steps >= len(steps)  # the script really moved the screens
