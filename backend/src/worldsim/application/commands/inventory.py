"""Inventory commands (owned by S2-PROGRESS-001).

Instances carry their single holder: giving sets it, transfer moves
it version-guarded, and ground items (no holder) wait where left.
Every change lands beside its audit command in one transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    CharacterId,
    ItemInstanceId,
    WorldId,
    new_item_instance_id,
)
from worldsim.domain.items import ItemDefinition
from worldsim.domain.progress import ItemInstance
from worldsim.domain.rules.coins import COINS_KEY, COINS_NAME
from worldsim.domain.rules.shop import Good


async def give_item(
    uow: UnitOfWork,
    actor_role: str,
    world_id: WorldId,
    item_key: str,
    owner_id: CharacterId | None,
    catalog: dict[str, ItemDefinition],
    quantity: int = 1,
) -> ItemInstance:
    """Create one instance for a holder (or the ground)."""
    if item_key not in catalog:
        raise DomainError(ErrorCode.NOT_FOUND, f"unknown item: {item_key}")
    if quantity < 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "quantity needs counting")
    if owner_id is not None:
        owner = await uow.characters.get(owner_id)
        if owner.world_id != world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "holder is not in this world")
    holder = owner_id.hex if owner_id else "ground"
    key = f"item-give:{world_id.hex}:{item_key}:{holder}:{uuid4().hex}"
    payload: dict[str, object] = {
        "item_key": item_key,
        "owner_id": str(owner_id) if owner_id else None,
        "quantity": quantity,
    }
    await uow.commands.add(
        command_id=uuid4(),
        world_id=world_id,
        key=key,
        actor_role=actor_role,
        command_type="give_item",
        expected_versions={},
        payload=payload,
        input_hash=canonical_input_hash({"key": key, "payload": payload}),
    )
    item = ItemInstance(
        id=new_item_instance_id(),
        world_id=world_id,
        item_key=item_key,
        owner_id=owner_id,
        quantity=quantity,
    )
    await uow.inventory.add_item(item)
    await uow.commit()
    return item


async def transfer_item(
    uow: UnitOfWork,
    actor_role: str,
    item_id: ItemInstanceId,
    to_owner_id: CharacterId | None,
) -> ItemInstance:
    """Move one instance to a new holder (or drop it)."""
    item = await uow.inventory.get_item(item_id)
    if to_owner_id is not None:
        owner = await uow.characters.get(to_owner_id)
        if owner.world_id != item.world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "holder is not in this world")
    if item.owner_id == to_owner_id:
        return item
    moved = await move_item(uow, item, to_owner_id)
    target = to_owner_id.hex if to_owner_id else "ground"
    key = f"item-transfer:{item.id.hex}:{target}:{uuid4().hex}"
    payload: dict[str, object] = {
        "item_id": str(item.id),
        "to_owner_id": str(to_owner_id) if to_owner_id else None,
    }
    await uow.commands.add(
        command_id=uuid4(),
        world_id=item.world_id,
        key=key,
        actor_role=actor_role,
        command_type="transfer_item",
        expected_versions={},
        payload=payload,
        input_hash=canonical_input_hash({"key": key, "payload": payload}),
    )
    await uow.commit()
    return moved


async def move_item(
    uow: UnitOfWork, item: ItemInstance, to_owner_id: CharacterId | None
) -> ItemInstance:
    """Version-guarded holder change without audit or commit (see fold_claim).

    Coins join the purse the new holder already carries (coins-001).
    """
    if to_owner_id is not None and item.item_key == COINS_KEY:
        purse = await _purse(uow, item.world_id, to_owner_id)
        if purse is not None and purse.id != item.id:
            await uow.inventory.remove_item(item.id)
            return await uow.inventory.save_item(
                purse.model_copy(update={"quantity": purse.quantity + item.quantity}),
                purse.version,
            )
    # Held items are with their holder, not lying anywhere.
    update: dict[str, object] = {"owner_id": to_owner_id}
    if to_owner_id is not None:
        update["location_id"] = None
    return await uow.inventory.save_item(item.model_copy(update=update), item.version)


async def _purse(uow: UnitOfWork, world_id: WorldId, owner_id: CharacterId) -> ItemInstance | None:
    held = await uow.inventory.list_for_owner(world_id, owner_id)
    return next((i for i in held if i.item_key == COINS_KEY), None)


async def pay_coins(
    uow: UnitOfWork,
    world_id: WorldId,
    payer_id: CharacterId,
    count: int,
    to_owner_id: CharacterId | None,
) -> int:
    """Take up to ``count`` coins from the payer's purse, to another's purse
    (or spent when nobody takes them); how many changed hands. Without
    audit or commit, like ``move_item``."""
    purse = await _purse(uow, world_id, payer_id)
    if purse is None or count < 1:
        return 0
    paid = min(count, purse.quantity)
    if paid == purse.quantity:
        await uow.inventory.remove_item(purse.id)
    else:
        await uow.inventory.save_item(
            purse.model_copy(update={"quantity": purse.quantity - paid}), purse.version
        )
    if to_owner_id is None or to_owner_id == payer_id:
        return paid
    theirs = await _purse(uow, world_id, to_owner_id)
    if theirs is None:
        await uow.inventory.add_item(
            ItemInstance(
                id=new_item_instance_id(),
                world_id=world_id,
                item_key=COINS_KEY,
                owner_id=to_owner_id,
                quantity=paid,
                name=COINS_NAME,
            )
        )
    else:
        await uow.inventory.save_item(
            theirs.model_copy(update={"quantity": theirs.quantity + paid}), theirs.version
        )
    return paid


async def purse_of(uow: UnitOfWork, world_id: WorldId, owner_id: CharacterId) -> int:
    """How many gold coins someone carries."""
    purse = await _purse(uow, world_id, owner_id)
    return purse.quantity if purse is not None else 0


@dataclass(frozen=True)
class Bought:
    """A purchase made: what was paid, and the good in hand when it is kept."""

    paid: int
    item: ItemInstance | None


async def buy_good(
    uow: UnitOfWork,
    world_id: WorldId,
    buyer_id: CharacterId,
    good: Good,
    paid: int,
    seller_id: CharacterId | None,
) -> Bought | None:
    """Buy ``good`` for ``paid`` coins (at least its price): the coins go to
    the seller (or are spent), and a good one keeps lands in the buyer's
    hands. A purse short of the price changes nothing (None). Without audit
    or commit, like ``pay_coins``."""
    price = max(good.price, paid)
    if await purse_of(uow, world_id, buyer_id) < price:
        return None
    await pay_coins(uow, world_id, buyer_id, price, seller_id)
    if not good.keep:
        return Bought(price, None)
    item = ItemInstance(
        id=new_item_instance_id(),
        world_id=world_id,
        item_key=good.key,
        owner_id=buyer_id,
        name=good.name,
        description=good.description,
    )
    await uow.inventory.add_item(item)
    return Bought(price, item)


async def receive_coins(
    uow: UnitOfWork, world_id: WorldId, owner_id: CharacterId, count: int
) -> None:
    """Add coins to someone's purse (a new one when they carry none)."""
    if count < 1:
        return
    purse = await _purse(uow, world_id, owner_id)
    if purse is None:
        await uow.inventory.add_item(
            ItemInstance(
                id=new_item_instance_id(),
                world_id=world_id,
                item_key=COINS_KEY,
                owner_id=owner_id,
                quantity=count,
                name=COINS_NAME,
            )
        )
        return
    await uow.inventory.save_item(
        purse.model_copy(update={"quantity": purse.quantity + count}), purse.version
    )


async def sell_item(uow: UnitOfWork, item: ItemInstance, price: int) -> None:
    """Sell one of ``item`` for ``price`` coins to its holder's purse: the
    stack loses one (the last one is gone). Without audit or commit."""
    assert item.owner_id is not None
    if item.quantity > 1:
        await uow.inventory.save_item(
            item.model_copy(update={"quantity": item.quantity - 1}), item.version
        )
    else:
        await uow.inventory.remove_item(item.id)
    await receive_coins(uow, item.world_id, item.owner_id, price)
