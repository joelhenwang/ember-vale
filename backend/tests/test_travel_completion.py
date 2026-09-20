"""Completed gameplay action: Wren travels Hearth -> Market through the API.

Exercises the intended production path, not an assembly of internals:
draft/create (rev 2 starter) -> POST /stage2/activities (travel) ->
POST /stage1/advance (commits the movement) -> fresh-session verification ->
idempotent retry -> presentation reads. Role headers are watcher throughout;
the engine grants watchers MANAGE_ACTIVITIES+ADVANCE (product-policy
reconciliation of observer/director powers is later milestone work).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient

from worldsim.domain.enums import ActivityStatus
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

WATCHER = {"X-Worldsim-Role": "watcher"}


@pytest.fixture
def gate(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def _script_decisions(gateway: FakeGateway, world_id: UUID, wren_id: UUID, ash_id: UUID) -> None:
    """WAIT decisions for both walkers; one honest narration beat."""
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
    from worldsim.application.ports.model_gateway import CompletionRequest

    snapshot = derive_snapshot_id(derive_run_id(world_id, 1))

    def _wait(actor: UUID) -> str:
        return json.dumps(
            {"family": "wait", "character_id": str(actor), "snapshot_id": str(snapshot)}
        )

    def _route(request: CompletionRequest) -> str | None:
        system = request.system or ""
        prompt = request.prompt
        if "You narrate" in system:
            return json.dumps([{"text": "Wren walks to the Market.", "cited_fact_keys": []}])
        if "You decide" in system:
            if "Wren" in prompt:
                return _wait(wren_id)
            if "Ash" in prompt:
                return _wait(ash_id)
        return None

    gateway.route = _route


def _run(coro):
    return asyncio.run(coro)


def _world_state(world_id: UUID):
    async def _inner():
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                characters = {c.name: c for c in await uow.characters.list_for_world(world_id)}
                locations = {loc.name: loc for loc in await uow.locations.list_for_world(world_id)}
                activities = await uow.activities.list_active_for_world(world_id)
                world = await uow.worlds.get(world_id)
                return characters, locations, activities, (world.day, world.phase.value)
        finally:
            await engine.dispose()

    return _run(_inner())


def _activity_and_events(world_id: UUID):
    async def _inner():
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                activities = await uow.activities.list_active_for_world(world_id)
                events = await uow.events.list_range(world_id, 0, 100)
                resolved = []
                for event in events:
                    if event.event_type.value == "action_resolved":
                        effects = await uow.events.list_effects(event.id)
                        resolved.append((event.sequence, len(effects)))
                return activities, [(e.sequence, e.event_type.value) for e in events], resolved
        finally:
            await engine.dispose()

    return _run(_inner())


def test_wren_travel_completes_through_advance(gate: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = gate
    created = client.post(
        "/api/v1/story-drafts",
        json={
            "payload": {
                "world": {"preset_id": WORLD_PRESET_ID, "preset_revision": 2},
                "cast": [
                    {
                        "instance_key": "wren",
                        "preset_id": WREN_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Wren",
                        "location_key": "hearth",
                    },
                    {
                        "instance_key": "ash",
                        "preset_id": ASH_PRESET_ID,
                        "preset_revision": 1,
                        "name": "Ash",
                        "location_key": "market",
                    },
                ],
                "mode": {"role": "watcher"},
                "story": {"title": "Wren Walks to Market"},
                "ai": {"art_source": "curated"},
            },
            "current_step": "review",
        },
        headers={},
    )
    assert created.status_code == 200, created.text
    made = client.post(
        "/api/v1/stories",
        json={"draft_id": created.json()["id"], "expected_draft_version": 1},
        headers={"Idempotency-Key": "completion-walk"},
    )
    assert made.status_code == 200, made.text
    world_id = UUID(made.json()["world_id"])

    characters, locations, _actives, _clock = _world_state(world_id)
    assert characters["Wren"].location_id == locations["Hearth"].id
    _script_decisions(gateway, world_id, characters["Wren"].id, characters["Ash"].id)

    started = client.post(
        "/api/v1/stage2/activities",
        json={
            "world_id": str(world_id),
            "character_id": str(characters["Wren"].id),
            "kind": "travel",
            "to_location_id": str(locations["Market"].id),
        },
        headers=WATCHER,
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == ActivityStatus.ACTIVE.value
    activity_id = started.json()["id"]

    advanced = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(world_id), "absolute_index": 1},
        headers=WATCHER,
    )
    assert advanced.status_code == 200, advanced.text

    characters, locations, actives, clock = _world_state(world_id)
    assert characters["Wren"].location_id == locations["Market"].id
    assert characters["Ash"].location_id == locations["Market"].id
    assert all(a.id != UUID(activity_id) for a in actives)
    assert clock != (1, "dawn")

    _actives, event_list, resolved = _activity_and_events(world_id)
    assert "action_resolved" in [kind for _, kind in event_list]
    assert any(count >= 1 for _, count in resolved)

    listed = client.get(f"/api/v1/stage2/activities?world_id={world_id}", headers=WATCHER)
    assert listed.status_code == 200, listed.text
    assert all(item["id"] != activity_id for item in listed.json().get("items", []))

    # Retry the same beat: no second movement, duplicate effect, or extra events.
    events_before = len(event_list)
    again = client.post(
        "/api/v1/stage1/advance",
        json={"world_id": str(world_id), "absolute_index": 1},
        headers=WATCHER,
    )
    assert again.status_code == 200, again.text
    characters, locations, _, _ = _world_state(world_id)
    assert characters["Wren"].location_id == locations["Market"].id
    _, event_list_after, _ = _activity_and_events(world_id)
    assert len(event_list_after) == events_before

    # Presentation reads expose the committed outcome.
    timeline = client.get(
        f"/api/v1/stage2/timeline?world_id={world_id}&after=0&limit=20", headers=WATCHER
    )
    assert timeline.status_code == 200, timeline.text
    entries = timeline.json()["entries"]
    assert any(e["event_type"] == "action_resolved" for e in entries)
    world_map = client.get(f"/api/v1/stage2/map?world_id={world_id}", headers=WATCHER)
    assert world_map.status_code == 200, world_map.text
    market = next(p for p in world_map.json()["places"] if p["name"] == "Market")
    assert "Wren" in market["occupants"]
    hearth = next(p for p in world_map.json()["places"] if p["name"] == "Hearth")
    assert any(r["to_location_id"] == str(locations["Market"].id) for r in hearth["routes"])
