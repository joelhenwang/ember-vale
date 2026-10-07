"""The director can add the places its openings send characters to."""

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

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.director import DirectorDecision, DirectorProposal, validate_proposal
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

HEARTH, PLACE, NPC, ITEM = (uuid.uuid4() for _ in range(4))


def _decide(extra: dict[str, Any], places_left: int = 3) -> DirectorDecision:
    proposal = DirectorProposal.model_validate(
        {"action": "propose_hook", "title": "The old forge", "purpose": "Find the smith.", **extra}
    )
    return validate_proposal(
        proposal,
        uuid.uuid4(),
        frozenset(),
        0,
        0,
        uuid.uuid4(),
        uuid.uuid4(),
        known_location_ids=frozenset({HEARTH}),
        spawns_left=3,
        npc_id=NPC,
        item_id=ITEM,
        place_id=PLACE,
        places_left=places_left,
        known_place_names=frozenset({"hearth", "market"}),
    )


def test_new_place_with_its_smith_and_a_key_there() -> None:
    decision = _decide(
        {
            "place": {"name": "Old Forge", "connect_to": str(HEARTH), "travel_phases": 2},
            "npc": {"name": "Hob", "description": "A tired smith."},
            "item": {"name": "Forge key"},
        }
    )
    assert decision.accepted, decision.reason
    assert decision.place is not None and decision.place.id == PLACE
    assert decision.npc is not None and decision.npc.location_id == PLACE
    assert decision.item is not None and decision.item.location_id == PLACE
    assert decision.hook is not None
    assert {"new_location", "spawn_npc", "place_item"} <= set(decision.hook.requested_powers)


@pytest.mark.parametrize(
    ("extra", "left", "reason"),
    [
        ({"place": {"name": "Cave", "connect_to": str(uuid.uuid4())}}, 3, "connect to a known"),
        ({"place": {"name": "market", "connect_to": str(HEARTH)}}, 3, "already exists"),
        ({"place": {"name": "Cave", "connect_to": str(HEARTH)}}, 0, "no new places left"),
        ({"requested_powers": ["new_location"]}, 3, "needs a place"),
        ({"npc": {"name": "Hob"}}, 3, "not a known location"),  # no place to default to
    ],
)
def test_place_rejections(extra: dict[str, Any], left: int, reason: str) -> None:
    decision = _decide(extra, places_left=left)
    assert not decision.accepted and reason in decision.reason


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


async def _pending_jobs(world_id: Any) -> list[Any]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            return await uow.assets.list_pending_jobs(50, world_id)
    finally:
        await engine.dispose()


def test_added_place_is_on_the_map_and_reachable(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())  # Wren at the Hearth, Ash at the Market
    base = _route_for(ids, {})
    watcher = {"X-Worldsim-Role": "watcher"}

    def route(request: CompletionRequest) -> str | None:
        if "You direct" in (request.system or ""):
            return json.dumps(
                {
                    "action": "propose_hook",
                    "title": "Smoke from the old forge",
                    "purpose": "Hob the smith needs help relighting the forge.",
                    "place": {"name": "Old Forge", "connect_to": str(ids["hearth"])},
                    "npc": {"name": "Hob", "description": "A tired smith."},
                }
            )
        if "<<untrusted:identity>>Hob" in request.prompt:
            return json.dumps({"family": "wait"})  # Hob acts from beat 2
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200

    places = {
        p["name"]: p
        for p in client.get(
            "/api/v1/stage2/map", params={"world_id": str(ids["world"])}, headers=watcher
        ).json()["places"]
    }
    forge = places["Old Forge"]
    assert "Hob" in forge["occupants"]
    # The new place and the new person each get an image queued.
    jobs = asyncio.run(_pending_jobs(ids["world"]))
    assert {(job.kind.value, str(job.subject_id)) for job in jobs} >= {("background", forge["id"])}
    assert sum(job.kind.value == "portrait" for job in jobs) == 1
    assert {r["to_location_id"] for r in forge["routes"]} == {str(ids["hearth"])}
    assert forge["id"] in {r["to_location_id"] for r in places["Hearth"]["routes"]}

    anchors = client.get(
        "/api/v1/world/presentation", params={"world_id": str(ids["world"])}, headers=watcher
    ).json()["manifest"]["anchors"]
    assert forge["id"] in {a["location_id"] for a in anchors}

    # Players hear the opening as word around the vale.
    heard = client.get(
        "/api/v1/world/presentation",
        params={"world_id": str(ids["world"])},
        headers={"X-Worldsim-Role": "player", "X-Worldsim-Character": str(ids["wren"])},
    ).json()["rumours"]
    assert [r["title"] for r in heard] == ["Smoke from the old forge"]

    before = len(gateway.sent_requests)
    assert _advance(client, ids["world"], 2).status_code == 200
    wren = next(
        r.prompt
        for r in gateway.sent_requests[before:]
        if "You decide" in (r.system or "") and "<<untrusted:identity>>Wren" in r.prompt
    )
    assert f"Old Forge (location_id {forge['id']}" in wren
