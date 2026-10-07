"""S0-API-001: HTTP boundary contracts (owned by S0-API-001)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

import worldsim
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"
OPENAPI = ROOT / "content" / "schemas" / "openapi.json"


class BoundaryClient:
    """Strict-typed facade over the untyped starlette test client."""

    def __init__(self, raw: TestClient) -> None:
        self._raw = raw

    def _raw_any(self) -> Any:
        return self._raw

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().get(url, **kwargs))

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().post(url, **kwargs))


@pytest.fixture
def boundary(migrated_db: None) -> Iterator[tuple[BoundaryClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield BoundaryClient(raw), gateway


def test_unseeded_boundary(
    boundary: tuple[BoundaryClient, FakeGateway], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health, readiness and lookups before any world exists (one app)."""
    monkeypatch.setenv("WORLDSIM_SECURITY__API_KEY", "sentinel-key-xyz")
    client, _gateway = boundary
    live = client.get("/api/v1/health/live", headers={"X-Request-ID": "req-demo-1"})
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert live.headers["X-Request-ID"] == "req-demo-1"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "degraded"
    assert body["version"] == worldsim.__version__
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    assert body["migration_head"] in ScriptDirectory.from_config(config).get_heads()
    assert body["schema_version"] == 1
    by_name = {check["name"]: check for check in body["checks"]}
    assert by_name["database"]["status"] == "ok"
    assert by_name["migrations"]["status"] == "ok"
    assert by_name["extensions"]["status"] == "ok"
    assert by_name["seed"]["status"] == "degraded"
    assert "sentinel-key-xyz" not in ready.text

    missing = client.get("/api/v1/world")
    assert missing.status_code == 404
    error = missing.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == missing.headers["X-Request-ID"]
    task = client.get("/api/v1/operations/tasks/10000000-0000-4000-8000-000000009999")
    assert task.status_code == 404


def test_seed_inspect_and_reconcile(boundary: tuple[BoundaryClient, FakeGateway]) -> None:
    client, _gateway = boundary
    first = client.post("/api/v1/world/seed")
    assert first.status_code == 200
    assert first.json()["seed_version"] == "stage0-v1"
    assert first.json()["duplicate"] is False
    world_id = first.json()["world_id"]
    second = client.post("/api/v1/world/seed")
    assert second.json()["duplicate"] is True
    assert second.json()["world_id"] == world_id

    world = client.get("/api/v1/world").json()
    assert world["id"] == world_id
    assert world["name"] == "Ember Vale"
    assert world["day"] == 1
    assert world["phase"] == "dawn"
    assert world["absolute_index"] == 0

    clock = client.get("/api/v1/world/clock").json()
    assert clock == {"day": 1, "phase": "dawn", "absolute_index": 0}

    current = client.get("/api/v1/world/phases/current").json()
    assert current["absolute_index"] == 0
    assert current["run_id"] is None

    events = client.get("/api/v1/world/events", params={"after": 0}).json()
    assert len(events["entries"]) == 1
    assert events["entries"][0]["sequence"] == 1
    assert events["entries"][0]["event_type"] == "world_seeded"
    assert events["next_after"] == 1
    empty = client.get("/api/v1/world/events", params={"after": 1}).json()
    assert empty["entries"] == [] and empty["next_after"] == 1
    bad_after = client.get("/api/v1/world/events", params={"after": -1})
    assert bad_after.status_code == 422
    assert bad_after.json()["error"]["code"] == "VALIDATION_FAILED"
    assert client.get("/api/v1/world/events", params={"limit": 0}).status_code == 422

    report = client.post("/api/v1/operations/reconcile", json={"world_id": world_id}).json()
    assert report["open_run_id"] is None
    assert report["open_state"] is None


def test_error_status_mapping_is_stable() -> None:
    from worldsim.domain.errors import ErrorCode
    from worldsim.interfaces.http.errors import status_for

    assert status_for(ErrorCode.NOT_FOUND) == 404
    assert status_for(ErrorCode.FORBIDDEN) == 403
    assert status_for(ErrorCode.VERSION_CONFLICT) == 409
    assert status_for(ErrorCode.IDEMPOTENCY_CONFLICT) == 409
    assert status_for(ErrorCode.PRECONDITION_FAILED) == 409
    assert status_for(ErrorCode.VALIDATION_FAILED) == 422
    assert status_for(ErrorCode.UNSUPPORTED_ACTION) == 422
    assert status_for(ErrorCode.INVARIANT_VIOLATED) == 500


def test_openapi_matches_committed() -> None:
    app = create_app(Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS)
    generated = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    assert generated == OPENAPI.read_text(encoding="utf-8")
