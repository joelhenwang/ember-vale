"""Roads longer than one phase are journeys: the traveller sets off, pays the
road's stamina, sits out the place they left, and arrives when its phases pass."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for

from worldsim.application.orchestration.stage1 import journey_span, road_note, split_journeys
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.effects import MoveEntityEffect, ResourceAdjustedEffect
from worldsim.domain.enums import ActivityKind, ResourceKind
from worldsim.domain.geography import MAX_ROAD_STAMINA, road_stamina
from worldsim.domain.ids import new_card_id, new_character_id, new_location_id, new_world_id
from worldsim.domain.world import Location, Route, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

WATCHER = {"X-Worldsim-Role": "watcher"}


def test_roads_tire_by_length_and_kind_up_to_a_cap() -> None:
    assert road_stamina(10, "road") == 20
    assert road_stamina(10, "sea") == 10  # aboard ship one mostly sits
    assert road_stamina(4, "pass") == 20
    assert road_stamina(30, "pass") == MAX_ROAD_STAMINA
    assert road_stamina(3, "ferry") == 6  # unknown kinds count as roads


def test_roads_read_their_length_and_cost() -> None:
    there = uuid.uuid4()
    assert journey_span(1) == "1 phase"
    assert journey_span(24) == "about 2 days and 4 phases"
    assert (
        road_note(
            Route(id=uuid.uuid4(), destination_location_id=there, duration_phases=1, stamina_cost=0)
        )
        == ""
    )
    long = Route(
        id=uuid.uuid4(), destination_location_id=there, duration_phases=10, stamina_cost=20
    )
    assert road_note(long) == "; a journey of about 1 day, costs 20 stamina"


def test_only_moves_along_long_roads_become_journeys() -> None:
    here, there, who = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    short = Route(id=uuid.uuid4(), destination_location_id=there, duration_phases=1, stamina_cost=2)
    long = Route(id=uuid.uuid4(), destination_location_id=there, duration_phases=3, stamina_cost=6)

    def move(route: Route) -> MoveEntityEffect:
        return MoveEntityEffect(
            affected_ids=[who],
            expected_versions={str(who): 1},
            from_location_id=here,
            to_location_id=there,
            route_id=route.id,
        )

    paid = ResourceAdjustedEffect(
        affected_ids=[who], expected_versions={str(who): 1}, resource=ResourceKind.STAMINA, delta=-6
    )
    roads = {short.id: short, long.id: long}
    kept, journeys = split_journeys([move(long), paid], roads)
    assert kept == [paid]  # the stamina is paid on setting off
    assert [r for _, r in journeys] == [long]
    kept, journeys = split_journeys([move(short)], roads)
    assert len(kept) == 1 and journeys == []


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


async def _seed_road() -> dict[str, uuid.UUID]:
    """Wren and Tam at the Hearth, Ash at the Market: a 3-phase road away."""
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Roads", seed_version="s1-test"))
            hearth, market = new_location_id(), new_location_id()
            for here, there, name in ((hearth, market, "Hearth"), (market, hearth, "Market")):
                await uow.locations.add(
                    Location(
                        id=here,
                        world_id=wid,
                        name=name,
                        routes=[
                            Route(
                                id=uuid.uuid4(),
                                destination_location_id=there,
                                duration_phases=3,
                                stamina_cost=6,
                            )
                        ],
                    )
                )
            wren, ash, tam = new_character_id(), new_character_id(), new_character_id()
            for cid, name, place in (
                (wren, "Wren", hearth),
                (ash, "Ash", market),
                (tam, "Tam", hearth),
            ):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name, version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=place,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.versions.ensure(wid, wid, "world")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash, "hearth": hearth, "market": market}
    finally:
        await engine.dispose()


async def _state(ids: dict[str, uuid.UUID]) -> tuple[Character, list[ActivityKind]]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wren = await uow.characters.get(ids["wren"])
            active = [
                a.kind
                for a in await uow.activities.list_active_for_world(ids["world"])
                if a.character_id == ids["wren"]
            ]
            return wren, active
    finally:
        await engine.dispose()


def test_a_long_road_is_a_journey(stage1_client: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_road())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        system = request.system or ""
        if "You decide" in system:
            if "<<untrusted:identity>>Wren" in request.prompt:
                return json.dumps({"family": "move", "destination_location_id": str(ids["market"])})
            return json.dumps({"family": "observe", "focus": "the road"})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "ok"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    decisions = [r.prompt for r in gateway.sent_requests if "You decide" in (r.system or "")]
    # Ash and Wren were told how long and how tiring the road is.
    assert any("a journey of 3 phases, costs 6 stamina" in p for p in decisions)
    wren, active = asyncio.run(_state(ids))
    assert wren.location_id == ids["hearth"]  # set off, not arrived
    assert wren.stamina == 74  # paid on setting off
    assert active == [ActivityKind.TRAVEL]
    narrator = [r.prompt for r in gateway.sent_requests if "You narrate" in (r.system or "")]
    setting_off = [p for p in narrator if "Wren sets off on the road to Market" in p]
    assert setting_off and "a journey of 3 phases" in setting_off[0]
    # Ash is at the far end: not met yet, so not in Wren's departure scene.
    assert "Ash" not in setting_off[0]

    # On the road: Wren decides nothing and is not "present" at the Hearth.
    before = len(gateway.sent_requests)
    assert _advance(client, ids["world"], 2).status_code == 200
    asked = [r.prompt for r in gateway.sent_requests[before:] if "You decide" in (r.system or "")]
    assert asked and not any("<<untrusted:identity>>Wren" in p for p in asked)
    assert not any(f"Wren (character_id {ids['wren']})" in p for p in asked)

    assert _advance(client, ids["world"], 3).status_code == 200
    assert asyncio.run(_state(ids))[0].location_id == ids["hearth"]
    trip = next(
        a
        for a in client.get(
            "/api/v1/world/presentation", params={"world_id": str(ids["world"])}, headers=WATCHER
        ).json()["activities"]
        if a["character_id"] == str(ids["wren"])
    )
    assert trip["effective_progress_phases"] >= 2  # the story-watch map walks the road
    assert _advance(client, ids["world"], 4).status_code == 200  # three phases on the road
    wren, active = asyncio.run(_state(ids))
    assert wren.location_id == ids["market"] and active == []
    entries = client.get(
        "/api/v1/world/chronicle", params={"world_id": str(ids["world"])}, headers=WATCHER
    ).json()["entries"]
    assert any(e["title"] == "Wren arrives at Market." for e in entries)
