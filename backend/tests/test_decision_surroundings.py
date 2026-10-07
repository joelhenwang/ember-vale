"""Decision context lists what a character can act on where they stand."""

from __future__ import annotations

import uuid

from worldsim.application.orchestration.stage1 import surroundings_text
from worldsim.domain.characters import Character
from worldsim.domain.enums import LifeStatus
from worldsim.domain.world import Location, Route


def _character(name: str, world: uuid.UUID, place: uuid.UUID, **extra: object) -> Character:
    return Character.model_validate(
        {
            "id": uuid.uuid4(),
            "world_id": world,
            "name": name,
            "card_version": 1,
            "location_id": place,
            "stamina": 80,
            "mana": 50,
            **extra,
        }
    )


def test_surroundings_name_routes_and_present_characters() -> None:
    world, hearth_id, market_id, mill_id = (uuid.uuid4() for _ in range(4))
    hearth = Location(
        id=hearth_id,
        world_id=world,
        name="Hearth",
        region="Ember Vale",
        routes=[
            Route(
                id=uuid.uuid4(),
                destination_location_id=market_id,
                duration_phases=1,
                stamina_cost=5,
            )
        ],
    )
    wren = _character("Wren", world, hearth_id)
    ash = _character("Ash", world, hearth_id)
    miller = _character("Tam", world, mill_id)
    ghost = _character("Old Bren", world, hearth_id, life_status=LifeStatus.DEAD)

    text = surroundings_text(hearth, {market_id: "Market"}, [wren, ash, miller, ghost], wren.id)

    assert f"Market (location_id {market_id}; a journey of 1 phase, costs 5 stamina)" in text
    assert f"Ash (character_id {ash.id})" in text
    assert "Wren" not in text  # never lists the viewer
    assert "Tam" not in text  # elsewhere: not perceived
    assert "Old Bren" not in text  # dead: cannot be addressed


def test_surroundings_say_when_alone_and_without_routes() -> None:
    world, place_id = uuid.uuid4(), uuid.uuid4()
    cell = Location(id=place_id, world_id=world, name="Cell")
    alone = _character("Wren", world, place_id)

    text = surroundings_text(cell, {}, [alone], alone.id)

    assert "From here you can travel to: nowhere." in text
    assert text.startswith("You are at Cell.")
    assert "Present here: no one else." in text
