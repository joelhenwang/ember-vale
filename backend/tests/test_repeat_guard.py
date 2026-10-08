"""Repeated questions: answered exchanges are shown, and a repeat gets one retry."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import (
    MIGRATIONS,
    SEED_DIR,
    ApiClient,
    _advance,
    _route_for,
    _seed_two_at_hearth,
)

from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.rules.repeats import (
    Exchange,
    answered_exchanges,
    overlap,
    repeated,
    retry_note,
    settled_note,
)
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

LINES = [
    (1, "Wren says to Ash: What brings you to the vale?"),
    (1, 'Ash replies to Wren: "The harvest fair, and a debt to settle."'),
    (2, "Wren says to Ash: Do you know the miller?"),
    (5, "Wren says to Marta: Seen my purse?"),
]


def test_answered_exchanges_pair_lines_with_their_replies() -> None:
    found = answered_exchanges(LINES, "Wren")
    assert found == [
        Exchange(
            1, "What brings you to the vale?", "Ash", "Ash: The harvest fair, and a debt to settle."
        )
    ]  # the miller and the purse were never answered: asking again is fine


def test_a_repeat_is_caught_by_words_or_by_meaning() -> None:
    answered = answered_exchanges(LINES, "Wren")
    assert overlap("So what brings you to the vale, Ash?", answered[0].said) >= 0.6
    assert repeated("So what brings you to the vale, Ash?", answered) == answered[0]
    assert repeated("Shall we walk to the mill?", answered) is None
    # A paraphrase with no shared words, caught by embeddings.
    assert repeated("Why did you come here?", answered, {0: 0.9}) == answered[0]
    assert "do not ask again" in settled_note(answered)
    assert "The harvest fair" in retry_note("Why did you come here?", answered[0])


@pytest.fixture
def client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_a_repeated_question_gets_one_retry_with_the_answer(
    client: tuple[ApiClient, FakeGateway],
) -> None:
    api, gateway = client
    ids = asyncio.run(_seed_two_at_hearth())
    base = _route_for(ids, {})
    question = "What brings you to the vale?"

    def route(request: CompletionRequest) -> str | None:
        system, prompt = request.system or "", request.prompt
        wren = "<<untrusted:identity>>Wren" in prompt
        if "You decide" in system and wren:
            topic = (
                "Let us walk to the fair together"
                if "You were about to say" in prompt
                else question
            )
            return json.dumps(
                {"family": "communicate", "target_character_id": str(ids["ash"]), "topic": topic}
            )
        if "You decide" in system:
            return json.dumps({"family": "wait"})
        if "You react" in system and not wren:
            index = 1 if "Day 1, sunrise" in prompt and "Day 1, morning" not in prompt else 2
            return json.dumps(
                {
                    "character_id": str(ids["ash"]),
                    "snapshot_id": str(derive_snapshot_id(derive_run_id(ids["world"], index))),
                    "family": "communicate",
                    "target_character_id": str(ids["wren"]),
                    "topic": '"The harvest fair, and a debt to settle."',
                }
            )
        return base(request)

    gateway.route = route
    assert _advance(api, ids["world"], 1).status_code == 200
    before = len(gateway.sent_requests)
    assert _advance(api, ids["world"], 2).status_code == 200
    decisions = [
        r.prompt
        for r in gateway.sent_requests[before:]
        if "You decide" in (r.system or "") and "<<untrusted:identity>>Wren" in r.prompt
    ]
    assert len(decisions) == 2  # the repeat, then one retry
    assert "Already asked and answered" in decisions[0]
    assert 'You were about to say "What brings you to the vale?"' in decisions[1]
    assert "The harvest fair, and a debt to settle." in decisions[1]


def test_a_reply_that_repeats_an_answered_question_gets_one_retry(
    client: tuple[ApiClient, FakeGateway],
) -> None:
    api, gateway = client
    ids = asyncio.run(_seed_two_at_hearth())
    base = _route_for(ids, {})
    question = "What brings you to the vale?"
    beat = {"n": 1}

    def reply(who: str, to: str, topic: str) -> str:
        snapshot = derive_snapshot_id(derive_run_id(ids["world"], beat["n"]))
        return json.dumps(
            {
                "character_id": str(ids[who]),
                "snapshot_id": str(snapshot),
                "family": "communicate",
                "target_character_id": str(ids[to]),
                "topic": topic,
            }
        )

    def route(request: CompletionRequest) -> str | None:
        system, prompt = request.system or "", request.prompt
        wren = "<<untrusted:identity>>Wren" in prompt
        if "You decide" in system:
            if wren and beat["n"] == 1:  # Wren asks; Ash answers below
                return json.dumps(
                    {
                        "family": "communicate",
                        "target_character_id": str(ids["ash"]),
                        "topic": question,
                    }
                )
            if not wren and beat["n"] == 2:  # Ash speaks; Wren replies below
                return json.dumps(
                    {
                        "family": "communicate",
                        "target_character_id": str(ids["wren"]),
                        "topic": "Fine weather for the fair.",
                    }
                )
            return json.dumps({"family": "wait"})
        if "You react" in system and not wren and beat["n"] == 1:
            return reply("ash", "wren", '"The harvest fair, and a debt to settle."')
        if "You react" in system and wren and beat["n"] == 2:
            again = "You were about to say" in prompt
            return reply("wren", "ash", "Then walk there with me." if again else question)
        return base(request)

    gateway.route = route
    assert _advance(api, ids["world"], 1).status_code == 200
    beat["n"] = 2
    before = len(gateway.sent_requests)
    assert _advance(api, ids["world"], 2).status_code == 200
    replies = [
        r.prompt
        for r in gateway.sent_requests[before:]
        if "You react" in (r.system or "") and "<<untrusted:identity>>Wren" in r.prompt
    ]
    assert len(replies) == 2  # the repeat, then one retry
    assert "Already asked and answered" in replies[0]
    assert 'You were about to say "What brings you to the vale?"' in replies[1]
    assert "The harvest fair, and a debt to settle." in replies[1]
