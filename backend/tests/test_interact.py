"""Physical attempts in plain words, judged by the resolver and remembered."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_meetups import _seed_connected
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for

from worldsim.application.graphs.character import precheck_action
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.characters import Character
from worldsim.domain.commands import InteractAction
from worldsim.domain.errors import DomainError
from worldsim.domain.rules.actions import check_interact
from worldsim.domain.rules.views import WorldView
from worldsim.domain.world import Location, World
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

SNAP = uuid.uuid4()


def _view() -> tuple[WorldView, Character, Character]:
    world = World(id=uuid.uuid4(), name="Vale", seed_version="t")
    here, there = (Location(id=uuid.uuid4(), world_id=world.id, name=n) for n in ("A", "B"))
    me, away = (
        Character(
            id=uuid.uuid4(),
            world_id=world.id,
            name=name,
            card_version=1,
            location_id=place.id,
            stamina=80,
            mana=40,
        )
        for name, place in (("Wren", here), ("Ash", there))
    )
    return WorldView(world=world, characters=[me, away], locations=[here, there]), me, away


def test_attempts_need_a_partner_on_shared_ground() -> None:
    view, me, away = _view()
    alone = InteractAction(character_id=me.id, snapshot_id=SNAP, attempt="heave the wheel free")
    check_interact(me, alone, view)  # no partner: fine
    with_absent = alone.model_copy(update={"target_character_id": away.id})
    with pytest.raises(DomainError, match="elsewhere"):
        check_interact(me, with_absent, view)


def test_precheck_rejects_unknown_partners_and_unreachable_items() -> None:
    me, item = uuid.uuid4(), uuid.uuid4()
    attempt = InteractAction(character_id=me, snapshot_id=SNAP, attempt="search the stall")
    none: frozenset[str] = frozenset()
    assert precheck_action(attempt, known_character_ids=none, location_ids=none) is None
    stranger = attempt.model_copy(update={"target_character_id": uuid.uuid4()})
    assert "unknown partner" in str(
        precheck_action(stranger, known_character_ids=none, location_ids=none)
    )
    with_item = attempt.model_copy(update={"item_instance_id": item})
    out_of_reach = precheck_action(
        with_item,
        known_character_ids=none,
        location_ids=none,
        carried_item_ids=none,
        item_ids_here=none,
    )
    assert "out of reach" in str(out_of_reach)
    in_hand = precheck_action(
        with_item,
        known_character_ids=none,
        location_ids=none,
        carried_item_ids=frozenset({str(item)}),
        item_ids_here=none,
    )
    assert in_hand is None


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_an_attempt_is_judged_and_remembered_with_its_outcome(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_connected())  # Wren at the Hearth, Ash at the Market
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        system = request.system or ""
        if "You decide" in system and "<<untrusted:identity>>Wren" in request.prompt:
            if "heave the wheel free" in request.prompt:
                return json.dumps({"family": "wait"})  # beat 2: already remembered
            return json.dumps({"family": "interact", "attempt": "heave the wheel free."})
        if "You decide" in system:
            return json.dumps({"family": "wait"})
        if "You resolve" in system:
            return json.dumps(
                {"outcome": "success", "effects": [], "rationale": "Wren's back does it."}
            )
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    resolver = [r.prompt for r in gateway.sent_requests if "You resolve" in (r.system or "")]
    # The resolver sees who tries what, by name, with the id effects need,
    # and where they stand.
    assert any(
        f"Wren (character:{ids['wren']}), at " in p and "tries to heave the wheel free" in p
        for p in resolver
    )

    before = len(gateway.sent_requests)
    assert _advance(client, ids["world"], 2).status_code == 200
    wren = next(
        r.prompt
        for r in gateway.sent_requests[before:]
        if "You decide" in (r.system or "") and "<<untrusted:identity>>Wren" in r.prompt
    )
    assert "Wren tries to heave the wheel free: it works" in wren


def test_resolver_sees_names_and_content_not_just_families() -> None:
    from worldsim.domain.commands import CommunicateAction, MoveAction
    from worldsim.domain.rules.resolution import describe_intent
    from worldsim.domain.scenes import Intent

    view, me, away = _view()

    def intent(action: object) -> Intent:
        return Intent.model_validate(
            {
                "id": str(uuid.uuid4()),
                "world_id": str(view.world.id),
                "snapshot_id": str(SNAP),
                "phase_run_id": str(uuid.uuid4()),
                "author_character_id": str(me.id),
                "action": action,
                "idempotency_key": "character:t",
            }
        )

    talk = CommunicateAction(
        character_id=me.id, snapshot_id=SNAP, target_character_id=away.id, topic='"Cart stuck?"'
    )
    assert describe_intent(intent(talk.model_dump(mode="json")), view) == (
        f'Wren (character:{me.id}) says to Ash (character:{away.id}): "Cart stuck?"'
    )
    there = view.locations[1]
    move = MoveAction(character_id=me.id, snapshot_id=SNAP, destination_location_id=there.id)
    assert f"moves to B (location {there.id})" in describe_intent(
        intent(move.model_dump(mode="json")), view
    )
