"""The director can add the people its openings name."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for, _seed_two

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.director import DirectorProposal, NpcSpec, validate_proposal
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

WORLD, HOOK, ARC, NPC, MARKET, ASH = (uuid.uuid4() for _ in range(6))


def _hook(**extra: object) -> DirectorProposal:
    return DirectorProposal.model_validate(
        {"action": "propose_hook", "title": "Late carts", "purpose": "Ask the carter.", **extra}
    )


def _validate(proposal: DirectorProposal, spawns_left: int = 3) -> object:
    return validate_proposal(
        proposal,
        WORLD,
        frozenset({ASH}),
        0,
        0,
        HOOK,
        ARC,
        known_location_ids=frozenset({MARKET}),
        spawns_left=spawns_left,
        npc_id=NPC,
    )


def test_spawn_is_accepted_with_a_known_place_and_joins_the_hook() -> None:
    npc = NpcSpec(name="Tam the carter", description="Worried about his cart.", location_id=MARKET)
    decision = _validate(_hook(requested_powers=["spawn_npc"], npc=npc.model_dump()))
    assert decision.accepted  # type: ignore[attr-defined]
    assert decision.npc.id == NPC and decision.npc.name == "Tam the carter"  # type: ignore[attr-defined]
    assert decision.hook.participant_ids == []  # type: ignore[attr-defined]  # heard by all
    named = _validate(
        _hook(requested_powers=["spawn_npc"], npc=npc.model_dump(), participant_ids=[str(ASH)])
    )
    assert named.hook.participant_ids == [ASH, NPC]  # type: ignore[attr-defined]


def test_npc_without_the_power_still_counts_as_a_spawn() -> None:
    npc = {"name": "Tam", "location_id": str(MARKET)}
    decision = _validate(_hook(npc=npc))
    assert decision.accepted and "spawn_npc" in decision.hook.requested_powers  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("extra", "left", "reason"),
    [
        ({"requested_powers": ["spawn_npc"]}, 3, "needs an npc"),
        ({"npc": {"name": "Tam", "location_id": str(uuid.uuid4())}}, 3, "not a known location"),
        ({"npc": {"name": "Tam", "location_id": str(MARKET)}}, 0, "no new characters left"),
    ],
)
def test_spawn_rejections(extra: dict[str, object], left: int, reason: str) -> None:
    decision = _validate(_hook(**extra), spawns_left=left)
    assert not decision.accepted and reason in decision.reason  # type: ignore[attr-defined]


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_spawned_character_appears_and_acts_from_the_next_beat(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    watcher = {"X-Worldsim-Role": "watcher"}

    def places() -> dict[str, list[str]]:
        rows = client.get(
            "/api/v1/stage2/map", params={"world_id": str(ids["world"])}, headers=watcher
        ).json()["places"]
        return {p["name"]: p.get("occupants", []) for p in rows}

    market = next(
        p["id"]
        for p in client.get(
            "/api/v1/stage2/map", params={"world_id": str(ids["world"])}, headers=watcher
        ).json()["places"]
        if p["name"] == "Market"
    )
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You direct" in (request.system or ""):
            return json.dumps(
                {
                    "action": "propose_hook",
                    "title": "Late carts",
                    "purpose": "Tam the carter is missing a cart.",
                    "requested_powers": ["spawn_npc"],
                    "npc": {
                        "name": "Tam",
                        "description": "A carter who lost a cart.",
                        "location_id": market,
                    },
                }
            )
        if "You decide" in (request.system or "") and "<<untrusted:identity>>Tam" in request.prompt:
            return json.dumps({"family": "wait"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    assert "Tam" in places()["Market"]
    tam_decisions = [r for r in gateway.sent_requests if "<<untrusted:identity>>Tam" in r.prompt]
    assert tam_decisions == []  # not sealed into beat 1

    assert _advance(client, ids["world"], 2).status_code == 200
    assert any("<<untrusted:identity>>Tam" in r.prompt for r in gateway.sent_requests)
