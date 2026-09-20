"""Story travel: preset legs materialize at creation; bad legs roll back."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.application.commands.activities import start_activity
from worldsim.domain.activities import ActivityKind
from worldsim.domain.enums import LifeStatus
from worldsim.domain.presets import (
    Preset,
    PresetKind,
    PresetRevision,
    WorldLocationPreset,
    WorldPresetPayload,
)
from worldsim.domain.time import utcnow
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
WREN_PRESET_ID = "20000000-0000-4000-8000-000000000101"
ASH_PRESET_ID = "20000000-0000-4000-8000-000000000102"


@pytest.fixture
def client(migrated_db: None) -> Iterator[ApiClient]:
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


def _draft(client: ApiClient, world_preset: str = WORLD_PRESET_ID, world_rev: int = 2) -> str:
    created = client.post(
        "/api/v1/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": world_preset, "preset_revision": world_rev},
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
                "story": {"title": "A Morning in Ember Vale", "tone": "hopeful mystery"},
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


def _run(coro):
    return asyncio.run(coro)


def _routes(world_id: UUID) -> dict[tuple[str, str], tuple[int, int]]:
    async def _inner():
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                all_locations = await uow.locations.list_for_world(world_id)
                locations = {loc.id: loc.name for loc in all_locations}
                legs = {}
                for route in await uow.routes.list_for_world(world_id):
                    legs[(locations[route.from_location_id], locations[route.to_location_id])] = (
                        route.duration_phases,
                        route.stamina_cost,
                    )
                return legs
        finally:
            await engine.dispose()

    return _run(_inner())


def test_creation_materializes_both_directed_legs(client: ApiClient) -> None:
    created = _create(client, _draft(client), "travel-legs")
    assert created.status_code == 200, created.text
    legs = _routes(UUID(created.json()["world_id"]))
    assert legs == {("Hearth", "Market"): (1, 0), ("Market", "Hearth"): (1, 0)}


def test_created_leg_serves_travel_activity(client: ApiClient) -> None:
    created = _create(client, _draft(client), "travel-activity")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])

    async def _inner():
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                characters = await uow.characters.list_for_world(world_id)
                wren = next(c for c in characters if c.name == "Wren")
                assert wren.life_status == LifeStatus.ALIVE
                placed = await uow.locations.list_for_world(world_id)
                locations = {loc.name: loc.id for loc in placed}
                assert wren.location_id == locations["Hearth"]
                activity = await start_activity(
                    uow,
                    world_id,
                    wren.id,
                    ActivityKind.TRAVEL,
                    0,
                    to_location_id=locations["Market"],
                )
                assert activity.duration_phases == 1
                assert activity.payload["stamina_cost"] == 0
        finally:
            await engine.dispose()

    _run(_inner())


def _add_broken_world() -> str:
    """A world preset whose travel names a place that does not exist."""
    preset_id = uuid4()
    payload = WorldPresetPayload(
        name="Broken Vale",
        description="A vale with a road to nowhere.",
        lore=None,
        locations=[WorldLocationPreset(key="hearth", name="Hearth")],
        travel=[["hearth", "nowhere"]],
        starting_location_key="hearth",
        default_cast=[],
        style_pack_id=None,
    )
    now = utcnow()

    async def _inner():
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.presets.add_preset(
                    Preset(id=preset_id, kind=PresetKind.WORLD, name="Broken Vale")
                )
                await uow.presets.add_revision(
                    PresetRevision(
                        preset_id=preset_id,
                        revision=1,
                        schema_version=1,
                        payload=payload,
                        content_hash="test-broken-travel",
                        created_at=now,
                    )
                )
                await uow.commit()
        finally:
            await engine.dispose()

    _run(_inner())
    return str(preset_id)


def _row_counts() -> dict[str, int]:
    from fixtures.postgres import sync_dsn
    from psycopg import connect

    conn = connect(sync_dsn(Settings()), autocommit=True)
    try:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("world", "location", "travel_route", "story_draft")
        }
    finally:
        conn.close()


def test_consumed_draft_cannot_create_again(client: ApiClient) -> None:
    draft_id = _draft(client)
    first = _create(client, draft_id, "consume-once")
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    draft = client.get(f"/api/v1/story-drafts/{draft_id}", headers={}).json()
    assert draft["created_world_id"] == first.json()["world_id"]
    second = _create(client, draft_id, "consume-twice")
    assert second.status_code == 403, second.text
    assert second.json()["error"]["code"] == "FORBIDDEN"
    assert len(client.get("/api/v1/stories", headers={}).json()["items"]) == 1


def test_unknown_travel_endpoint_rolls_creation_back(client: ApiClient) -> None:
    before = len(client.get("/api/v1/stories", headers={}).json()["items"])
    draft_id = _draft(client, world_preset=_add_broken_world(), world_rev=1)
    rows_before = _row_counts()
    bad = _create(client, draft_id, "broken-travel")
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "VALIDATION_FAILED"
    assert len(client.get("/api/v1/stories", headers={}).json()["items"]) == before
    assert _row_counts() == rows_before
    draft = client.get(f"/api/v1/story-drafts/{draft_id}", headers={}).json()
    assert draft["created_world_id"] is None


def test_builtin_world_rev2_carries_both_legs(client: ApiClient) -> None:
    """The corrected starter revision itself names Hearth <-> Market."""

    async def _inner():
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                revision = await uow.presets.get_revision(UUID(WORLD_PRESET_ID), 2)
                payload = revision.payload
                assert isinstance(payload, WorldPresetPayload)
                assert sorted(tuple(pair) for pair in payload.travel) == [
                    ("hearth", "market"),
                    ("market", "hearth"),
                ]
        finally:
            await engine.dispose()

    _run(_inner())
