"""Story-effective provider status (owned by S3-PROV-001).

The room banner must name exactly what beats run: the resolved story pin
(including which revision of which model on which adapter) or the
environment default when nothing is pinned. A pin that no longer resolves
is reported as broken data, never silently replaced.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.domain.ids import new_world_id
from worldsim.domain.stories import SetupProvenance, StoryCatalogEntry, StoryInitialSetup
from worldsim.domain.time import utcnow
from worldsim.domain.world import World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _app() -> TestClient:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    return TestClient(app)


async def _seed_world(pin: dict[str, Any] | None) -> UUID:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Prov", seed_version="s1-test"))
            await uow.stories.put_catalog(StoryCatalogEntry(world_id=wid, title="Prov"))
            if pin is not None:
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=wid,
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            "art": pin,
                        },
                        content_hash="prov-pin",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
            await uow.commit()
            return wid
    finally:
        await engine.dispose()


def _connection(client: ApiClient, adapter: str, name: str) -> dict[str, Any]:
    res = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": adapter,
            "name": name,
            "endpoint": "http://127.0.0.1:7144/v1",
            "allow_local_endpoint": True,
        },
        headers=_watcher(),
    )
    assert res.status_code == 200, res.text
    return res.json()


def _profile(client: ApiClient, connection_id: str, model_id: str) -> dict[str, Any]:
    res = client.post(
        f"/api/v1/settings/providers/{connection_id}/profiles",
        json={"model_id": model_id},
        headers=_watcher(),
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_live_pin_over_fake_environment(migrated_db: None) -> None:
    with _app() as raw:
        client = ApiClient(raw)
        connection = _connection(client, "openrouter", "Live")
        profile = _profile(client, connection["id"], "live-model")
        world_id = asyncio.run(
            _seed_world(
                {"profile_id": profile["id"], "profile_revision": profile["revision"]}
            )
        )
        res = client.get(f"/api/v1/stories/{world_id}/provider", headers=_watcher())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pin_state"] == "ok"
    assert body["pin"]["model_id"] == "live-model"
    assert body["pin"]["adapter"] == "openrouter"
    assert body["pin"]["revision"] == profile["revision"]
    assert body["environment"]["active_profile"] == "fake"
    assert body["effective_source"] == "pin"
    assert body["effective_adapter"] == "openrouter"
    assert body["effective_model_id"] == "live-model"


def test_fake_pin_over_live_environment(
    migrated_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORLDSIM_PROVIDER__ACTIVE_PROFILE", "openrouter")
    monkeypatch.setenv("WORLDSIM_PROVIDER__OPENROUTER_API_KEY", "test-key")
    with _app() as raw:
        client = ApiClient(raw)
        connection = _connection(client, "fake", "Demo")
        profile = _profile(client, connection["id"], "fake-echo")
        world_id = asyncio.run(
            _seed_world(
                {"profile_id": profile["id"], "profile_revision": profile["revision"]}
            )
        )
        res = client.get(f"/api/v1/stories/{world_id}/provider", headers=_watcher())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pin_state"] == "ok"
    assert body["pin"]["adapter"] == "fake"
    assert body["environment"]["active_profile"] == "openrouter"
    assert body["effective_source"] == "pin"
    assert body["effective_adapter"] == "fake"


def test_unpinned_story_reports_environment_default(migrated_db: None) -> None:
    with _app() as raw:
        client = ApiClient(raw)
        world_id = asyncio.run(_seed_world(None))
        res = client.get(f"/api/v1/stories/{world_id}/provider", headers=_watcher())
        missing = client.get(f"/api/v1/stories/{uuid4()}/provider", headers=_watcher())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pin_state"] == "none"
    assert body["pin"] is None
    assert body["effective_source"] == "environment"
    assert body["effective_adapter"] == body["environment"]["adapter"]
    assert missing.status_code == 404, missing.text


def test_broken_pin_reports_unavailable(migrated_db: None) -> None:
    with _app() as raw:
        client = ApiClient(raw)
        world_id = asyncio.run(
            _seed_world({"profile_id": str(uuid4()), "profile_revision": 1})
        )
        res = client.get(f"/api/v1/stories/{world_id}/provider", headers=_watcher())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pin_state"] == "broken"
    assert body["pin"] is None
    assert body["pin_error"], "a broken pin must say what failed"
    # Execution fails closed: no effective provider may be implied, while the
    # environment block stays as diagnostic context only.
    assert body["effective_source"] == "unavailable"
    assert body["effective_adapter"] is None
    assert body["effective_model_id"] is None
    assert body["environment"]["adapter"] == "fake"
