"""Loot: a successful attempt that reaches for a thing puts it in the actor's pack."""

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

from worldsim.application.graphs.resolve import keep_fair_finds
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def _find(owner: str, name: str = "Coin pouch") -> dict[str, Any]:
    return {
        "effect_type": "item_found",
        "affected_ids": [owner],
        "owner_character_id": owner,
        "name": name,
    }


def test_finds_go_only_to_a_successful_finder_and_only_once() -> None:
    raw = json.dumps(
        {"outcome": "success", "effects": [_find("ash"), _find("wren"), _find("wren", "Key")]}
    )
    kept = json.loads(keep_fair_finds(raw, frozenset({"wren"})))["effects"]
    assert [(e["owner_character_id"], e["name"]) for e in kept] == [("wren", "Coin pouch")]
    failed = json.dumps({"outcome": "failure", "effects": [_find("wren")]})
    assert json.loads(keep_fair_finds(failed, frozenset({"wren"})))["effects"] == []


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_a_successful_snatch_puts_the_pouch_in_your_pack(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())
    wren = str(ids["wren"])
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You resolve one scene" in (request.system or "") and "tries to grab" in request.prompt:
            return json.dumps(
                {
                    "outcome": "success",
                    "rationale": "Wren is quicker than the dog.",
                    "effects": [{**_find(wren, "Knotted coin pouch"), "description": "Heavy."}],
                }
            )
        return base(request)

    gateway.route = route
    attempt: dict[str, Any] = {
        wren: {
            "family": "interact",
            "character_id": wren,
            "snapshot_id": str(uuid.UUID(int=0)),
            "attempt": "grab the coin pouch from the dog",
        }
    }
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    response = _advance(client, ids["world"], 1, attempt, headers=player)
    assert response.status_code == 200, response.text

    pack = client.get(
        "/api/v1/stage2/items",
        params={"world_id": str(ids["world"]), "owner_id": wren},
        headers=player,
    ).json()["members"]
    assert [(i["name"], i["description"]) for i in pack] == [("Knotted coin pouch", "Heavy.")]


def test_the_resolver_knows_who_and_what_is_at_hand(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())  # Wren at the Hearth, Ash at the Market
    wren = str(ids["wren"])
    base = _route_for(ids, {})
    prompts: list[str] = []

    def route(request: CompletionRequest) -> str | None:
        if "You resolve one scene" in (request.system or ""):
            prompts.append(request.prompt)
        return base(request)

    gateway.route = route
    attempt: dict[str, Any] = {
        wren: {
            "family": "interact",
            "character_id": wren,
            "snapshot_id": str(uuid.UUID(int=0)),
            "attempt": "search the hearth for the lost crate",
        }
    }
    player = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    assert _advance(client, ids["world"], 1, attempt, headers=player).status_code == 200
    mine = next(p for p in prompts if "search the hearth" in p)
    assert "Around them:" in mine
    assert "At Hearth: Wren" in mine  # who is at hand
    assert "lying here" in mine and "carried here" in mine  # and what is


def test_a_thing_already_carried_is_not_found_again() -> None:
    raw = json.dumps({"outcome": "success", "effects": [_find("wren", "Worn Leather Purse")]})
    kept = json.loads(
        keep_fair_finds(raw, frozenset({"wren"}), {"wren": frozenset({"worn leather purse"})})
    )["effects"]
    assert kept == []
