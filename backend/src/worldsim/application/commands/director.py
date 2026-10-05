"""Director acceptance shared by graph and user paths (owned by S2-ROLE-001)."""

from __future__ import annotations

from uuid import uuid4

from worldsim.application.transactions.canonical import canonical_input_hash
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.director import SPAWNED_CONFIG_KEY, DirectorDecision, SpawnedNpc
from worldsim.domain.ids import WorldId, new_card_id
from worldsim.domain.progress import ItemInstance

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
        if decision.npc is not None:
            await _spawn(uow, world_id, decision.npc)
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


async def _spawn(uow: UnitOfWork, world_id: WorldId, npc: SpawnedNpc) -> None:
    """Create the opening's new character, ready to act from the next beat."""
    await uow.characters.add_identity(npc.id, world_id, npc.name)
    await uow.characters.add_card(
        CharacterCard(
            id=new_card_id(),
            character_id=npc.id,
            name=npc.name,
            personality=npc.description,
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
