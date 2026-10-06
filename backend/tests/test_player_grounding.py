"""A player's "Do" that plainly travels moves them; the words reach the narrator."""

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

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.commands import InteractAction, MoveAction
from worldsim.domain.rules.grounding import destination_named, grounded_move
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

MARKET, MILL = uuid.uuid4(), uuid.uuid4()
REACHABLE = {MARKET: "Market", MILL: "Old Mill"}


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("carry two cups out toward the market to find Ash", MARKET),
        ("walk over to the Old Mill", MILL),
        ("head back to the market", MARKET),
        ("search the market stalls", None),  # no direction: an attempt here
        ("go to the market or to the old mill", None),  # two places: too unclear
        ("go to the forge", None),  # not one route away
    ],
)
def test_destination_needs_a_direction_and_one_reachable_place(
    words: str, expected: uuid.UUID | None
) -> None:
    assert destination_named(words, REACHABLE) == expected


def test_an_aimed_attempt_is_left_alone() -> None:
    attempt = InteractAction(
        character_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        attempt="hand the cup to Ash at the market",
        target_character_id=uuid.uuid4(),
    )
    assert grounded_move(attempt, REACHABLE) is None
    plain = attempt.model_copy(update={"target_character_id": None, "attempt": "run to the market"})
    move = grounded_move(plain, REACHABLE)
    assert isinstance(move, MoveAction)
    assert (move.destination_location_id, move.note) == (MARKET, "run to the market")


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_player_walks_where_their_words_go(stage1_client: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())  # Wren at the Hearth, Ash at the Market
    base = _route_for(ids, {})
    narrator_prompts: list[str] = []

    def route(request: CompletionRequest) -> str | None:
        if "narrat" in (request.system or "").lower():
            narrator_prompts.append(request.prompt)
        return base(request)

    gateway.route = route
    wren = str(ids["wren"])
    words = "brew strong tea and carry two cups out toward the market to find Ash"
    intents: dict[str, Any] = {
        wren: {
            "family": "interact",
            "character_id": wren,
            "snapshot_id": str(uuid.UUID(int=0)),
            "attempt": words,
        }
    }
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    response = _advance(client, ids["world"], 1, intents, headers=player)
    assert response.status_code == 200, response.text

    async def where() -> uuid.UUID:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return (await uow.characters.get(ids["wren"])).location_id
        finally:
            await engine.dispose()

    assert asyncio.run(where()) == ids["market"]
    assert any(json.dumps(words)[1:-1] in prompt for prompt in narrator_prompts)
