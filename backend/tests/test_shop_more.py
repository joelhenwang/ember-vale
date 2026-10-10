"""Shops, second round (shops-002): a room rests you, a shield guards a
calling trained with it, and goods and spoils sell back."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_shop import _held, _seed
from test_stage1_api import ApiClient

from worldsim.domain.progress import ItemInstance
from worldsim.domain.rules.coins import COINS_KEY
from worldsim.domain.rules.dnd import Sheet, auto_sheet, load_data
from worldsim.domain.rules.dnd.data import table
from worldsim.domain.rules.dnd.sheets import armor_ac
from worldsim.domain.rules.shop import (
    buyback_line,
    equip_bought,
    load_goods,
    sell_price,
    seller_kind,
    sold_item,
)
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")
GOODS = load_goods(ROOT / "content" / "definitions" / "shop.json")
WEAPONS = table(DATA, "weapons")


def test_a_place_buys_back_its_own_goods_at_half_and_spoils_at_a_set_price() -> None:
    market, smith, inn = seller_kind("Market"), seller_kind("Old Forge"), seller_kind("Hearth")
    assert sell_price("potion-of-healing", market, GOODS, WEAPONS) == 3  # 6 // 2
    assert sell_price("rope", market, GOODS, WEAPONS) == 0  # a one-coin good is worth nothing back
    assert sell_price("potion-of-healing", inn, GOODS, WEAPONS) == 0  # the inn does not sell it
    assert sell_price("scimitar", smith, GOODS, WEAPONS) == 3  # a fallen goblin's blade
    assert sell_price("scimitar", market, GOODS, WEAPONS) == 2
    assert sell_price("wolf-pelt", market, GOODS, WEAPONS) == 2
    assert sell_price("wolf-pelt", smith, GOODS, WEAPONS) == 0
    assert sell_price("scimitar", None, GOODS, WEAPONS) == 0
    line = buyback_line("Market", market)
    assert line is not None and "a pelt for 2 gold coins" in line


def test_the_words_name_what_is_sold() -> None:
    held = [("a", "scimitar"), ("b", "wolf pelt"), ("c", "potion of healing")]
    assert sold_item("I sell the scimitar to the trader", held) == "a"
    assert sold_item("I sell both wolf pelts", held) == "b"
    assert sold_item("How much would you give for my scimitar?", held) is None
    assert sold_item("I won't sell the potion of healing", held) is None
    assert sold_item("I sell my boots", held) is None


def test_a_shield_guards_only_a_calling_trained_with_it() -> None:
    ranger = auto_sheet("Wren", "human", "ranger", 1, DATA)
    assert not ranger.shield
    before = armor_ac(DATA, ranger)
    assert equip_bought(ranger, "shield", WEAPONS) and ranger.shield
    assert armor_ac(DATA, ranger) == before + 2
    wizard: Sheet = auto_sheet("Lyra", "elf", "wizard", 1, DATA)
    assert not equip_bought(wizard, "shield", WEAPONS) and not wizard.shield
    assert equip_bought(wizard, "dagger", WEAPONS) is (
        "dagger" not in auto_sheet("Lyra", "elf", "wizard", 1, DATA).weapons
    )


def _give(world_id: UUID, wren: str, item_key: str, name: str) -> None:
    async def inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.inventory.add_item(
                    ItemInstance(
                        id=uuid4(),
                        world_id=world_id,
                        item_key=item_key,
                        owner_id=UUID(wren),
                        name=name,
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(inner())


def _stamina(world_id: UUID, wren: str) -> int:
    async def inner() -> int:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return (await uow.characters.get(UUID(wren))).stamina
        finally:
            await engine.dispose()

    return asyncio.run(inner())


def test_spoils_sell_at_the_market_and_pay_for_a_room_that_rests_the_hero(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "shop-two", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    _seed(world_id, wren, coins=0, potion=False, hp=3)
    _give(world_id, wren, "scimitar", "scimitar")
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

    def act(index: int, intent: dict[str, Any]) -> None:
        moved = client.post(
            "/api/v1/stage1/advance",
            json={
                "world_id": str(world_id),
                "absolute_index": index,
                "player_intents": {
                    wren: {**intent, "character_id": wren, "snapshot_id": NIL_SNAPSHOT}
                },
            },
            headers=headers,
        )
        assert moved.status_code == 200, moved.text

    places = {
        p["name"]: p["id"]
        for p in client.get(
            "/api/v1/stage2/map", params={"world_id": str(world_id)}, headers=headers
        ).json()["places"]
    }
    # To the market with a fallen goblin's scimitar: the shop offers to buy it.
    act(1, {"family": "move", "destination_location_id": places["Market"]})
    shop = client.get("/api/v1/stage1/shop", params={"world_id": str(world_id)}, headers=headers)
    assert [(b["name"], b["price"]) for b in shop.json()["buys"]] == [("scimitar", 2)]
    act(2, {"family": "interact", "attempt": "I sell the scimitar to the trader"})
    assert _held(world_id, wren) == {COINS_KEY: 2}
    assert "Market pays 2 gold coins for Wren's scimitar" in told[-1]

    # Back at the inn, the two coins pay for a room: the hero wakes rested.
    act(3, {"family": "move", "destination_location_id": places["Hearth"]})
    assert _stamina(world_id, wren) < 100
    act(4, {"family": "interact", "attempt": "I rent a room for the night"})
    assert COINS_KEY not in _held(world_id, wren)
    party = client.get("/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers)
    (hero,) = party.json()["members"]
    assert hero["hp_current"] == hero["hp_max"]
    assert _stamina(world_id, wren) == 100
    entries = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 80},
        headers=headers,
    ).json()["entries"]
    kinds = [r["kind"] for e in entries if e["combat"] for r in e["combat"]["rolls"]]
    assert kinds.count("rest") == 1 and kinds.count("sell") == 1
