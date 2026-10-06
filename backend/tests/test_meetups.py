"""Characters heading for each other meet instead of swapping places."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for, _seed_two

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.commands import MoveAction, ObserveAction, WaitAction
from worldsim.domain.ids import new_card_id, new_character_id, new_location_id, new_world_id
from worldsim.domain.rules.meetups import resolve_meetups
from worldsim.domain.rules.routes import with_route
from worldsim.domain.scenes import Intent
from worldsim.domain.world import Location, Route, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

SNAP = uuid.uuid4()
HEARTH, MARKET, MILL = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _ids(*names: str) -> dict[str, uuid.UUID]:
    # Sorted uuids so "which id sorts first" is predictable in tests.
    made = sorted((uuid.uuid4() for _ in names), key=lambda u: u.hex)
    return dict(zip(names, made, strict=True))


def _move(actor: uuid.UUID, to: uuid.UUID, key: str = "character:t") -> Intent:
    return Intent(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        snapshot_id=SNAP,
        phase_run_id=uuid.uuid4(),
        author_character_id=actor,
        action=MoveAction(character_id=actor, snapshot_id=SNAP, destination_location_id=to),
        idempotency_key=key,
    )


def _families(intents: list[Intent]) -> list[str]:
    return [i.action.family.value for i in intents]


def test_crossing_moves_become_a_meeting() -> None:
    ids = _ids("ash", "wren")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET}
    names = {ids["ash"]: "Ash", ids["wren"]: "Wren"}
    out = resolve_meetups([_move(ids["ash"], MARKET), _move(ids["wren"], HEARTH)], where, names)
    assert _families(out) == ["observe", "move"]  # Ash (first id) stays
    stay = out[0].action
    assert isinstance(stay, ObserveAction) and stay.focus == "watching for Wren to arrive"
    assert out[0].author_character_id == ids["ash"]


def test_a_player_always_travels() -> None:
    ids = _ids("ash", "wren")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET}
    out = resolve_meetups(
        [_move(ids["ash"], MARKET, key="player:t"), _move(ids["wren"], HEARTH)], where, {}
    )
    assert _families(out) == ["move", "observe"]  # the AI character waits


def test_two_players_or_directed_moves_are_left_alone() -> None:
    ids = _ids("ash", "wren")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET}
    intents = [_move(ids["ash"], MARKET, key="player:a"), _move(ids["wren"], HEARTH, "direct:b")]
    assert resolve_meetups(intents, where, {}) == intents


def test_one_way_and_unrelated_moves_are_untouched() -> None:
    ids = _ids("ash", "wren", "tam")
    where = {ids["ash"]: HEARTH, ids["wren"]: MARKET, ids["tam"]: MILL}
    intents = [
        _move(ids["ash"], MARKET),  # toward Wren, but Wren goes to the mill
        _move(ids["wren"], MILL),
        Intent(
            id=uuid.uuid4(),
            world_id=uuid.uuid4(),
            snapshot_id=SNAP,
            phase_run_id=uuid.uuid4(),
            author_character_id=ids["tam"],
            action=WaitAction(character_id=ids["tam"], snapshot_id=SNAP),
            idempotency_key="character:t",
        ),
    ]
    assert resolve_meetups(intents, where, {}) == intents


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_beat_with_crossing_decisions_files_one_wait_and_watch(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())  # Wren at the Hearth, Ash at the Market
    places = {
        p["name"]: p["id"]
        for p in client.get(
            "/api/v1/stage2/map",
            params={"world_id": str(ids["world"])},
            headers={"X-Worldsim-Role": "watcher"},
        ).json()["places"]
    }
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You decide" in (request.system or ""):
            wren = "<<untrusted:identity>>Wren" in request.prompt
            to = places["Market"] if wren else places["Hearth"]
            return json.dumps({"family": "move", "destination_location_id": to})
        return base(request)

    gateway.route = route
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text

    watcher = {"X-Worldsim-Role": "watcher"}
    scenes = client.get(
        "/api/v1/stage1/scenes", params={"phase_run_id": report.json()["run_id"]}, headers=watcher
    ).json()
    families: list[Any] = []
    for scene in scenes:
        detail = client.get(f"/api/v1/stage1/scenes/{scene['id']}", headers=watcher).json()
        families += [(i["detail"]["family"], i["detail"].get("focus")) for i in detail["intents"]]
    assert sorted(f for f, _ in families) == ["move", "observe"]
    assert any(focus and focus.startswith("watching for") for _, focus in families)


def test_with_route_fills_the_shortest_route_only_for_routeless_moves() -> None:
    world = uuid.uuid4()
    fast, slow = uuid.uuid4(), uuid.uuid4()
    hearth = Location(
        id=HEARTH,
        world_id=world,
        name="Hearth",
        routes=[
            Route(id=slow, destination_location_id=MARKET, duration_phases=2, stamina_cost=5),
            Route(id=fast, destination_location_id=MARKET, duration_phases=1, stamina_cost=8),
        ],
    )
    places = {HEARTH: hearth}
    actor = uuid.uuid4()
    routeless = MoveAction(character_id=actor, snapshot_id=SNAP, destination_location_id=MARKET)
    filled = with_route(routeless, HEARTH, places)
    assert isinstance(filled, MoveAction) and filled.route_id == fast
    chosen = routeless.model_copy(update={"route_id": slow})
    assert with_route(chosen, HEARTH, places) == chosen
    nowhere = MoveAction(character_id=actor, snapshot_id=SNAP, destination_location_id=MILL)
    assert with_route(nowhere, HEARTH, places) == nowhere
    wait = WaitAction(character_id=actor, snapshot_id=SNAP)
    assert with_route(wait, HEARTH, places) == wait


async def _seed_connected() -> dict[str, uuid.UUID]:
    """Two places joined both ways; Wren at the Hearth, Ash at the Market."""
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
                                duration_phases=1,
                                stamina_cost=5,
                            )
                        ],
                    )
                )
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
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


def test_a_decided_move_actually_moves_and_crossers_meet(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You decide" in (request.system or ""):
            wren = "<<untrusted:identity>>Wren" in request.prompt
            to = ids["market"] if wren else ids["hearth"]
            return json.dumps({"family": "move", "destination_location_id": str(to)})
        if "You resolve" in (request.system or ""):
            return json.dumps({"outcome": "success", "effects": [], "rationale": "ok"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    occupants = {
        p["name"]: set(p.get("occupants", []))
        for p in client.get(
            "/api/v1/stage2/map",
            params={"world_id": str(ids["world"])},
            headers={"X-Worldsim-Role": "watcher"},
        ).json()["places"]
    }
    # Ash (or Wren) waits; the other travels: both end up in one place.
    assert {"Wren", "Ash"} in occupants.values()


def test_a_meeting_scene_is_set_where_it_ends() -> None:
    from worldsim.application.orchestration.stage1 import scene_place_facts

    met = dict(scene_place_facts("Hearth", {"Wren": "Market", "Ash": "Market"}))
    assert met["place"] == "The scene begins at Hearth and ends at Market, where everyone in it is."
    assert met["whereabouts"] == "By the end of the scene: Ash at Market; Wren at Market."
    apart = dict(scene_place_facts("Hearth", {"Wren": "Hearth", "Ash": "Market"}))
    assert apart["place"] == "The scene takes place at Hearth."
    assert "Ash at Market" in apart["whereabouts"]
    alone = dict(scene_place_facts("Hearth", {"Wren": "Hearth"}))
    assert alone == {"place": "The scene takes place at Hearth."}
