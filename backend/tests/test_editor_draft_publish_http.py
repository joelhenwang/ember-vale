"""Publish response identity over HTTP (E3, review follow-up).

The publish endpoint names the exact published/replayed revision
separately from the Library head, so a nested return flow can pin an
unambiguous revision even after later revisions exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

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


def _open(client: ApiClient, preset_id: str, base: int) -> dict[str, Any]:
    opened = client.post(
        f"/api/v1/library/presets/{preset_id}/editor-drafts",
        json={"base_revision": base},
        headers={},
    )
    assert opened.status_code == 200, opened.text
    return opened.json()


def _save(
    client: ApiClient, preset_id: str, draft_id: str, version: int, fields: dict[str, Any]
) -> dict[str, Any]:
    saved = client.patch(
        f"/api/v1/library/presets/{preset_id}/editor-drafts/{draft_id}",
        json={"fields": fields, "expected_version": version},
        headers={},
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def _publish(
    client: ApiClient, preset_id: str, draft_id: str, version: int, preset_version: int
):
    return client.post(
        f"/api/v1/library/presets/{preset_id}/editor-drafts/{draft_id}/publish",
        json={"expected_version": version, "preset_expected_version": preset_version},
        headers={},
    )


def _complete(client: ApiClient, preset_id: str, draft_id: str, version: int) -> None:
    completed = client.post(
        f"/api/v1/library/presets/{preset_id}/editor-drafts/{draft_id}/complete",
        json={"expected_version": version},
        headers={},
    )
    assert completed.status_code == 200, completed.text


def test_publish_replay_names_older_revision_after_newer_lands(client: ApiClient) -> None:
    """Replaying publication 2 after revision 3 exists names revision 2.

    The head still reports current_revision 3, but the response carries
    the replayed revision number and its payload separately, so a caller
    can pin exactly what was published.
    """
    made = client.post(
        "/api/v1/library/presets",
        json={"kind": "character", "name": "Miri", "payload": {"name": "Miri"}},
        headers={},
    )
    assert made.status_code == 200, made.text
    preset_id = made.json()["id"]

    first_draft = _open(client, preset_id, 1)
    first_saved = _save(
        client, preset_id, first_draft["id"], 1, {"name": "Miri of the ford"}
    )
    first = _publish(client, preset_id, first_draft["id"], first_saved["version"], 0)
    assert first.status_code == 200, first.text
    assert first.json()["published_revision"] == 2
    _complete(client, preset_id, first_draft["id"], first_saved["version"])

    second_draft = _open(client, preset_id, 2)
    second_saved = _save(
        client, preset_id, second_draft["id"], 1, {"name": "Miri of the hills"}
    )
    second = _publish(client, preset_id, second_draft["id"], second_saved["version"], 1)
    assert second.status_code == 200, second.text
    assert second.json()["published_revision"] == 3

    replay = _publish(client, preset_id, first_draft["id"], first_saved["version"], 0)
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["published_revision"] == 2
    assert body["detail"]["current_revision"] == 3
    assert body["detail"]["revision"]["name"] == "Miri of the ford"
