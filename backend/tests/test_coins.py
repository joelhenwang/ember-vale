"""Gold coins: a counted purse that grows when coins are picked up and
shrinks when a successful attempt pays (coins-001)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.application.commands.inventory import move_item
from worldsim.domain.progress import ItemInstance
from worldsim.domain.rules.coins import COINS_KEY, coins_paid
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def test_the_words_say_how_many_coins_are_paid() -> None:
    assert coins_paid("I pay the innkeeper 3 gold coins for a room") == 3
    assert coins_paid("Hand her a coin for her trouble") == 1
    assert coins_paid("I buy a loaf of bread for two coins") == 2
    assert coins_paid("I give Ash 5 gp") == 5
    assert coins_paid("I count my coins") is None
    assert coins_paid("I won't pay you 3 coins") is None
    assert coins_paid("I'll give you 10 coins if you help") is None


def _coins(world_id: UUID, quantity: int, owner: UUID | None, place: UUID | None) -> ItemInstance:
    return ItemInstance(
        id=uuid4(),
        world_id=world_id,
        item_key=COINS_KEY,
        owner_id=owner,
        location_id=place,
        quantity=quantity,
        name="gold coins",
    )


def _purses(world_id: UUID) -> dict[UUID | None, list[int]]:
    async def inner() -> dict[UUID | None, list[int]]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                found: dict[UUID | None, list[int]] = {}
                for item in await uow.inventory.list_for_world(world_id):
                    if item.item_key == COINS_KEY:
                        found.setdefault(item.owner_id, []).append(item.quantity)
                return found
        finally:
            await engine.dispose()

    return asyncio.run(inner())


def test_picked_up_coins_join_the_purse_and_paying_hands_them_over(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "coin-story", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ash = next(c["character_id"] for c in cast if c["name"] == "Ash")

    async def seed() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                hero = await uow.characters.get(UUID(wren))
                await uow.inventory.add_item(_coins(world_id, 4, hero.id, None))
                lying = _coins(world_id, 3, None, hero.location_id)
                await uow.inventory.add_item(lying)
                held = await move_item(uow, lying, hero.id)
                assert held.quantity == 7
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(seed())
    assert _purses(world_id) == {UUID(wren): [7]}

    def route(request: Any) -> str | None:
        system = request.system or ""
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": ash, "snapshot_id": ash})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Paid."})
        return None

    gateway.route = route
    paid = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": 1,
            "player_intents": {
                wren: {
                    "family": "interact",
                    "character_id": wren,
                    "snapshot_id": NIL_SNAPSHOT,
                    "attempt": "I pay Ash 3 gold coins for the map",
                    "target_character_id": ash,
                }
            },
        },
        headers=headers,
    )
    assert paid.status_code == 200, paid.text
    assert _purses(world_id) == {UUID(wren): [4], UUID(ash): [3]}


def test_the_resolver_hears_an_empty_purse() -> None:
    from worldsim.application.orchestration.stage1 import purse_notes
    from worldsim.domain.characters import Character
    from worldsim.domain.commands import InteractAction
    from worldsim.domain.scenes import Intent

    world, wren = uuid4(), uuid4()
    me = Character.model_construct(id=wren, world_id=world, name="Wren")

    def paying(words: str) -> Intent:
        return Intent(
            id=uuid4(),
            world_id=world,
            snapshot_id=uuid4(),
            phase_run_id=uuid4(),
            author_character_id=wren,
            idempotency_key=words,
            action=InteractAction(character_id=wren, snapshot_id=uuid4(), attempt=words),
        )

    pay = [paying("I pay Ash 2 gold coins")]
    assert purse_notes(pay, [me], []) == ["Wren carries no coins: they cannot pay 2."]
    one = [_coins(world, 1, wren, None)]
    assert purse_notes(pay, [me], one) == ["Wren carries only 1 gold coin: they cannot pay 2."]
    assert purse_notes(pay, [me], [_coins(world, 5, wren, None)]) == []
