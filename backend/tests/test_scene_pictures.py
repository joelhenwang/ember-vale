"""Scene pictures: key moments paint themselves; players can paint a scene.

The people in a picture keep their faces: portraits are registered with
the image service once per version and sent as references, with the
place's own art as a further reference.
"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_images import PACKS
from test_stage1_api import (
    MIGRATIONS,
    SEED_DIR,
    ApiClient,
    _advance,
    _player,
    _route_for,
    _seed_two_at_hearth,
    _watcher,
)

from worldsim.application.images import compose_prompt, load_style_pack
from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.pictures import service_character_id
from worldsim.application.ports.images import CharacterCard
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.assets import AssetKind, AssetRecord
from worldsim.domain.ids import new_asset_id
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.images.krea import KreaImageGenerator
from worldsim.infrastructure.images.runner import ImageJobRunner
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http.app import create_app


def _png(color: tuple[int, int, int] = (120, 80, 60)) -> bytes:
    raw = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(raw, format="PNG")
    return raw.getvalue()


class _Krea:
    """A stand-in image service that keeps what it was sent."""

    def __init__(self) -> None:
        self.characters: dict[str, dict[str, Any]] = {}
        self.generated: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.startswith("/v1/characters/"):
            known = path.rsplit("/", 1)[1] in self.characters
            return httpx.Response(200 if known else 404, json={})
        if request.method == "POST" and path == "/v1/characters":
            body = json.loads(request.content)
            if body["id"] in self.characters:
                return httpx.Response(400, json={"detail": "character already exists"})
            self.characters[body["id"]] = body
            return httpx.Response(200, json=body)
        if path == "/generate":
            self.generated.append(json.loads(request.content))
            headers = {"content-type": "image/png", "x-size": "1360x768", "x-seed": "5"}
            return httpx.Response(200, content=_png(), headers=headers)
        return httpx.Response(404)

    def client(self) -> KreaImageGenerator:
        transport = httpx.MockTransport(self)
        return KreaImageGenerator("http://krea.test", client=httpx.AsyncClient(transport=transport))


def test_service_ids_fit_the_registry_rules() -> None:
    cid = service_character_id(UUID(int=2**128 - 1), 12)
    assert len(cid) <= 40 and cid.startswith("ev-") and cid.endswith("-v12")
    assert cid == cid.lower()


def test_scene_wording_comes_from_each_pack() -> None:
    anime = load_style_pack(PACKS, "anime-saga-v1")
    pixel = load_style_pack(PACKS, "pixel-saga-v1")
    prompt, ratio = compose_prompt(anime, AssetKind.SCENE, "Wren meets Ash.")
    assert "story moment" in prompt and ratio == "16:9"
    prompt, _ = compose_prompt(pixel, AssetKind.SCENE, "Wren meets Ash.")
    assert "event illustration" in prompt


def test_a_character_registers_once() -> None:
    krea = _Krea()
    card = CharacterCard(id="ev-abc-v1", name="Wren", description="Wren, a courier", image=_png())

    async def run() -> None:
        client = krea.client()
        await client.ensure_character(card)
        await client.ensure_character(card)

    asyncio.run(run())
    assert list(krea.characters) == ["ev-abc-v1"]
    sent = krea.characters["ev-abc-v1"]
    assert sent["name"] == "Wren" and len(sent["images"]) == 1


@pytest.fixture
def stack(migrated_db: None) -> Iterator[tuple[ApiClient, TestClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), raw, gateway


def _ash_greets_wren(ids: dict[str, UUID]) -> Any:
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You decide" in system and "<<untrusted:identity>>Ash" in prompt:
            snapshot = derive_snapshot_id(derive_run_id(ids["world"], 1))
            return json.dumps(
                {
                    "family": "communicate",
                    "character_id": str(ids["ash"]),
                    "snapshot_id": str(snapshot),
                    "target_character_id": str(ids["wren"]),
                    "topic": "Well met, traveller.",
                }
            )
        return base(request)

    return route


async def _give_wren_a_portrait(ids: dict[str, UUID], root: Path) -> None:
    """Wren's portrait and the Hearth's art, as earlier jobs would leave them."""
    engine = create_engine(Settings())
    try:
        storage = LocalStorage(root)
        async with create_unit_of_work(engine) as uow:
            hearth = (await uow.locations.list_for_world(ids["world"]))[0]
            for kind, subject, ref in (
                (AssetKind.PORTRAIT, ids["wren"], "generated/wren.png"),
                (AssetKind.BACKGROUND, hearth.id, "generated/hearth.png"),
            ):
                await storage.write(ref, _png(), "image/png")
                await uow.assets.add_asset(
                    AssetRecord(
                        id=new_asset_id(),
                        world_id=ids["world"],
                        kind=kind,
                        subject_id=subject,
                        content_ref=ref,
                        mime="image/png",
                        width=64,
                        height=64,
                        style_pack_version="anime-saga-v1",
                    )
                )
            await uow.commit()
    finally:
        await engine.dispose()


def _paint_all(world_id: UUID, krea: _Krea, root: Path) -> None:
    async def run() -> None:
        engine = create_engine(Settings())
        try:
            runner = ImageJobRunner(
                lambda: create_unit_of_work(engine),
                krea.client(),
                LocalStorage(root),
                PACKS,
                world_id=world_id,
            )
            while await runner.run_once():
                pass
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_a_first_meeting_is_painted_with_faces_and_the_place(
    stack: tuple[ApiClient, TestClient, FakeGateway], tmp_path: Path
) -> None:
    api, raw, gateway = stack
    ids = asyncio.run(_seed_two_at_hearth())
    asyncio.run(_give_wren_a_portrait(ids, tmp_path))
    krea = _Krea()
    raw.app.state.app_state._images = krea.client()  # pyright: ignore[reportAttributeAccessIssue]
    selected = api.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "player", "character_id": str(ids["wren"])},
        headers=_watcher(),
    )
    assert selected.status_code == 200, selected.text
    gateway.route = _ash_greets_wren(ids)
    advanced = _advance(api, ids["world"], 1, headers=_player(ids["wren"]))
    assert advanced.status_code == 200, advanced.text

    def scene_art() -> list[dict[str, Any]]:
        view = api.get(
            "/api/v1/world/presentation",
            params={"world_id": str(ids["world"])},
            headers=_player(ids["wren"]),
        )
        return view.json()["scene_art"]

    art = scene_art()
    assert [(a["moment"], a["status"]) for a in art] == [("meeting", "pending")]
    assert art[0]["caption"] == "Wren meets Ash."

    _paint_all(ids["world"], krea, tmp_path)
    art = scene_art()
    assert art[0]["status"] == "ready" and art[0]["asset_id"]
    painted = krea.generated[-1]
    wren_face = service_character_id(ids["wren"], 1)
    assert painted["characters"] == [wren_face]  # Ash has no portrait yet: words only
    assert painted["references"][0].startswith("data:image/png;base64,")  # the Hearth
    assert "Ash" in painted["prompt"] and "story moment" in painted["prompt"]
    assert list(krea.characters) == [wren_face]
    picture = api.get(
        f"/api/v1/assets/{art[0]['asset_id']}",
        params={"world_id": str(ids["world"])},
        headers=_player(ids["wren"]),
    )
    # Allowed (the bytes themselves live in this test's own storage folder).
    assert picture.status_code != 403 and "perspective" not in picture.text

    # The same meeting never paints twice.
    assert _advance(api, ids["world"], 2, headers=_player(ids["wren"])).status_code == 200
    assert len(scene_art()) == 1

    # Paint this scene: the suggestion, edited, painted with the same face.
    scene_id = art[0]["scene_id"]
    offer = api.get(
        f"/api/v1/world/scenes/{scene_id}/picture-suggestion",
        params={"world_id": str(ids["world"])},
        headers=_player(ids["wren"]),
    ).json()
    assert offer["available"] and "Wren" in offer["prompt"] and offer["place"] == "Hearth"
    assert [(c["name"], c["has_face"]) for c in offer["characters"]] == [
        ("Wren", True),
        ("Ash", False),
    ]
    edited = "Wren and Ash share bread by the fire, laughing."
    queued = api.post(
        f"/api/v1/world/scenes/{scene_id}/pictures",
        json={"world_id": str(ids["world"]), "prompt": edited},
        headers=_player(ids["wren"]),
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "pending" and queued.json()["moment"] == "manual"
    _paint_all(ids["world"], krea, tmp_path)
    assert krea.generated[-1]["prompt"].startswith(edited)
    assert krea.generated[-1]["characters"] == [wren_face]
    assert len(krea.characters) == 1  # registered once
    assert [a["status"] for a in scene_art()] == ["ready", "ready"]


def test_suggested_words_leave_out_speech_and_backstory() -> None:
    from worldsim.application.pictures import look_of, without_speech

    told = 'Wren nods. "Well met," she says. The fire cracks. "A cairn, you say'
    assert without_speech(told) == "Wren nods. The fire cracks."
    assert without_speech("Wren nods. “Well met,” she says.") == "Wren nods."
    assert look_of("Tobin", "A young apprentice with sawdust in his hair. He ran away.") == (
        "Tobin: a young apprentice with sawdust in his hair"
    )
    assert look_of("Ola", "RED cloak, grey eyes.") == "Ola: RED cloak, grey eyes"
    assert look_of("Tobin", "A boy with sawdust in his hair, who ran from the city.") == (
        "Tobin: a boy with sawdust in his hair"
    )
    assert look_of("Ash", "") == "Ash"
