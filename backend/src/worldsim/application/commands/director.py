"""Director acceptance shared by graph and user paths (owned by S2-ROLE-001)."""

from __future__ import annotations

from uuid import uuid4, uuid5

from worldsim.application.images import queue_image, world_style_pack
from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import AssetKind
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.director import (
    ADDED_PLACES_CONFIG_KEY,
    SPAWNED_CONFIG_KEY,
    AddedPlace,
    DirectorDecision,
    SpawnedNpc,
)
from worldsim.domain.ids import WorldId, new_card_id
from worldsim.domain.progress import ItemInstance
from worldsim.domain.world import Location, Route

#: Catalog key for one-off items a director opening places (named per instance).
PLACED_ITEM_KEY = "found_object"


async def accept_decision(
    uow: UnitOfWork,
    world_id: WorldId,
    decision: DirectorDecision,
    actor_role: str,
    key: str,
    last_absolute: int,
) -> None:
    """Persist accepted rows, audit the command, and advance the cooldown."""
    await uow.worlds.put_config(world_id, "director.last_absolute", last_absolute)
    if decision.accepted:
        style_pack = await world_style_pack(uow, world_id)
        if decision.place is not None:
            await _add_place(uow, world_id, decision.place)
            await queue_image(uow, world_id, AssetKind.BACKGROUND, decision.place.id, style_pack)
        if decision.npc is not None:
            await _spawn(uow, world_id, decision.npc)
            await queue_image(uow, world_id, AssetKind.PORTRAIT, decision.npc.id, style_pack)
        if decision.item is not None:
            await uow.inventory.add_item(
                ItemInstance(
                    id=decision.item.id,
                    world_id=world_id,
                    item_key=PLACED_ITEM_KEY,
                    location_id=decision.item.location_id,
                    name=decision.item.name,
                    description=decision.item.description or None,
                )
            )
        if decision.hook is not None:
            await uow.narrative.add_hook(
                decision.hook.model_copy(update={"created_phase_index": last_absolute})
            )
        if decision.arc is not None:
            await uow.narrative.add_arc(
                decision.arc.model_copy(update={"created_phase_index": last_absolute})
            )
        payload: dict[str, object] = {
            "hook_id": str(decision.hook.id) if decision.hook else None,
            "arc_id": str(decision.arc.id) if decision.arc else None,
            "npc_id": str(decision.npc.id) if decision.npc else None,
            "item_id": str(decision.item.id) if decision.item else None,
            "place_id": str(decision.place.id) if decision.place else None,
        }
        await uow.commands.add(
            command_id=uuid4(),
            world_id=world_id,
            key=key,
            actor_role=actor_role,
            command_type="director_proposal",
            expected_versions={},
            payload=payload,
            input_hash=canonical_input_hash({"key": key, "payload": payload}),
        )
    await uow.commit()


#: Stamina a route to a director-added place costs per phase of travel.
ROUTE_STAMINA_PER_PHASE = 5


async def _add_place(uow: UnitOfWork, world_id: WorldId, place: AddedPlace) -> None:
    """Create the opening's new place, joined both ways to the place it connects to."""
    origin = await uow.locations.get(place.connect_to)
    cost = ROUTE_STAMINA_PER_PHASE * place.travel_phases
    await uow.locations.add(
        Location(
            id=place.id,
            world_id=world_id,
            name=place.name.strip(),
            region=origin.region,
            routes=[
                Route(
                    id=uuid5(place.id, "route-back"),
                    destination_location_id=origin.id,
                    duration_phases=place.travel_phases,
                    stamina_cost=cost,
                )
            ],
            discovered=True,
        )
    )
    await uow.locations.save(
        origin.model_copy(
            update={
                "routes": [
                    *origin.routes,
                    Route(
                        id=uuid5(place.id, "route-there"),
                        destination_location_id=place.id,
                        duration_phases=place.travel_phases,
                        stamina_cost=cost,
                    ),
                ]
            }
        ),
        origin.version,
    )
    config = await uow.worlds.get_config(world_id)
    added = config.get(ADDED_PLACES_CONFIG_KEY)
    count = added if isinstance(added, int) else 0
    await uow.worlds.put_config(world_id, ADDED_PLACES_CONFIG_KEY, count + 1)


async def _spawn(uow: UnitOfWork, world_id: WorldId, npc: SpawnedNpc) -> None:
    """Create the opening's new character, ready to act from the next beat."""
    await uow.characters.add_identity(npc.id, world_id, npc.name)
    await uow.characters.add_card(
        CharacterCard(
            id=new_card_id(),
            character_id=npc.id,
            name=npc.name,
            personality=npc.description,
            pronouns=npc.pronouns,
            version=1,
        )
    )
    await uow.characters.add_state(
        Character(
            id=npc.id,
            world_id=world_id,
            name=npc.name,
            card_version=1,
            location_id=npc.location_id,
            stamina=80,
            mana=40,
        )
    )
    await uow.versions.ensure(npc.id, world_id, "character")
    config = await uow.worlds.get_config(world_id)
    spawned = config.get(SPAWNED_CONFIG_KEY)
    count = spawned if isinstance(spawned, int) else 0
    await uow.worlds.put_config(world_id, SPAWNED_CONFIG_KEY, count + 1)
