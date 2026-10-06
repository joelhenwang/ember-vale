"""Places characters talk about that are not on the map reach the director."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for, _seed_two

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.rules.mentions import unmapped_places
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def test_unmapped_places_counts_named_and_described_places() -> None:
    said = [
        "We should check Dryden's mill before dark.",
        "Is Dryden's mill far?",
        "Let's head to the old forge.",
        "The market is busy today.",  # on the map
        "Meet me by the Market stalls",
    ]
    assert unmapped_places(said, ["Hearth", "Market"]) == [
        ("Dryden's mill", 2),
        ("old forge", 1),
    ]


def test_places_on_the_map_and_plain_talk_are_ignored() -> None:
    assert unmapped_places(["Back to the hearth", "nothing to see"], ["Hearth"]) == []
    assert unmapped_places(["the mill", "the mill", "a cave"], ["Old Mill"], limit=1) == [
        ("cave", 1)
    ]


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_director_hears_about_the_mill(stage1_client: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        system = request.system or ""
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "watching"})
        if "You decide" in system:
            wren = "<<untrusted:identity>>Wren" in request.prompt
            target = ids["ash"] if wren else ids["wren"]
            topic = (
                '"Shall we walk to the old mill?"' if wren else '"The old mill is past the stream."'
            )
            return json.dumps(
                {"family": "communicate", "target_character_id": str(target), "topic": topic}
            )
        return base(request)

    gateway.route = route
    for index in range(1, 5):  # director runs at beats 1 and 4
        assert _advance(client, ids["world"], index).status_code == 200
    director = [r.prompt for r in gateway.sent_requests if "You direct" in (r.system or "")]
    assert re.search(
        r"Places mentioned but not on the map: old mill \(\d+ mentions\)", director[-1]
    )


def test_suggestion_names_the_place_and_where_it_joins() -> None:
    import uuid

    from worldsim.application.orchestration import stage1
    from worldsim.domain.characters import Character
    from worldsim.domain.world import Location

    suggest = stage1._place_suggestion  # pyright: ignore[reportPrivateUsage]
    world = uuid.uuid4()
    hearth, market = (
        Location(id=uuid.uuid4(), world_id=world, name=n) for n in ("Hearth", "Market")
    )
    people = [
        Character(
            id=uuid.uuid4(),
            world_id=world,
            name=n,
            card_version=1,
            location_id=market.id,
            stamina=80,
            mana=40,
        )
        for n in ("Wren", "Ash")
    ]
    text = suggest([("old mill", 4)], people, [hearth, market], places_left=2)
    assert '"name": "Old Mill"' in text and f'"connect_to": "{market.id}"' in text
    assert suggest([("old mill", 4)], people, [hearth, market], places_left=0) == ""
    assert suggest([], people, [hearth, market], places_left=2) == ""


def test_landmarks_people_plan_to_visit_count_as_places() -> None:
    from worldsim.domain.rules.mentions import unmapped_places

    said = ["Let's go see the peddler by the fountain.", "I'll show you the way to the fountain."]
    assert unmapped_places(said, ["Hearth", "Market"]) == [("fountain", 2)]


def test_model_read_lines_drop_verbs_and_add_named_roads() -> None:
    keep = "Keep an eye on the cart until I return."
    forge = "Ask Bram about the forge mark on the coin."
    road = "Ash, does the north road stay open in rain?"
    ridge = "What was on that ridge you don't want me to know about?"
    read = {
        keep: [],
        forge: [],
        road: ["the north road"],
        ridge: ["that ridge"],
    }
    found = dict(unmapped_places([keep, forge, road, ridge], ["Market"], read=read))
    assert found == {"north road": 1, "ridge": 1}
    # Unread lines keep the noun list, false friends and all.
    assert dict(unmapped_places([keep], ["Market"])) == {"keep": 1}


def test_model_spans_that_are_people_or_bare_nouns_are_not_places() -> None:
    line = (
        "Let's find the stall and ask Old Marta about the shelf by Dryden's mill, "
        "and the chip on the coin's edge."
    )
    read = {line: ["stall", "Old Marta", "shelf", "Dryden's mill", "the coin's edge"]}
    found = unmapped_places([line], ["Market"], read=read, people=["Old Marta"])
    assert found == [("Dryden's mill", 1)]
