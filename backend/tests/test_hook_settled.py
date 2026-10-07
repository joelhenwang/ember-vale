"""Settling: a successful attempt that finishes a rumour's matter closes it."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_meetups import _seed_connected
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for

from worldsim.application.graphs.resolve import keep_fair_settles
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.enums import NarrativeStatus
from worldsim.domain.narrative import NarrativeHook
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def _settle(hook: str, ending: str = "The wheel rolls free.", who: str = "wren") -> dict[str, Any]:
    return {
        "effect_type": "hook_settled",
        "affected_ids": [who],
        "hook_id": hook,
        "ending": ending,
    }


def test_settles_only_open_rumours_on_success_once() -> None:
    raw = json.dumps(
        {
            "outcome": "success",
            "effects": [_settle("closed"), _settle("open"), _settle("open2"), _settle("open", "")],
        }
    )
    kept = json.loads(keep_fair_settles(raw, frozenset({"wren"}), frozenset({"open", "open2"})))
    assert [e["hook_id"] for e in kept["effects"]] == ["open"]
    failed = json.dumps({"outcome": "partial", "effects": [_settle("open")]})
    assert (
        json.loads(keep_fair_settles(failed, frozenset({"wren"}), frozenset({"open"})))["effects"]
        == []
    )
    # A settle credited to someone who did not act goes to an actor instead.
    other = json.dumps({"outcome": "success", "effects": [_settle("open", who="ghost")]})
    effect = json.loads(keep_fair_settles(other, frozenset({"wren"}), frozenset({"open"})))[
        "effects"
    ][0]
    assert effect["affected_ids"] == ["wren"]


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


async def _add_hook(world: uuid.UUID) -> uuid.UUID:
    hook_id = uuid.uuid4()
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await uow.narrative.add_hook(
                NarrativeHook(
                    id=hook_id,
                    world_id=world,
                    title="The stuck cart",
                    purpose="Old Marg's wheel is sunk in the mud.",
                )
            )
            await uow.commit()
    finally:
        await engine.dispose()
    return hook_id


async def _hook(hook_id: uuid.UUID) -> NarrativeHook:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return await uow.narrative.get_hook(hook_id)
    finally:
        await engine.dispose()


def test_freeing_the_wheel_settles_the_rumour(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())
    wren = str(ids["wren"])
    hook_id = asyncio.run(_add_hook(ids["world"]))
    base = _route_for(ids, {})
    resolver_prompts: list[str] = []

    def route(request: CompletionRequest) -> str | None:
        if (
            "You resolve one scene" in (request.system or "")
            and "heave the wheel" in request.prompt
        ):
            resolver_prompts.append(request.prompt)
            return json.dumps(
                {
                    "outcome": "success",
                    "rationale": "Wren has the leverage.",
                    "effects": [_settle(str(hook_id), "Marg's cart rolls free at last.", wren)],
                }
            )
        return base(request)

    gateway.route = route
    attempt: dict[str, Any] = {
        wren: {
            "family": "interact",
            "character_id": wren,
            "snapshot_id": str(uuid.UUID(int=0)),
            "attempt": "heave the wheel out of the mud",
        }
    }
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    response = _advance(client, ids["world"], 1, attempt, headers=player)
    assert response.status_code == 200, response.text

    # The resolver can name the rumour it settles.
    assert f"hook_id {hook_id}" in resolver_prompts[0]
    assert "The stuck cart" in resolver_prompts[0]
    hook = asyncio.run(_hook(hook_id))
    assert hook.status == NarrativeStatus.CLOSED
    assert hook.ending == "Marg's cart rolls free at last."
    assert hook.closed_phase_index is not None
