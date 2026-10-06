"""Rumours settle: the director closes finished hooks with an ending.

Before, nothing ever closed a hook and only three could be open, so a
long story's director could never open anything new again.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_meetups import _seed_connected
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.director import (
    MAX_ACTIVE_HOOKS,
    DirectorProposal,
    HookEnding,
    validate_proposal,
)
from worldsim.domain.enums import NarrativeStatus
from worldsim.domain.narrative import NarrativeHook
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

WORLD = uuid.uuid4()
OPEN = [uuid.uuid4() for _ in range(MAX_ACTIVE_HOOKS)]


def _validate(proposal: DirectorProposal, open_ids: list[uuid.UUID]):
    return validate_proposal(
        proposal,
        WORLD,
        frozenset(),
        len(open_ids),
        0,
        uuid.uuid4(),
        uuid.uuid4(),
        open_hook_ids=frozenset(open_ids),
    )


def test_settling_a_hook_frees_its_slot_for_a_new_one() -> None:
    full = DirectorProposal(action="propose_hook", title="A new rumour")
    assert _validate(full, OPEN).accepted is False  # three open: no room

    settled = full.model_copy(
        update={"resolved": [HookEnding(hook_id=OPEN[0], ending="The crate was sorted.")]}
    )
    decision = _validate(settled, OPEN)
    assert decision.accepted is True
    assert [c.hook_id for c in decision.closed] == [OPEN[0]]


def test_endings_count_alongside_noop_and_ignore_unknown_hooks() -> None:
    noop = DirectorProposal(
        action="noop",
        resolved=[
            HookEnding(hook_id=OPEN[1], ending="Tamsin's ghost was the wind."),
            HookEnding(hook_id=OPEN[1], ending="twice"),
            HookEnding(hook_id=uuid.uuid4(), ending="not a hook here"),
        ],
    )
    decision = _validate(noop, OPEN)
    assert decision.accepted is False
    assert [(c.hook_id, c.ending) for c in decision.closed] == [
        (OPEN[1], "Tamsin's ghost was the wind.")
    ]


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_a_settled_rumour_leaves_word_around_the_vale(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())
    crate = uuid.uuid4()

    async def open_hook() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.narrative.add_hook(
                    NarrativeHook(
                        id=crate,
                        world_id=ids["world"],
                        title="A Market-stall Puzzle",
                        purpose="Nessa's crate came with the wrong goods.",
                        status=NarrativeStatus.ACTIVE,
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(open_hook())
    base = _route_for(ids, {})
    summaries: list[str] = []

    def route(request: CompletionRequest) -> str | None:
        if "You direct" in (request.system or ""):
            summaries.append(request.prompt)
            return json.dumps(
                {
                    "action": "noop",
                    "reason": "story is moving",
                    "resolved": [{"hook_id": str(crate), "ending": "The crate got sorted."}],
                }
            )
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    assert f"hook_id {crate}" in summaries[0]

    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(ids["wren"])}
    view = client.get(
        "/api/v1/world/presentation", params={"world_id": str(ids["world"])}, headers=player
    ).json()
    assert view["rumours"] == []
    assert [(s["title"], s["purpose"]) for s in view["settled"]] == [
        ("A Market-stall Puzzle", "The crate got sorted.")
    ]
