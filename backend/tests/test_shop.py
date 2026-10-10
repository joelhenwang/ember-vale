"""Goods for sale in combat stories, bought with gold coins (shops-001).

- What a place sells follows from its name: a market, an inn, a smithy.
- A successful buying attempt takes the price from the purse and puts the
  good in the buyer's hands; a purse short of the price changes nothing.
- A healing potion heals when drunk, kept as the scene's dice.
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.domain.progress import ItemInstance
from worldsim.domain.rules.coins import COINS_KEY
from worldsim.domain.rules.dnd import HitPoints
from worldsim.domain.rules.shop import (
    drinks_potion,
    for_sale,
    good_named,
    load_goods,
    roll_heal,
    sale_line,
    seller_kind,
)
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

GOODS = load_goods(Path(__file__).parent.parent.parent / "content" / "definitions" / "shop.json")


def test_a_place_sells_by_what_its_name_reads_as() -> None:
    assert seller_kind("Market") == "market"
    assert seller_kind("The Rusty Anvil Smithy") == "smith"
    assert seller_kind("Hearth") == "inn"
    assert seller_kind("Old Mill") is None
    inn = [g.key for g in for_sale("Hearth", GOODS)]
    assert "room" in inn and "potion-of-healing" not in inn
    market = for_sale("Market", GOODS)
    assert "potion-of-healing" in [g.key for g in market]
    assert [g.price for g in market] == sorted(g.price for g in market)
    line = sale_line("Market", market)
    assert line is not None and line.startswith("For sale at Market (paid in gold coins): ")
    assert "potion of healing (6 gold coins)" in line and "rope (1 gold coin)" in line
    assert sale_line("Old Mill", []) is None


def test_the_words_name_what_is_bought() -> None:
    market = for_sale("Market", GOODS)
    assert good_named("I buy a healing potion from Bram", market) == GOODS["potion-of-healing"]
    assert good_named("Buy a coil of rope for 1 gold coin", market) == GOODS["rope"]
    assert (
        good_named("I pay the trader 3 gold coins for a healer's kit", market)
        == (GOODS["healers-kit"])
    )
    assert good_named("How much is the rope?", market) is None
    assert good_named("I look at the rope", market) is None
    assert good_named("I won't buy the rope", market) is None
    # Sold elsewhere: the market has no rooms.
    assert good_named("I rent a room for the night", market) is None


def test_a_potion_is_drunk_and_heals_its_dice() -> None:
    assert drinks_potion("I drink the potion of healing")
    assert drinks_potion("Wren uncorks the vial and gulps it down")
    assert not drinks_potion("I drink some ale")
    assert not drinks_potion("I buy a potion")
    rolls = {roll_heal("2d4+2", random.Random(seed)) for seed in range(200)}
    assert rolls == set(range(4, 11))


def _seed(world_id: UUID, wren: str, coins: int, potion: bool, hp: int | None) -> None:
    async def inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                owner = UUID(wren)
                if coins:
                    await uow.inventory.add_item(
                        ItemInstance(
                            id=uuid4(),
                            world_id=world_id,
                            item_key=COINS_KEY,
                            owner_id=owner,
                            quantity=coins,
                            name="gold coins",
                        )
                    )
                if potion:
                    good = GOODS["potion-of-healing"]
                    await uow.inventory.add_item(
                        ItemInstance(
                            id=uuid4(),
                            world_id=world_id,
                            item_key=good.key,
                            owner_id=owner,
                            name=good.name,
                        )
                    )
                if hp is not None:
                    (hero,) = await uow.party.list_for_world(world_id)
                    sheet = hero.sheet.model_copy(deep=True)
                    assert sheet.hp is not None
                    sheet.hp = HitPoints(current=hp, max=sheet.hp.max)
                    await uow.party.save_sheet(hero.id, sheet, hero.version)
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(inner())


def _held(world_id: UUID, wren: str) -> dict[str, int]:
    async def inner() -> dict[str, int]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return {
                    i.item_key: i.quantity
                    for i in await uow.inventory.list_for_owner(world_id, UUID(wren))
                }
        finally:
            await engine.dispose()

    return asyncio.run(inner())


def test_buying_at_the_inn_and_drinking_a_potion_through_turns(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "shop-story", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    _seed(world_id, wren, coins=1, potion=False, hp=None)
    told: list[str] = []

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": wren, "snapshot_id": wren})
        if "You resolve" in system:
            told.append(prompt)
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Done."})
        return None

    gateway.route = route

    def act(index: int, words: str) -> None:
        moved = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(world_id),
                "absolute_index": index,
                "player_intents": {
                    wren: {
                        "family": "interact",
                        "character_id": wren,
                        "snapshot_id": NIL_SNAPSHOT,
                        "attempt": words,
                    }
                },
            },
            headers=headers,
        )
        assert moved.status_code == 200, moved.text

    # The Hearth is an inn: Adventure is told what it sells, and the purse.
    shop = client.get("/api/v1/stage1/shop", params={"world_id": str(world_id)}, headers=headers)
    assert shop.status_code == 200, shop.text
    assert shop.json()["place"] == "Hearth" and shop.json()["purse"] == 1
    assert "room" in [g["key"] for g in shop.json()["goods"]]

    # A room costs 2: one coin buys nothing, and the resolver hears why.
    act(1, "I rent a room for the night")
    assert _held(world_id, wren) == {COINS_KEY: 1}
    assert "For sale at Hearth" in told[-1] and "so they cannot buy it" in told[-1]

    # A trail ration costs 1: bought, the purse is spent.
    act(2, "I buy a trail ration for the road")
    assert _held(world_id, wren) == {"ration": 1}

    # A potion in hand, the hero hurt: drinking it heals and is kept as dice.
    _seed(world_id, wren, coins=0, potion=True, hp=2)
    act(3, "I drink the potion of healing")
    assert "potion-of-healing" not in _held(world_id, wren)
    party = client.get("/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers)
    (hero,) = party.json()["members"]
    assert 6 <= hero["hp_current"] <= 12
    entries = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 80},
        headers=headers,
    ).json()["entries"]
    drunk = [
        r for e in entries if e["combat"] for r in e["combat"]["rolls"] if r["kind"] == "potion"
    ]
    assert len(drunk) == 1 and drunk[0]["hp_before"] == 2
    assert drunk[0]["hp_after"] == hero["hp_current"]


def test_a_story_without_fights_sells_nothing(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, _gateway = wired
    tale = {"role": "player", "controlled_cast_key": "cast-wren"}
    created = _create(client, tale, "shop-tale", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = created.json()["world_id"]
    shop = client.get(
        "/api/v1/stage1/shop",
        params={"world_id": world_id},
        headers={
            "X-Worldsim-Role": "player",
            "X-Worldsim-Character": created.json()["character_id"],
        },
    )
    assert shop.status_code == 200, shop.text
    assert shop.json()["goods"] == [] and shop.json()["place"] is None
