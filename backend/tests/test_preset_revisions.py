"""Preset revision repair: rev 1 stays stable, corrected config ships as rev 2.

Covers the review's upgrade matrix: fresh head installs, pre-0032 databases
with an existing draft+story, and databases where the original 0032 already
ran. Historical snapshots must survive byte-for-byte; drafts keep their exact
revision references.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.library.builtins import ensure_builtin_presets
from worldsim.domain.presets import (
    TemplatePresetPayload,
    WorldPresetPayload,
    canonical_payload_hash,
)
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"
TEMPLATE_PRESET_ID = "20000000-0000-4000-8000-000000000301"
WREN_PRESET_ID = "20000000-0000-4000-8000-000000000101"
ASH_PRESET_ID = "20000000-0000-4000-8000-000000000102"


def _run(coro):
    return asyncio.run(coro)


@contextlib.contextmanager
def _scratch_db(monkeypatch: pytest.MonkeyPatch, name: str) -> Iterator[None]:
    from fixtures.postgres import (
        create_scratch_database,
        drop_scratch_database,
        replace_database,
    )

    base = Settings()
    create_scratch_database(base, name)
    monkeypatch.setenv("WORLDSIM_DATABASE__URL", replace_database(base.database.url, name))
    try:
        yield
    finally:
        drop_scratch_database(Settings(), name)


def _upgrade_to(revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    alembic_command.upgrade(config, revision)


@contextlib.contextmanager
def _client() -> Iterator[ApiClient]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = lambda request: None
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw)


def _draft(client: ApiClient, world_rev: int = 1) -> str:
    created = client.post(
        "/api/v1/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": WORLD_PRESET_ID, "preset_revision": world_rev},
                "cast": [
                    {
                        "instance_key": "cast-wren",
                        "preset_id": WREN_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Wren",
                        "location_key": "hearth",
                    },
                    {
                        "instance_key": "cast-ash",
                        "preset_id": ASH_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Ash",
                        "location_key": "market",
                    },
                ],
                "mode": {"role": "watcher"},
                "story": {"title": "Revision probe", "tone": "hopeful mystery"},
                "ai": {"art_source": "curated"},
            },
            "current_step": "review",
        },
        headers={},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _create(client: ApiClient, draft_id: str, key: str):
    return client.post(
        "/api/v1/stories",
        json={"draft_id": draft_id, "expected_draft_version": 1},
        headers={"Idempotency-Key": key},
    )


def _setup_bytes(client: ApiClient, world_id: str) -> bytes:
    setup = client.get(f"/api/v1/stories/{world_id}/setup", headers={})
    assert setup.status_code == 200, setup.text
    return json.dumps(setup.json()["payload"], sort_keys=True).encode()


def _read_revision(preset_id: UUID, revision: int):
    async def _inner():
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                item = await uow.presets.get_revision(preset_id, revision)
                preset = await uow.presets.get_preset(preset_id)
                return item, preset.current_revision
        finally:
            await engine.dispose()

    return _run(_inner())


def test_fresh_head_has_stable_rev1_and_canonical_rev2(monkeypatch: pytest.MonkeyPatch) -> None:
    with _scratch_db(monkeypatch, "worldsim_revtest_fresh"):
        _upgrade_to("head")
        world1, world_current = _read_revision(UUID(WORLD_PRESET_ID), 1)
        assert isinstance(world1.payload, WorldPresetPayload)
        assert world1.payload.travel == []
        assert world1.content_hash == "builtin-v1"
        world2, _ = _read_revision(UUID(WORLD_PRESET_ID), 2)
        assert isinstance(world2.payload, WorldPresetPayload)
        assert sorted(tuple(pair) for pair in world2.payload.travel) == [
            ("hearth", "market"),
            ("market", "hearth"),
        ]
        assert world2.content_hash == canonical_payload_hash(world2.payload)
        tmpl1, tmpl_current = _read_revision(UUID(TEMPLATE_PRESET_ID), 1)
        assert isinstance(tmpl1.payload, TemplatePresetPayload)
        assert tmpl1.payload.world_preset_revision == 1
        tmpl2, _ = _read_revision(UUID(TEMPLATE_PRESET_ID), 2)
        assert isinstance(tmpl2.payload, TemplatePresetPayload)
        assert tmpl2.payload.world_preset_revision == 2
        assert tmpl2.content_hash == canonical_payload_hash(tmpl2.payload)
        assert world_current == 2
        assert tmpl_current == 2

        async def _ensure_twice() -> int:
            engine = create_engine(Settings())
            try:
                async with create_unit_of_work(engine) as uow:
                    first = await ensure_builtin_presets(uow)
                    await uow.commit()
                async with create_unit_of_work(engine) as uow:
                    second = await ensure_builtin_presets(uow)
                    await uow.commit()
                return first + second
            finally:
                await engine.dispose()

        assert _run(_ensure_twice()) == 0


def test_pre0032_upgrade_preserves_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-0032 database with an existing draft+story survives the repair upgrade."""
    with _scratch_db(monkeypatch, "worldsim_revtest_pre"):
        _upgrade_to("0031_settings_pipeline")
        with _client() as client:
            draft_id = _draft(client, world_rev=1)
            created = _create(client, draft_id, "pre-key")
            assert created.status_code == 200, created.text
            world_id = created.json()["world_id"]
            setup_before = _setup_bytes(client, world_id)
            draft_before = client.get(f"/api/v1/story-drafts/{draft_id}", headers={}).json()
        _upgrade_to("head")
        world1, world_current = _read_revision(UUID(WORLD_PRESET_ID), 1)
        assert world1.payload.travel == []
        assert world1.content_hash == "builtin-v1"
        assert world_current == 2
        with _client() as client:
            assert _setup_bytes(client, world_id) == setup_before
            draft_after = client.get(
                f"/api/v1/story-drafts/{draft_before['id']}", headers={}
            ).json()
            assert draft_after["payload"]["world"]["preset_revision"] == 1
            assert draft_after["created_world_id"] == world_id
            # New stories on rev 2 materialize the legs; rev 1 stories stay routeless.
            rev2_draft = _draft(client, world_rev=2)
            created = _create(client, rev2_draft, "pre-rev2-key")
            assert created.status_code == 200, created.text

            async def _legs() -> int:
                engine = create_engine(Settings())
                try:
                    async with create_unit_of_work(engine) as uow:
                        legs = await uow.routes.list_for_world(UUID(created.json()["world_id"]))
                        return len(legs)
                finally:
                    await engine.dispose()

            assert _run(_legs()) == 2


def test_post0032_upgrade_restores_rev1(monkeypatch: pytest.MonkeyPatch) -> None:
    with _scratch_db(monkeypatch, "worldsim_revtest_post"):
        _upgrade_to("0032_starter_travel")
        mutated, _ = _read_revision(UUID(WORLD_PRESET_ID), 1)
        assert sorted(tuple(pair) for pair in mutated.payload.travel) == [
            ("hearth", "market"),
            ("market", "hearth"),
        ]
        with _client() as client:
            draft_id = _draft(client, world_rev=1)
            created = _create(client, draft_id, "post-key")
            assert created.status_code == 200, created.text
            world_id = created.json()["world_id"]
            setup_before = _setup_bytes(client, world_id)
        _upgrade_to("head")
        restored, world_current = _read_revision(UUID(WORLD_PRESET_ID), 1)
        assert restored.payload.travel == []
        assert restored.content_hash == "builtin-v1"
        assert world_current == 2
        world2, _ = _read_revision(UUID(WORLD_PRESET_ID), 2)
        assert world2.content_hash == canonical_payload_hash(world2.payload)
        with _client() as client:
            # The committed snapshot is byte-identical; the draft keeps its rev 1
            # reference. Documented ambiguity: a draft pinned during the mutation
            # window now resolves the restored original content.
            assert _setup_bytes(client, world_id) == setup_before
            draft_after = client.get(f"/api/v1/story-drafts/{draft_id}", headers={}).json()
            assert draft_after["payload"]["world"]["preset_revision"] == 1
