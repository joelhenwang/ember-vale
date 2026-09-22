"""Idempotent preset first publication (E3 studio wiring).

The creation receipt, the preset, and its first revision commit
atomically under a client key: the same key plus the same request
replays the same preset (even when the first response was lost), the
same key with different content conflicts, and simultaneous
submissions still mint exactly one preset.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw)


def _body(name: str = "Miri", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": name}
    if extra:
        payload.update(extra)
    return {"kind": "character", "name": name, "payload": payload}


def _create(client: ApiClient, key: str | None, body: dict[str, Any]) -> httpx.Response:
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post("/api/v1/library/presets", json=body, headers=headers)


def _count(client: ApiClient) -> int:
    listed = client.get("/api/v1/library/presets", headers={})
    assert listed.status_code == 200, listed.text
    return len(listed.json())


def test_same_key_and_request_replays_same_preset(client: ApiClient) -> None:
    before = _count(client)
    first = _create(client, "first-key", _body())
    assert first.status_code == 200, first.text
    again = _create(client, "first-key", _body())
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["current_revision"] == 1
    assert _count(client) == before + 1


def test_retry_after_committed_response_lost_returns_same_preset(
    client: ApiClient,
) -> None:
    """The first response committed server-side but never reached the
    caller: retrying the identical request must return that preset,
    byte-identical, instead of minting a second one."""
    first = _create(client, "lost-key", _body())
    assert first.status_code == 200, first.text
    committed = first.json()
    retry = _create(client, "lost-key", _body())
    assert retry.status_code == 200, retry.text
    assert retry.json() == committed


def test_same_key_with_different_content_conflicts(client: ApiClient) -> None:
    first = _create(client, "shared-key", _body("Miri"))
    assert first.status_code == 200, first.text
    renamed = _create(client, "shared-key", _body("Miri renamed"))
    assert renamed.status_code == 409, renamed.text
    assert renamed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    repayloaded = _create(
        client, "shared-key", _body("Miri", {"appearance": "A new cloak."})
    )
    assert repayloaded.status_code == 409, repayloaded.text
    assert repayloaded.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    # The conflict created nothing: the original preset still stands alone.
    detail = client.get(f"/api/v1/library/presets/{first.json()['id']}", headers={})
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "Miri"


def test_simultaneous_submissions_mint_one_preset(client: ApiClient) -> None:
    before = _count(client)
    outcomes: list[httpx.Response] = []

    def _run() -> None:
        outcomes.append(_create(client, "race-key", _body()))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(response.status_code == 200 for response in outcomes), [
        (r.status_code, r.text) for r in outcomes
    ]
    assert outcomes[0].json()["id"] == outcomes[1].json()["id"]
    assert _count(client) == before + 1


def test_keyless_creation_stays_legacy(client: ApiClient) -> None:
    """Without a key every call mints a fresh preset: older clients keep
    their behavior, and only keyed callers get replay protection."""
    first = _create(client, None, _body())
    assert first.status_code == 200, first.text
    second = _create(client, None, _body())
    assert second.status_code == 200, second.text
    assert second.json()["id"] != first.json()["id"]
