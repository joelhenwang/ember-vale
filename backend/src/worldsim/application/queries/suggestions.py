"""Validated action suggestions for one character (owned by REVAMP-P08).

Suggestions are computed from live rules state, never hardcoded:
destinations come from travel legs, targets from co-location, and
each entry carries the IDs the attempt needs. Empty states are honest.
"""

from __future__ import annotations

from uuid import UUID

from worldsim.application.orchestration.stage1 import item_description, item_label
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.enums import LifeStatus
from worldsim.domain.party import party_name_key
from worldsim.interfaces.http import schemas as api


async def suggestions_for(uow: UnitOfWork, character_id: UUID) -> list[api.SuggestionView]:
    """Build the contextual suggestion list for one character."""
    character = await uow.characters.get(character_id)
    if character.life_status != LifeStatus.ALIVE:
        return []
    world_id = character.world_id
    others = [
        c
        for c in await uow.characters.list_for_world(world_id)
        if c.id != character_id
        and c.life_status == LifeStatus.ALIVE
        and c.location_id == character.location_id
    ]
    legs = await uow.routes.list_for_world(world_id)
    destinations = [leg for leg in legs if leg.from_location_id == character.location_id]
    locations = {loc.id: loc for loc in await uow.locations.list_for_world(world_id)}
    suggestions = [
        api.SuggestionView(
            id="rest",
            family="rest",
            title="Rest",
            subtitle="Recover stamina and mana.",
        ),
        api.SuggestionView(
            id="observe",
            family="observe",
            title="Look around",
            subtitle="Notice what is happening here.",
        ),
    ]
    for leg in destinations:
        place = locations.get(leg.to_location_id)
        suggestions.append(
            api.SuggestionView(
                id=f"move:{leg.to_location_id.hex}",
                family="move",
                title=f"Go to {place.name if place else 'the road'}",
                subtitle=f"{leg.duration_phases} phase(s) on the road.",
                destination_location_id=leg.to_location_id,
            )
        )
    # A bout needs both fighters seated with sheets (the party roster); offering
    # it without them only fails the turn.
    seated = {member.name_key for member in await uow.party.list_for_world(world_id)}
    can_spar = party_name_key(character.name) in seated
    for other in others:
        suggestions.append(
            api.SuggestionView(
                id=f"talk:{other.id.hex}",
                family="communicate",
                title=f"Talk to {other.name}",
                subtitle="Say something in person.",
                target_character_id=other.id,
                needs_topic=True,
            )
        )
        if can_spar and party_name_key(other.name) in seated:
            suggestions.append(
                api.SuggestionView(
                    id=f"spar:{other.id.hex}",
                    family="spar",
                    title=f"Spar with {other.name}",
                    subtitle="A practice bout, not a real fight.",
                    target_character_id=other.id,
                )
            )
    for item in await uow.inventory.list_at_location(world_id, character.location_id):
        if item.owner_id is not None:
            continue
        suggestions.append(
            api.SuggestionView(
                id=f"take:{item.id.hex}",
                family="take",
                title=f"Pick up the {item_label(item)}",
                subtitle=item_description(item)[:120],
                item_instance_id=item.id,
            )
        )
    suggestions.append(
        api.SuggestionView(
            id="appeal",
            family="appeal",
            title="Make a case",
            subtitle="Argue for something you believe.",
            needs_topic=True,
        )
    )
    return suggestions
