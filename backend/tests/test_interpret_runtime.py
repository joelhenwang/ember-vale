"""Pinned interpretation runtime at the HTTP boundary.

A story pinning a provider profile revision interprets directions through
that exact revision (the runtime-selection mechanism beats use), with the
requested pin, the executed model, and the outcome in the trace audit.
Unpinned stories keep environment interpretation, still audited, and items
needing clarification stay in the operator queue across reloads.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from test_intervention_advance import _directed_route, _seed_market_world

from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
from worldsim.domain.time import utcnow
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.models.calls import ModelCallRow
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


@pytest.fixture
def interpret_app(migrated_db: None) -> Iterator[tuple[TestClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = _directed_route
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield raw, gateway


def _deity() -> dict[str, str]:
    return {"X-Worldsim-Role": "deity"}


async def _pin_world(world: UUID, profile_id: str, revision: int) -> None:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            await uow.stories.put_setup(
                StoryInitialSetup(
                    world_id=world,
                    payload={
                        "schema_version": 1,
                        "provenance": "created",
                        "art": {
                            "profile_id": profile_id,
                            "profile_revision": revision,
                        },
                    },
                    content_hash="interpret-pin",
                    created_at=utcnow(),
                    provenance=SetupProvenance.CREATED,
                )
            )
            await uow.commit()
    finally:
        await engine.dispose()


async def _calls_for(world: UUID) -> list[ModelCallRow]:
    engine = create_engine(Settings())
    try:
        async with AsyncSession(engine) as session:
            rows = (
                await session.execute(
                    sa_select(ModelCallRow).where(ModelCallRow.world_id == world)
                )
            ).scalars().all()
            return list(rows)
    finally:
        await engine.dispose()


def test_pinned_interpretation_uses_pin_and_audits(
    interpret_app: tuple[TestClient, FakeGateway],
) -> None:
    client, _gateway = interpret_app
    ids = asyncio.run(_seed_market_world())
    world = ids["world"]

    connection = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": "fake",
            "name": "Travel Pin",
            "endpoint": "http://127.0.0.1:7144/v1",
            "allow_local_endpoint": True,
        },
        headers={},
    )
    assert connection.status_code == 200, connection.text
    profile = client.post(
        f"/api/v1/settings/providers/{connection.json()['id']}/profiles",
        json={"model_id": "fake-travel-pin", "temperature": 0.3},
        headers={},
    )
    assert profile.status_code == 200, profile.text
    pin = profile.json()
    asyncio.run(_pin_world(world, pin["id"], pin["revision"]))

    filed = client.post(
        "/api/v1/interventions",
        headers=_deity(),
        json={
            "world_id": str(world),
            "client_request_id": "interpret-pin-1",
            "text": "Send Wren to Market",
            "mode": "force",
        },
    )
    assert filed.status_code == 200, filed.text
    item = filed.json()
    assert item["status"] == "queued"
    assert len(item["steps"]) == 1

    rows = asyncio.run(_calls_for(world))
    assert rows, "expected an audited interpretation call"
    sampling = rows[0].request["sampling"]
    assert sampling["model_id"] == "fake-travel-pin"
    assert sampling["pin_profile_id"] == pin["id"]
    assert sampling["pin_profile_revision"] == pin["revision"]
    assert rows[0].result["model"] == "fake-travel-pin"
    assert rows[0].profile_version.startswith("pin-")


def test_unpinned_clarification_stays_queued_across_reload(
    interpret_app: tuple[TestClient, FakeGateway],
) -> None:
    client, _gateway = interpret_app
    ids = asyncio.run(_seed_market_world())
    world = ids["world"]

    filed = client.post(
        "/api/v1/interventions",
        headers=_deity(),
        json={
            "world_id": str(world),
            "client_request_id": "interpret-plain-1",
            "text": "mumble vaguely",
            "mode": "force",
        },
    )
    assert filed.status_code == 200, filed.text
    assert filed.json()["status"] == "needs_clarification"

    # A reload re-reads the operator queue: the item is still there.
    listed = client.get(
        "/api/v1/interventions", params={"world_id": str(world)}, headers=_deity()
    )
    assert listed.status_code == 200, listed.text
    assert [entry["id"] for entry in listed.json()] == [filed.json()["id"]]

    rows = asyncio.run(_calls_for(world))
    assert rows, "expected an audited interpretation call"
    assert "pin_profile_id" not in rows[0].request["sampling"]
