"""Characters can say how they are referred to; prompts carry it."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for, _seed_two

from worldsim.application.graphs.narrate import (
    _speaker_roster,  # pyright: ignore[reportPrivateUsage]
)
from worldsim.application.orchestration.stage1 import identity_text, surroundings_text
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.presets import CharacterPresetPayload
from worldsim.domain.world import Location
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def _card(pronouns: str = "") -> CharacterCard:
    return CharacterCard(
        id=uuid.uuid4(),
        character_id=uuid.uuid4(),
        name="Wren",
        personality="Quick.",
        pronouns=pronouns,
        version=1,
    )


def test_identity_names_pronouns_only_when_stated() -> None:
    assert identity_text(_card("she/her")) == "Wren (she/her).  Quick."
    assert identity_text(_card()) == "Wren.  Quick."


def test_others_present_show_their_stated_pronouns() -> None:
    world, place = uuid.uuid4(), uuid.uuid4()
    hearth = Location(id=place, world_id=world, name="Hearth")
    people = [
        Character(
            id=uuid.uuid4(),
            world_id=world,
            name=name,
            card_version=1,
            location_id=place,
            stamina=80,
            mana=40,
        )
        for name in ("Wren", "Ash", "Tam")
    ]
    me, ash, tam = people
    text = surroundings_text(hearth, {}, people, me.id, (), {ash.id: "he/him"})
    assert f"Ash (he/him, character_id {ash.id})" in text
    assert f"Tam (character_id {tam.id})" in text


def test_narrator_roster_carries_pronouns() -> None:
    lines = _speaker_roster(
        [
            {"key": "speech:1", "value": "x", "speaker": "a1", "speaker_name": "Ash",
             "speaker_pronouns": "he/him"},
            {"key": "speech:2", "value": "y", "speaker": "w1", "speaker_name": "Wren"},
        ]
    )  # fmt: skip
    assert "- Ash (he/him, id: a1)" in lines and "- Wren (id: w1)" in lines


def test_presets_accept_pronouns() -> None:
    payload = CharacterPresetPayload.model_validate(
        {"kind": "character", "name": "Wren", "pronouns": "she/her"}
    )
    assert payload.pronouns == "she/her"


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_created_character_pronouns_reach_its_prompt(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    watcher = {"X-Worldsim-Role": "watcher"}
    hearth = next(
        p["id"]
        for p in client.get(
            "/api/v1/stage2/map", params={"world_id": str(ids["world"])}, headers=watcher
        ).json()["places"]
        if p["name"] == "Hearth"
    )
    created = client.post(
        "/api/v1/stage1/characters",
        json={"world_id": str(ids["world"]), "name": "Tam", "location_id": hearth,
              "pronouns": "they/them"},
        headers=watcher,
    )  # fmt: skip
    assert created.status_code == 200, created.text
    tam = created.json()["id"]
    detail = client.get(f"/api/v1/stage1/characters/{tam}", headers=watcher).json()
    assert detail["card"]["pronouns"] == "they/them"

    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "<<untrusted:identity>>Tam" in request.prompt:
            return json.dumps({"family": "wait"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    prompts = [r.prompt for r in gateway.sent_requests if "You decide" in (r.system or "")]
    assert any("<<untrusted:identity>>Tam (they/them)." in p for p in prompts)
    wren = next(p for p in prompts if "<<untrusted:identity>>Wren" in p)
    assert f"Tam (they/them, character_id {tam})" in wren
