"""Items lie in places, can be picked up and handed over, and openings can place them."""

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

from worldsim.application.graphs.character import precheck_action
from worldsim.application.orchestration.stage1 import item_line
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.commands import TakeAction, TransferAction
from worldsim.domain.director import DirectorProposal, validate_proposal
from worldsim.domain.progress import ItemInstance
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

SNAP = uuid.uuid4()


def test_item_line_names_catalog_and_one_off_items() -> None:
    world = uuid.uuid4()
    rope = ItemInstance(id=uuid.uuid4(), world_id=world, item_key="rope")
    locket = ItemInstance(
        id=uuid.uuid4(),
        world_id=world,
        item_key="found_object",
        name="Silver locket",
        description="Engraved with an R.",
    )
    assert item_line(locket) == f"Silver locket — Engraved with an R. (item_id {locket.id})"
    assert item_line(rope).startswith("Rope")  # catalog name
    assert f"(item_id {rope.id})" in item_line(rope)


def test_precheck_rejects_items_the_character_cannot_reach() -> None:
    me, other, item = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    take = TakeAction(character_id=me, snapshot_id=SNAP, item_instance_id=item)
    give = TransferAction(
        character_id=me, snapshot_id=SNAP, item_instance_id=item, target_character_id=other
    )
    known = frozenset({str(other)})
    nowhere: frozenset[str] = frozenset()
    assert "no such item here" in str(
        precheck_action(
            take, known_character_ids=known, location_ids=nowhere, item_ids_here=nowhere
        )
    )
    assert (
        precheck_action(
            take,
            known_character_ids=known,
            location_ids=nowhere,
            item_ids_here=frozenset({str(item)}),
        )
        is None
    )
    assert "not carrying" in str(
        precheck_action(
            give, known_character_ids=known, location_ids=nowhere, carried_item_ids=nowhere
        )
    )


def test_director_can_place_an_item_at_a_known_place() -> None:
    market, hook, arc, item = (uuid.uuid4() for _ in range(4))
    proposal = DirectorProposal.model_validate(
        {
            "action": "propose_hook",
            "title": "A dropped locket",
            "purpose": "Someone lost it.",
            "item": {
                "name": "Silver locket",
                "description": "Engraved.",
                "location_id": str(market),
            },
        }
    )
    common: dict[str, Any] = {"known_location_ids": frozenset({market}), "item_id": item}
    decision = validate_proposal(proposal, uuid.uuid4(), frozenset(), 0, 0, hook, arc, **common)
    assert decision.accepted and decision.item is not None
    assert decision.item.id == item and "place_item" in decision.hook.requested_powers  # type: ignore[union-attr]
    elsewhere = proposal.model_copy(
        update={"item": proposal.item.model_copy(update={"location_id": uuid.uuid4()})}  # type: ignore[union-attr]
    )
    rejected = validate_proposal(elsewhere, uuid.uuid4(), frozenset(), 0, 0, hook, arc, **common)
    assert not rejected.accepted and "not a known location" in rejected.reason


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


async def _drop_item(world: uuid.UUID, place: uuid.UUID) -> uuid.UUID:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            item = ItemInstance(
                id=uuid.uuid4(),
                world_id=world,
                item_key="found_object",
                location_id=place,
                name="Silver locket",
                description="Engraved with an R.",
            )
            await uow.inventory.add_item(item)
            await uow.commit()
            return item.id
    finally:
        await engine.dispose()


async def _item(item_id: uuid.UUID) -> ItemInstance:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return await uow.inventory.get_item(item_id)
    finally:
        await engine.dispose()


def test_a_character_sees_and_picks_up_what_lies_here(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())  # Wren at the Hearth, Ash at the Market
    locket = asyncio.run(_drop_item(ids["world"], ids["hearth"]))
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        system = request.system or ""
        if "You decide" in system and "<<untrusted:identity>>Wren" in request.prompt:
            if "Silver locket" in request.prompt and "carrying nothing" in request.prompt:
                return json.dumps({"family": "take", "item_instance_id": str(locket)})
            return json.dumps({"family": "wait"})
        if "You decide" in system:
            return json.dumps({"family": "wait"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    taken = asyncio.run(_item(locket))
    assert taken.owner_id == ids["wren"] and taken.location_id is None

    before = len(gateway.sent_requests)
    assert _advance(client, ids["world"], 2).status_code == 200
    wren = next(
        r.prompt
        for r in gateway.sent_requests[before:]
        if "You decide" in (r.system or "") and "<<untrusted:identity>>Wren" in r.prompt
    )
    assert f"carrying Silver locket — Engraved with an R. (item_id {locket})" in wren
    assert "Things lying here" not in wren
    assert "Wren picks up Silver locket" in wren  # remembered with the item's name


def test_an_invented_item_falls_back_to_waiting(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You decide" in (request.system or ""):
            return json.dumps({"family": "take", "item_instance_id": str(uuid.uuid4())})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200  # no crash, no settle
