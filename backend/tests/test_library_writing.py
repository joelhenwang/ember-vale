"""Writing help in the studios, and painting a character from how they look."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_stage1_api import ApiClient
from test_story_travel import MIGRATIONS, SEED_DIR

from worldsim.application.library.writing import (
    Field,
    Place,
    WritingAnswerError,
    enhance_prompt,
    fill_prompt,
    parse_enhanced,
    parse_filled,
)
from worldsim.application.ports.images import GeneratedImage, ImageRequest
from worldsim.application.ports.writer import Written
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ASSETS = SEED_DIR.parent.parent / "assets"

HAIR = Field("hair", "Hair", "colour and cut", "", 200)
EYES = Field("eyes", "Eyes", "colour", "grey", 100)
AGE = Field("age", "Age", "a number", "", 20)


def test_fill_asks_only_for_what_is_empty_and_keeps_the_rest() -> None:
    prompt = fill_prompt("character", "A ferrywoman who knows the river.", [HAIR, EYES], "Nessa")
    assert "It is called Nessa." in prompt
    assert "- Eyes: grey" in prompt  # decided: context, not a question
    assert '"hair" (Hair)' in prompt and '"eyes" (Eyes)' not in prompt
    assert "places" not in prompt.split("Answer with JSON")[1]


def test_fill_answers_are_trimmed_to_the_empty_fields() -> None:
    answer = '```json\n{"fields": {"hair": "  Long, salt-grey braid ", "eyes": "blue",'
    answer += ' "age": "' + "9" * 50 + '", "extra": "x"}}\n```'
    values, places = parse_filled(answer, [HAIR, EYES, AGE])
    # Eyes were the player's; extra was never asked for; age is cut to its length.
    assert values == {"hair": "Long, salt-grey braid", "age": "9" * 20}
    assert places == []


def test_places_are_described_and_added_but_never_doubled() -> None:
    known = [Place("Hearth", "A warm inn."), Place("Old Mill", "")]
    prompt = fill_prompt("world", "A river vale.", [], places=known, add_places=2)
    assert "Old Mill: (not described yet: describe it)" in prompt and "Add 2 new places" in prompt
    answer = json.dumps(
        {
            "fields": {},
            "places": [
                {"name": "Hearth", "description": "Rewritten."},  # already described: kept
                {"name": "old mill", "description": "A creaking wheel."},
                {"name": "Reedmarsh", "description": "Herons."},
                {"name": "Reedmarsh", "description": "Again."},
                {"name": "Stonebridge", "description": "Moss."},
                {"name": "Third", "description": "One too many."},
            ],
        }
    )
    _, places = parse_filled(answer, [], known, add_places=2)
    assert [(p.name, p.new) for p in places] == [
        ("Old Mill", False),
        ("Reedmarsh", True),
        ("Stonebridge", True),
    ]
    # Each place picks a kind the studio offers; anything else is left blank.
    kinds = ["Village inn", "Marsh"]
    assert "one of: Village inn, Marsh" in fill_prompt(
        "world", "", [], places=known, place_kinds=kinds
    )
    answer = json.dumps(
        {
            "places": [
                {"name": "Reedmarsh", "description": "Herons.", "kind": "marsh"},
                {"name": "Tower", "description": "Tall.", "kind": "castle"},
            ]
        }
    )
    _, places = parse_filled(answer, [], [], add_places=2, place_kinds=kinds)
    assert [(p.name, p.kind) for p in places] == [("Reedmarsh", "Marsh"), ("Tower", "")]


def test_an_unreadable_answer_is_an_error() -> None:
    with pytest.raises(WritingAnswerError):
        parse_enhanced("Sure! Here is a better overview.")
    with pytest.raises(WritingAnswerError):
        parse_enhanced('{"text": "  "}')
    assert parse_enhanced('{"text": "A ferrywoman."}') == "A ferrywoman."
    assert "<overview>\nkey points\n</overview>" in enhance_prompt("world", "  key points ")


class _Writer:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    async def write(self, prompt: str) -> Written:
        self.prompts.append(prompt)
        return Written(self.answer, "fake/writer", 0.2, 0.0001)


class _Painter:
    def __init__(self) -> None:
        self.requests: list[ImageRequest] = []

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        self.requests.append(request)
        out = io.BytesIO()
        Image.new("RGB", (64, 64), (120, 80, 50)).save(out, format="PNG")
        return GeneratedImage(out.getvalue(), "image/png", 64, 64)


@pytest.fixture
def raw(migrated_db: None) -> Iterator[TestClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as client:
        yield client


def test_enhance_and_fill_through_the_api(raw: TestClient) -> None:
    client = ApiClient(raw)
    state = raw.app.state.app_state  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]
    state._writer = None
    state.settings.provider.openrouter_api_key = None
    missing = client.post(
        "/api/v1/library/writing/enhance", json={"kind": "character", "overview": "tall"}
    )
    assert missing.status_code == 409, missing.text

    state._writer = _Writer('{"text": "A tall ferrywoman with a quiet laugh."}')
    enhanced = client.post(
        "/api/v1/library/writing/enhance",
        json={"kind": "character", "overview": "tall ferrywoman", "name": "Nessa"},
    )
    assert enhanced.status_code == 200, enhanced.text
    assert enhanced.json()["text"] == "A tall ferrywoman with a quiet laugh."
    assert enhanced.json()["cost_usd"] == pytest.approx(0.0001)

    state._writer = _Writer('{"fields": {"hair": "Grey braid", "eyes": "green"}}')
    body = {
        "kind": "character",
        "overview": "tall ferrywoman",
        "fields": [
            {"key": "hair", "label": "Hair", "hint": "colour and cut"},
            {"key": "eyes", "label": "Eyes", "value": "grey"},
        ],
    }
    filled = client.post("/api/v1/library/writing/fill", json=body)
    assert filled.status_code == 200, filled.text
    assert filled.json()["values"] == {"hair": "Grey braid"}

    body["fields"] = [{"key": "eyes", "label": "Eyes", "value": "grey"}]
    nothing = client.post("/api/v1/library/writing/fill", json=body)
    assert nothing.status_code == 422, nothing.text


def test_a_character_is_painted_from_how_they_look(raw: TestClient) -> None:
    client = ApiClient(raw)
    painter = _Painter()
    raw.app.state.app_state._images = painter  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]
    painted = client.post(
        "/api/v1/library/portraits/paint",
        json={"prompt": "a tall ferrywoman, grey braid, green eyes"},
    )
    assert painted.status_code == 200, painted.text
    asset_id = painted.json()["asset_id"]
    try:
        # The house style is wrapped around the player's words.
        assert painter.requests[0].prompt.startswith("a tall ferrywoman, grey braid, green eyes")
        assert len(painter.requests[0].prompt) > len("a tall ferrywoman, grey braid, green eyes")
        assert client.get(f"/api/v1/library/assets/{asset_id}/bytes").status_code == 200
        # It is a portrait: the face can be looked for on it.
        assert client.post(f"/api/v1/library/maps/{asset_id}/places").status_code == 404
    finally:
        for found in Path(ASSETS / "generated" / "portraits").glob(f"{asset_id}.*"):
            found.unlink()
