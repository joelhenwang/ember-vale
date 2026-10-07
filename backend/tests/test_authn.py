"""API key enforcement tests: closed with a key, open without, health exempt."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from worldsim.infrastructure.settings import SecuritySettings, Settings
from worldsim.interfaces.http.app import create_app


def _app(key: str | None) -> TestClient:
    settings = Settings(security=SecuritySettings(api_key=SecretStr(key) if key else None))
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_keyless_app_stays_open(migrated_db: None) -> None:
    with _app(None) as raw:
        assert raw.get("/api/v1/health/live").status_code == 200
        assert raw.get("/api/v1/no-such-route").status_code == 404


def test_keyed_app_needs_the_bearer_key_except_for_health(migrated_db: None) -> None:
    with _app("s3cr3t") as raw:
        denied = raw.get("/api/v1/no-such-route")
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "UNAUTHORIZED"
        assert "X-Request-ID" in denied.headers
        for wrong in ("s3cr3t", "Bearer wrong"):  # no scheme, wrong value
            assert (
                raw.get("/api/v1/no-such-route", headers={"Authorization": wrong}).status_code
                == 401
            )
        assert raw.get("/api/v1/health/live").status_code == 200
        assert raw.get("/api/v1/health/ready").status_code == 200
        bearer = {"Authorization": "Bearer s3cr3t"}
        assert raw.get("/api/v1/no-such-route", headers=bearer).status_code == 404
