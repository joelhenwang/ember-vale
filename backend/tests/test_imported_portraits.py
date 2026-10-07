"""A picture the player brings for a character, framed for portrait and face."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_stage1_api import ApiClient
from test_story_travel import MIGRATIONS, SEED_DIR

from worldsim.application.ports.map_reader import Reading
from worldsim.domain.framing import Frame, PictureFrames, within
from worldsim.domain.presets import CharacterPresetPayload, canonical_payload_hash
from worldsim.infrastructure.geography.openrouter import parse_face
from worldsim.infrastructure.images.runner import imported_portrait
from worldsim.infrastructure.images.shrink import crop
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"
ASSETS = SEED_DIR.parent.parent / "assets"
FRAMES = {
    "portrait": {"x": 0.25, "y": 0.0, "w": 0.5, "h": 1.0},
    "face": {"x": 0.375, "y": 0.1, "w": 0.25, "h": 0.25},
}


def test_frames_stay_inside_their_picture_and_portrait() -> None:
    portrait = Frame(x=0.25, y=0.0, w=0.5, h=1.0)
    face = Frame(x=0.375, y=0.1, w=0.25, h=0.25)
    assert PictureFrames(portrait=portrait, face=face).face == face
    with pytest.raises(ValueError):
        Frame(x=0.8, y=0.0, w=0.5, h=0.5)  # past the right edge
    with pytest.raises(ValueError):
        PictureFrames(portrait=portrait, face=Frame(x=0.0, y=0.0, w=0.2, h=0.2))
    # The face on the portrait crop: half its width in, a tenth down.
    on_crop = within(portrait, face)
    assert (on_crop.x, on_crop.y, on_crop.w, on_crop.h) == pytest.approx((0.25, 0.1, 0.5, 0.25))
    assert portrait.pixels(400, 300) == (100, 0, 300, 300)


def test_characters_without_a_picture_keep_their_hash() -> None:
    character = CharacterPresetPayload(name="Miri", appearance="Tall.")
    data = character.model_dump(mode="json")
    assert data.pop("portrait_frames") is None
    legacy = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    assert canonical_payload_hash(character) == legacy


def test_face_answers_are_cleaned() -> None:
    assert parse_face('{"face": [300, 100, 500, 350]}') == (300, 100, 500, 350)
    assert parse_face('```json\n{"face": null}\n```') is None
    assert parse_face('{"face": [500, 100, 300, 350]}') is None  # backwards
    assert parse_face('{"face": [1, 2, 3]}') is None


def test_the_service_gets_the_portrait_not_the_whole_picture() -> None:
    picture = Image.new("RGB", (400, 300), (200, 30, 30))
    raw = io.BytesIO()
    picture.save(raw, format="PNG")
    someone = UUID("00000000-0000-0000-0000-0000000000c1")
    framed = {"asset_id": str(UUID(int=1)), "portrait": [0.25, 0.0, 0.5, 1.0], "face": [0, 0, 1, 1]}
    assert imported_portrait({"other": framed}, someone, UUID(int=1)) is None
    # A newer (painted) portrait replaced the imported one: nothing to cut.
    assert imported_portrait({str(someone): framed}, someone, UUID(int=2)) is None
    frame = imported_portrait({str(someone): framed}, someone, UUID(int=1))
    assert frame is not None
    with Image.open(io.BytesIO(crop(raw.getvalue(), frame))) as cut:
        assert cut.size == (200, 300)


class _Reader:
    async def face(self, image: bytes, mime: str) -> Reading[tuple[int, int, int, int]]:
        assert image
        return Reading(((375, 100, 625, 350),), "fake/face", 0.1, 0.0004)


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        raw.app.state.app_state._map_reader = _Reader()  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]
        yield ApiClient(raw)


def _picture(size: tuple[int, int] = (300, 400)) -> str:
    out = io.BytesIO()
    Image.new("RGB", size, (90, 60, 40)).save(out, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def test_import_frame_and_play_a_character(client: ApiClient) -> None:
    uploaded = client.post("/api/v1/library/portraits", json={"data_url": _picture()})
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()["asset_id"]
    try:
        assert (uploaded.json()["width"], uploaded.json()["height"]) == (300, 400)
        assert client.get(f"/api/v1/library/assets/{asset_id}/bytes").status_code == 200
        face = client.post(f"/api/v1/library/portraits/{asset_id}/face").json()
        assert face["face"] == pytest.approx([0.375, 0.1, 0.25, 0.25])
        # A map is not a portrait.
        assert client.post(f"/api/v1/library/maps/{asset_id}/places").status_code == 404

        bad = client.post(
            "/api/v1/library/presets",
            json={
                "kind": "character",
                "name": "Miri",
                "payload": {
                    "name": "Miri",
                    "portrait_asset_id": asset_id,
                    "portrait_frames": {**FRAMES, "face": {"x": 0, "y": 0, "w": 0.1, "h": 0.1}},
                },
            },
        )
        assert bad.status_code == 422  # the face lies outside the portrait
        made = client.post(
            "/api/v1/library/presets",
            json={
                "kind": "character",
                "name": "Miri",
                "payload": {
                    "name": "Miri",
                    "portrait_asset_id": asset_id,
                    "portrait_frames": FRAMES,
                },
            },
        )
        assert made.status_code == 200, made.text
        miri = made.json()

        draft = client.post(
            "/api/v1/story-drafts",
            json={
                "payload": {
                    "world": {"preset_id": WORLD_PRESET_ID, "preset_revision": 1},
                    "cast": [
                        {
                            "instance_key": "cast-miri",
                            "preset_id": miri["id"],
                            "preset_revision": 1,
                            "name": "Miri",
                        }
                    ],
                    "mode": {"role": "watcher"},
                    "story": {"title": "Framed", "tone": "calm"},
                    "ai": {"art_source": "curated"},
                },
                "current_step": "review",
            },
        )
        assert draft.status_code == 200, draft.text
        created = client.post(
            "/api/v1/stories",
            json={"draft_id": draft.json()["id"], "expected_draft_version": 1},
            headers={"Idempotency-Key": "framed-story"},
        )
        assert created.status_code == 200, created.text
        world = created.json()["world_id"]
        cast = client.get(
            "/api/v1/world/presentation",
            params={"world_id": world},
            headers={"X-Worldsim-Role": "watcher"},
        ).json()["cast"]
        [entry] = [c for c in cast if c["name"] == "Miri"]
        assert entry["portrait_asset_id"] not in (None, asset_id)  # the story's own record
        assert entry["portrait_frame"] == [0.25, 0.0, 0.5, 1.0]
        assert entry["face_frame"] == [0.375, 0.1, 0.25, 0.25]
        art = client.get(
            f"/api/v1/assets/{entry['portrait_asset_id']}",
            params={"world_id": world},
            headers={"X-Worldsim-Role": "watcher"},
        )
        assert art.status_code == 200 and art.content[:2] == b"\xff\xd8"  # the JPEG itself
    finally:
        for stored in (ASSETS / "generated" / "portraits").glob(f"{asset_id}.*"):
            stored.unlink()


def test_large_imports_are_kept_smaller(client: ApiClient) -> None:
    uploaded = client.post("/api/v1/library/portraits", json={"data_url": _picture((3000, 4000))})
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()["asset_id"]
    try:
        assert (uploaded.json()["width"], uploaded.json()["height"]) == (1536, 2048)
    finally:
        for stored in (ASSETS / "generated" / "portraits").glob(f"{asset_id}.*"):
            stored.unlink()
