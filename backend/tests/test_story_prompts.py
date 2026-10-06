"""Story settings: the player's words around storyteller and image prompts."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_images import PACKS, _Painter
from test_stage1_api import (
    MIGRATIONS,
    SEED_DIR,
    ApiClient,
    _advance,
    _route_for,
    _seed_two_at_hearth,
)

from worldsim.application.images import queue_image
from worldsim.application.orchestration.framing import FramedGateway, frame_gateways
from worldsim.application.ports.model_gateway import CompletionRequest, ModelGateway
from worldsim.domain.assets import AssetKind
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.images.runner import ImageJobRunner
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http.app import create_app


def test_framing_wraps_the_prompt_and_leaves_the_system_alone() -> None:
    inner = FakeGateway(profile=FAKE_TEST_PROFILE)
    inner.route = lambda request: "ok"
    gateway = FramedGateway(inner, "Keep it grim.", "No modern words.")

    async def run() -> None:
        await gateway.complete(CompletionRequest(system="You narrate.", prompt="Scene: rain."))

    asyncio.run(run())
    sent = inner.sent_requests[-1]
    assert sent.prompt == "Keep it grim.\n\nScene: rain.\n\nNo modern words."
    assert sent.system == "You narrate."
    assert gateway.profile is inner.profile
    plain: dict[str, ModelGateway] = {"narrator": inner, "character": inner, "director": inner}
    assert frame_gateways(plain, " ", "") is plain  # nothing to add: untouched
    wrapped = frame_gateways(plain, "Keep it grim.", "")
    assert set(wrapped) == set(plain)  # every role, not only some
    assert all(isinstance(g, FramedGateway) for g in wrapped.values())


@pytest.fixture
def stack(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _save(api: ApiClient, world: UUID, version: int, **fields: Any) -> Any:
    return api.put(f"/api/v1/stories/{world}/prompts", json={**fields, "expected_version": version})


def test_story_words_round_trip_and_guard_their_version(
    stack: tuple[ApiClient, FakeGateway],
) -> None:
    api, _ = stack
    ids = asyncio.run(_seed_two_at_hearth())
    world = ids["world"]
    empty = api.get(f"/api/v1/stories/{world}/prompts").json()
    assert empty["version"] == 0 and empty["llm_prefix"] == ""
    assert [c["name"] for c in empty["characters"]] == ["Ash", "Wren"]
    saved = _save(
        api,
        world,
        0,
        llm_prefix="  Keep it grim.  ",
        image_suffix="muted colours",
        characters=[{"character_id": str(ids["wren"]), "suffix": "red scarf"}],
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["version"] == 1 and body["llm_prefix"] == "Keep it grim."
    wren = next(c for c in body["characters"] if c["name"] == "Wren")
    assert wren["suffix"] == "red scarf"
    assert _save(api, world, 0, llm_prefix="stale").status_code == 409
    stranger = {"character_id": "00000000-0000-0000-0000-000000000001", "prefix": "x"}
    assert _save(api, world, 1, characters=[stranger]).status_code == 422


def test_turn_prompts_carry_the_story_words(stack: tuple[ApiClient, FakeGateway]) -> None:
    api, gateway = stack
    ids = asyncio.run(_seed_two_at_hearth())
    gateway.route = _route_for(ids, {})
    assert _save(api, ids["world"], 0, llm_prefix="Keep it grim.", llm_suffix="No modern words.")
    assert _advance(api, ids["world"], 1).status_code == 200
    framed = [r for r in gateway.sent_requests if r.prompt.startswith("Keep it grim.\n\n")]
    assert framed and all(r.prompt.endswith("\n\nNo modern words.") for r in framed)
    assert all(r.system and not r.system.startswith("Keep") for r in framed)


def test_portraits_carry_story_and_character_words(
    stack: tuple[ApiClient, FakeGateway], tmp_path: Path
) -> None:
    api, _ = stack
    ids = asyncio.run(_seed_two_at_hearth())
    world = ids["world"]
    saved = _save(
        api,
        world,
        0,
        image_prefix="storybook cover,",
        image_suffix="muted colours",
        characters=[{"character_id": str(ids["wren"]), "prefix": "tall,", "suffix": "red scarf"}],
    )
    assert saved.status_code == 200, saved.text
    painter = _Painter()

    async def run() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await queue_image(uow, world, AssetKind.PORTRAIT, ids["wren"])
                await uow.commit()
            runner = ImageJobRunner(
                lambda: create_unit_of_work(engine),
                painter,
                LocalStorage(tmp_path),
                PACKS,
                world_id=world,
            )
            while await runner.run_once():
                pass
        finally:
            await engine.dispose()

    asyncio.run(run())
    prompt = painter.requests[-1].prompt
    assert prompt.startswith("storybook cover, tall, Portrait of Wren")
    assert prompt.endswith("muted colours")
    # The character's words sit around what is drawn, before the style wording.
    assert prompt.index("red scarf") < prompt.index("hand-painted")
