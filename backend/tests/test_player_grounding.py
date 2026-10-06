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


def test_resolver_moves_only_those_who_tried_to_move() -> None:
    from worldsim.application.graphs.resolve import fill_move_endpoints

    raw = json.dumps(
        {
            "outcome": "success",
            "effects": [
                {"effect_type": "record_observation", "affected_ids": ["ash"]},
                {"effect_type": "move_entity", "affected_ids": ["wren"], "to_location_id": "x"},
                {"effect_type": "move_entity", "affected_ids": ["ash"], "to_location_id": "market"},
            ],
        }
    )
    out = json.loads(fill_move_endpoints(raw, {"wren": ("hearth-id", "market-id")}))
    assert [e["effect_type"] for e in out["effects"]] == ["record_observation", "move_entity"]
    assert out["effects"][1]["from_location_id"] == "hearth-id"
    assert out["effects"][1]["to_location_id"] == "market-id"


def test_no_spar_offered_without_seated_sheets(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    """Quick Start casts have no party sheets: a bout would only fail the turn."""
    client, _ = stage1_client
    ids = asyncio.run(_seed_connected())

    async def bring_ash_home() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                ash = await uow.characters.get(ids["ash"])
                await uow.characters.save_state(
                    ash.model_copy(update={"location_id": ids["hearth"]}), ash.version
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(bring_ash_home())
    wren = str(ids["wren"])
    offered = client.get(
        "/api/v1/stage1/suggestions",
        params={"character_id": wren},
        headers={"X-Worldsim-Role": "player", "X-Worldsim-Character": wren},
    ).json()
    families = {s["family"] for s in offered}
    assert "communicate" in families  # Ash is here to talk to
    assert "spar" not in families


def test_carried_items_can_be_given_to_someone_here(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    from worldsim.domain.progress import ItemInstance

    client, _ = stage1_client
    ids = asyncio.run(_seed_connected())
    locket = uuid.uuid4()

    async def set_scene() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                ash = await uow.characters.get(ids["ash"])
                await uow.characters.save_state(
                    ash.model_copy(update={"location_id": ids["hearth"]}), ash.version
                )
                await uow.inventory.add_item(
                    ItemInstance(
                        id=locket,
                        world_id=ids["world"],
                        item_key="placed_item",
                        owner_id=ids["wren"],
                        name="Silver locket",
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(set_scene())
    wren = str(ids["wren"])
    offered = client.get(
        "/api/v1/stage1/suggestions",
        params={"character_id": wren},
        headers={"X-Worldsim-Role": "player", "X-Worldsim-Character": wren},
    ).json()
    give = [s for s in offered if s["family"] == "transfer"]
    assert [(s["title"], s["item_instance_id"], s["target_character_id"]) for s in give] == [
        ("Give the Silver locket to Ash", str(locket), str(ids["ash"]))
    ]
