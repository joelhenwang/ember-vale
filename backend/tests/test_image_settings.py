"""Image preferences: every Krea field, applied per job, tried by preview."""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_images import _Painter, _story, _work
from test_stage1_api import ApiClient
from test_story_travel import MIGRATIONS, SEED_DIR

from worldsim.application.images import image_request
from worldsim.application.ports.images import ImageRequest
from worldsim.domain.assets import AssetKind, JobStatus
from worldsim.domain.settings import ImagePrefs
from worldsim.infrastructure.images.krea import KreaImageGenerator
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def test_every_choice_reaches_the_request_body() -> None:
    prefs = ImagePrefs(
        checkpoint="krea2Anime_v15_bf16",
        mode="full",
        detail_scale=1.4,
        turbo=False,
        steps=8,
        style="kreanima-lora-r32",
        style_scale=0.7,
        seed_mode="fixed",
        seed=42,
    )
    request = image_request("a mill", "16:9", AssetKind.BACKGROUND, prefs)
    assert KreaImageGenerator.body(request) == {
        "prompt": "a mill",
        "ratio": "16:9",
        "mode": "full",
        "turbo": False,
        "checkpoint": "krea2Anime_v15_bf16",
        "style": "kreanima-lora-r32",
        "style_scale": 0.7,
        "seed": 42,
        "detail_scale": 1.4,
        "steps": 8,
    }


def test_detail_off_or_zero_strength_turns_the_lora_off() -> None:
    off = KreaImageGenerator.body(ImageRequest(prompt="x", ratio="1:1", detail=False))
    zero = KreaImageGenerator.body(ImageRequest(prompt="x", ratio="1:1", detail_scale=0))
    assert off["detail"] is False and zero["detail"] is False
    assert "detail" not in KreaImageGenerator.body(ImageRequest(prompt="x", ratio="1:1"))


def test_seeds_ratios_and_pixel_packs() -> None:
    portrait = AssetKind.PORTRAIT
    stable = image_request("x", "1:1", portrait, ImagePrefs(), stable_seed=9)
    random = image_request("x", "1:1", portrait, ImagePrefs(seed_mode="random"), stable_seed=9)
    assert (stable.seed, random.seed) == (9, None)
    framed = ImagePrefs(portrait_ratio="3:4", place_ratio="3:2")
    assert image_request("x", "1:1", portrait, framed).ratio == "3:4"
    assert image_request("x", "16:9", AssetKind.BACKGROUND, framed).ratio == "3:2"
    assert image_request("x", "16:9", AssetKind.MAP, framed).ratio == "16:9"
    pixel = image_request("x", "1:1", portrait, ImagePrefs(), pixel="64")
    assert (pixel.style, pixel.pixel) == (None, "64")


def test_unknown_steps_are_refused() -> None:
    with pytest.raises(ValueError, match="steps"):
        ImagePrefs(steps=5)


def _krea(handler: Callable[[httpx.Request], httpx.Response]) -> KreaImageGenerator:
    transport = httpx.MockTransport(handler)
    return KreaImageGenerator("http://krea.test", client=httpx.AsyncClient(transport=transport))


def _png() -> bytes:
    raw = io.BytesIO()
    Image.new("RGB", (1360, 768), (90, 60, 40)).save(raw, format="PNG")
    return raw.getvalue()


def _service(request: httpx.Request) -> httpx.Response:
    """A Krea stand-in: catalog reads, and /generate echoing the seed."""
    path = request.url.path
    if path == "/health":
        health = {"loaded": True, "checkpoint": "krea2Anime_v15_bf16", "queued": 2}
        return httpx.Response(200, json=health)
    if path == "/v1/checkpoints":
        items = [{"id": "krea2Anime_v15_bf16", "valid": True}, {"id": "broken", "valid": False}]
        return httpx.Response(200, json={"data": items})
    if path == "/v1/styles":
        return httpx.Response(
            200, json={"data": [{"id": "kreanima-lora-r32", "label": "Kreanima"}]}
        )
    seed = json.loads(request.content).get("seed")
    headers = {
        "content-type": "image/png",
        "x-size": "1360x768",
        "x-seed": str(seed),
        "x-timings": json.dumps({"total_s": 11.5}),
    }
    return httpx.Response(200, content=_png(), headers=headers)


def test_catalog_reads_health_checkpoints_and_styles() -> None:
    catalog = asyncio.run(_krea(_service).catalog())
    assert catalog.reachable and catalog.loaded and catalog.queued == 2
    assert catalog.checkpoint == "krea2Anime_v15_bf16"
    assert catalog.checkpoints == ["krea2Anime_v15_bf16"]  # invalid ones are left out
    assert [s.label for s in catalog.styles] == ["Kreanima"]


def test_catalog_of_a_missing_service_says_so() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    catalog = asyncio.run(_krea(down).catalog())
    assert not catalog.reachable and catalog.error is not None and "refused" in catalog.error


@pytest.fixture
def client(migrated_db: None) -> Iterator[tuple[ApiClient, TestClient]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), raw


def _save_images(api: ApiClient, images: dict[str, Any]) -> httpx.Response:
    current = api.get("/api/v1/settings/preferences").json()
    return api.patch(
        "/api/v1/settings/preferences",
        json={"images": images, "expected_version": current["version"]},
    )


def test_image_preferences_round_trip_and_validate(client: tuple[ApiClient, TestClient]) -> None:
    api, _ = client
    defaults = api.get("/api/v1/settings/preferences").json()["images"]
    assert defaults["checkpoint"] == "krea2Anime_v15_bf16" and defaults["turbo"] is True
    saved = _save_images(api, {**defaults, "mode": "draft", "detail_scale": 0.5})
    assert saved.status_code == 200, saved.text
    assert saved.json()["images"]["mode"] == "draft"
    assert _save_images(api, {**defaults, "steps": 5}).status_code == 422


def test_runner_draws_with_saved_choices_and_waits_when_off(
    client: tuple[ApiClient, TestClient], tmp_path: Path
) -> None:
    api, _ = client
    world_id = _story(api)
    defaults = api.get("/api/v1/settings/preferences").json()["images"]
    assert _save_images(api, {**defaults, "enabled": False}).status_code == 200
    painter = _Painter()
    assert not any(job.status == JobStatus.READY for job in _work(world_id, painter, tmp_path))
    assert painter.requests == []  # off: the jobs stay queued
    on = {**defaults, "mode": "full", "turbo": False, "steps": 8, "portrait_ratio": "3:4"}
    assert _save_images(api, on).status_code == 200
    jobs = _work(world_id, painter, tmp_path)
    assert jobs and all(job.status == JobStatus.READY for job in jobs)
    assert {(r.mode, r.turbo, r.steps, r.ratio, r.checkpoint) for r in painter.requests} == {
        ("full", False, 8, "3:4", "krea2Anime_v15_bf16")
    }


def test_service_view_and_preview(client: tuple[ApiClient, TestClient]) -> None:
    api, raw = client
    state: Any = raw.app.state.app_state  # pyright: ignore[reportAttributeAccessIssue]
    if state.settings.images.provider != "krea":
        assert api.get("/api/v1/settings/images/service").json()["configured"] is False
        preview = api.post("/api/v1/settings/images/preview", json={"prompt": "x"})
        assert preview.status_code == 409
    state._images = _krea(_service)
    service = api.get("/api/v1/settings/images/service").json()
    assert service["reachable"] and service["checkpoint"] == "krea2Anime_v15_bf16"
    assert "16:9" in service["ratios"] and 4 in service["steps"]
    preview = api.post(
        "/api/v1/settings/images/preview",
        json={
            "prompt": "a harbour at dusk",
            "ratio": "16:9",
            "count": 2,
            "images": {"seed_mode": "fixed", "seed": 100},
        },
    )
    assert preview.status_code == 200, preview.text
    images = preview.json()["images"]
    assert [i["seed"] for i in images] == [100, 101]
    assert images[0]["data_url"].startswith("data:image/webp;base64,")
    assert images[0]["seconds"] == 11.5
