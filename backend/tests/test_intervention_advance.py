"""Intervention execution through the normal advance endpoint (E6 acceptance).

Submit "Send Wren to Market", see it queued, advance through
POST /stage1/advance, observe the activity and the eventual arrival,
then reload/restart and verify persistent results with no duplicate
effects on beat retry. The director gateway is scripted
deterministically (names from the prompt context); every other role
gets the dev stand-in text, exactly like the local stack.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.world import Location, World
from worldsim.domain.activities import TravelRoute
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_location_id,
    new_route_id,
    new_world_id,
)
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE, STAGE0_DEFAULT_BEAT
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

DIRECTOR_SYSTEM = "game-master instruction"


def _directed_route(request: Any) -> str:
    """Name-resolving director: Wren/Market from the prompt context.

    Every other prompt gets the dev stand-in text, exactly like the
    local stack, so beats commit deterministically.
    """
    if DIRECTOR_SYSTEM not in (request.system or ""):
        return STAGE0_DEFAULT_BEAT
    try:
        asked = json.loads(request.prompt)
    except Exception:
        return None
    context = asked.get("context", {})
    characters = {c["name"]: c for c in context.get("characters", [])}
    locations = {loc["name"]: loc for loc in context.get("locations", [])}
    text = asked.get("text", "")
    if "Wren" in text and "Market" in text and "Wren" in characters and "Market" in locations:
        return json.dumps(
            {
                "schema_version": 1,
                "steps": [
                    {
                        "kind": "direct_activity",
                        "explanation": "Wren walks to the Market.",
                        "character_id": characters["Wren"]["id"],
                        "activity": "travel",
                        "to_location_id": locations["Market"]["id"],
                    }
                ],
                "clarification": "",
            }
        )
    return json.dumps(
        {"schema_version": 1, "steps": [], "clarification": "Say who should go where."}
    )


@pytest.fixture
def directed_app(migrated_db: None) -> Iterator[tuple[TestClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = _directed_route
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield raw, gateway


async def _seed_market_world() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            hearth = new_location_id()
            market = new_location_id()
            wren = new_character_id()
            ash = new_character_id()
            await uow.worlds.add(World(id=wid, name="Vale", seed_version="e6-advance"))
            await uow.versions.ensure(wid, wid, "world")
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth", capacity=4))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market", capacity=4))
            await uow.versions.ensure(hearth, wid, "location")
            await uow.versions.ensure(market, wid, "location")
            for src, dst in ((hearth, market), (market, hearth)):
                await uow.routes.add(
                    TravelRoute(
                        id=new_route_id(),
                        world_id=wid,
                        from_location_id=src,
                        to_location_id=dst,
                        duration_phases=1,
                        stamina_cost=0,
                    )
                )
            for cid, name in ((wren, "Wren"), (ash, "Ash")):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(
                        id=new_card_id(),
                        character_id=cid,
                        name=name,
                        appearance="",
                        personality="",
                        background="",
                        version=1,
                    )
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=hearth,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.commit()
            return {"world": wid, "hearth": hearth, "market": market, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def _deity() -> dict[str, str]:
    return {"X-Worldsim-Role": "deity"}


def _wren_place(client: TestClient, world: UUID) -> str | None:
    body = client.get(f"/api/v1/stage2/map?world_id={world}", headers=_deity()).json()
    for place in body.get("places", []):
        if "Wren" in (place.get("occupants") or []):
            return place.get("name")
    return None


def test_travel_direction_executes_and_arrives(
    directed_app: tuple[TestClient, FakeGateway],
) -> None:
    import asyncio

    client, _gateway = directed_app
    ids = asyncio.run(_seed_market_world())
    world = ids["world"]

    filed = client.post(
        "/api/v1/interventions",
        headers=_deity(),
        json={
            "world_id": str(world),
            "client_request_id": "e6-http-travel-1",
            "text": "Send Wren to Market",
            "mode": "force",
        },
    )
    assert filed.status_code == 200, filed.text
    item = filed.json()
    assert item["status"] == "queued"
    assert len(item["steps"]) == 1
    intervention_id = item["id"]

    first = client.post(
        "/api/v1/stage1/advance",
        headers=_deity(),
        json={"world_id": str(world), "absolute_index": 1},
    )
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False

    reread = client.get(f"/api/v1/interventions/{intervention_id}", headers=_deity()).json()
    assert reread["status"] == "completed"
    assert reread["steps"][0]["status"] == "completed"
    assert reread["steps"][0]["result_activity_id"]

    activities = client.get(f"/api/v1/stage2/activities?world_id={world}", headers=_deity()).json()
    travel = [a for a in activities.get("members", []) if a.get("character_id") == str(ids["wren"])]
    assert len(travel) == 1
    assert travel[0]["to_location_id"] == str(ids["market"])

    # The journey completes on a later beat: starting travel and arriving
    # stay distinguishable.
    second = client.post(
        "/api/v1/stage1/advance",
        headers=_deity(),
        json={"world_id": str(world), "absolute_index": 2},
    )
    assert second.status_code == 200, second.text
    assert _wren_place(client, world) == "Market"

    # Retrying the same beat replays without duplicating effects: the
    # duplicate path returns before the drain, so the recorded outcome
    # is untouched. The journey activity is done after arrival.
    before = client.get(f"/api/v1/interventions/{intervention_id}", headers=_deity()).json()
    replay = client.post(
        "/api/v1/stage1/advance",
        headers=_deity(),
        json={"world_id": str(world), "absolute_index": 1},
    )
    assert replay.json()["duplicate"] is True
    after = client.get(f"/api/v1/interventions/{intervention_id}", headers=_deity()).json()
    assert after["status"] == "completed"
    assert after["version"] == before["version"]
    assert after["steps"][0]["status"] == "completed"
    again = client.get(f"/api/v1/stage2/activities?world_id={world}", headers=_deity()).json()
    mine = [a for a in again.get("members", []) if a.get("character_id") == str(ids["wren"])]
    assert mine == []

    # Fresh reads after everything: persistent rows, no second intervention.
    listed = client.get(f"/api/v1/interventions?world_id={world}", headers=_deity()).json()
    assert listed == []
    assert _wren_place(client, world) == "Market"


def test_cancelled_direction_never_applies(
    directed_app: tuple[TestClient, FakeGateway],
) -> None:
    import asyncio

    client, _gateway = directed_app
    ids = asyncio.run(_seed_market_world())
    world = ids["world"]

    filed = client.post(
        "/api/v1/interventions",
        headers=_deity(),
        json={
            "world_id": str(world),
            "client_request_id": "e6-http-cancel-1",
            "text": "Send Wren to Market",
            "mode": "force",
        },
    )
    assert filed.json()["status"] == "queued"
    intervention_id = filed.json()["id"]
    cancelled = client.post(
        f"/api/v1/interventions/{intervention_id}/cancel",
        headers=_deity(),
        json={"expected_version": 0},
    )
    assert cancelled.json()["status"] == "cancelled"

    advanced = client.post(
        "/api/v1/stage1/advance",
        headers=_deity(),
        json={"world_id": str(world), "absolute_index": 1},
    )
    assert advanced.status_code == 200, advanced.text
    activities = client.get(f"/api/v1/stage2/activities?world_id={world}", headers=_deity()).json()
    assert activities.get("members", []) == []
    assert _wren_place(client, world) == "Hearth"


def test_player_cannot_direct_others(
    directed_app: tuple[TestClient, FakeGateway],
) -> None:
    import asyncio

    client, _gateway = directed_app
    ids = asyncio.run(_seed_market_world())

    denied = client.post(
        "/api/v1/interventions",
        headers={"X-Worldsim-Role": "player"},
        json={
            "world_id": str(ids["world"]),
            "client_request_id": "e6-http-deny-1",
            "text": "Send Ash to Market",
            "mode": "attempt",
            "scope": {"kind": "character", "character_ids": [str(ids["ash"])]},
        },
    )
    assert denied.status_code == 403
