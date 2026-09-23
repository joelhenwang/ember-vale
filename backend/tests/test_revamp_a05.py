"""Revamp A05: provider revisions, sampling transmission, endpoint policy."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_preset_revisions import ASH_PRESET_ID, WORLD_PRESET_ID, WREN_PRESET_ID
from test_stage1_api import ApiClient

from worldsim.application.library.builtins import ensure_builtin_presets
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.application.settings.endpoints import EndpointPolicy, validate_endpoint
from worldsim.application.settings.resolution import SamplingParams, resolve_sampling
from worldsim.domain.errors import DomainError
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
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


def test_sampling_flows_from_request_to_adapter_body() -> None:
    request = CompletionRequest(prompt="hello", max_tokens=64, temperature=0.7, top_p=0.9, top_k=40)
    gateway = OpenRouterGateway(
        FAKE_TEST_PROFILE,
        api_key=SecretStr("test-key"),
        base_url="https://example.test/v1",
    )
    body = gateway._body(request)  # pyright: ignore[reportPrivateUsage]
    assert body["temperature"] == 0.7
    assert body["top_p"] == 0.9
    assert body["top_k"] == 40
    assert body["model"] == "fake-echo"
    plain = CompletionRequest(prompt="hello")
    bare = gateway._body(plain)  # pyright: ignore[reportPrivateUsage]
    assert "temperature" not in bare and "top_p" not in bare and "top_k" not in bare


def test_fake_gateway_records_sampling_for_capture() -> None:
    async def _inner() -> None:
        gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
        gateway.route = lambda request: json.dumps({"ok": True})
        await gateway.complete(CompletionRequest(prompt="ping", temperature=0.5, top_k=10))
        sent = gateway.sent_requests[-1]
        assert sent.temperature == 0.5
        assert sent.top_k == 10
        assert sent.top_p is None

    asyncio.run(_inner())


def test_profile_revision_validation_and_secrets(client: ApiClient) -> None:
    made = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": "openrouter",
            "name": "Remote",
            "endpoint": "http://127.0.0.1:7143/v1",
            "credential_env": "WORLDSIM_TEST_KEY_ABSENT",
            "allow_local_endpoint": True,
        },
        headers={},
    )
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["has_credential"] is False
    connection_id = body["id"]

    os.environ["WORLDSIM_TEST_KEY_ABSENT"] = "secret-value"
    try:
        reread = client.get(f"/api/v1/settings/providers/{connection_id}", headers={})
        assert reread.json()["has_credential"] is True
        assert "secret-value" not in reread.text
    finally:
        del os.environ["WORLDSIM_TEST_KEY_ABSENT"]

    profile = client.post(
        f"/api/v1/settings/providers/{connection_id}/profiles",
        json={"model_id": "openrouter/auto", "temperature": 0.8, "top_k": 50},
        headers={},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["temperature"] == 0.8

    bad = client.post(
        f"/api/v1/settings/providers/{connection_id}/profiles",
        json={"model_id": "x", "mystery_param": 1.0},
        headers={},
    )
    assert bad.status_code == 422, bad.text
    out_of_range = client.post(
        f"/api/v1/settings/providers/{connection_id}/profiles",
        json={"model_id": "x", "temperature": 9.0},
        headers={},
    )
    assert out_of_range.status_code == 422, out_of_range.text


def test_endpoint_policy_blocks_dangerous_targets() -> None:
    blocked = [
        "http://169.254.169.254/latest",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "ftp://example.com/v1",
    ]
    for raw in blocked:
        try:
            validate_endpoint(raw, EndpointPolicy())
        except DomainError:
            continue
        raise AssertionError(f"endpoint accepted: {raw}")
    plain = "http://example.com/v1"
    try:
        validate_endpoint(plain, EndpointPolicy())
    except DomainError:
        pass
    else:
        raise AssertionError("plain http accepted without local allowance")
    loopback = validate_endpoint("http://127.0.0.1:11434/v1", EndpointPolicy(allow_local=True))
    assert loopback == "http://127.0.0.1:11434/v1"


def test_pinned_profile_resolves_from_created_snapshot_shape(client: ApiClient) -> None:
    """Regression: stories.create nests DraftAi under "art", not "ai".

    Resolution must read the section the writer emits, or every created
    story silently runs environment defaults.
    """
    connection = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": "fake",
            "name": "Demo",
            "endpoint": "http://127.0.0.1:7144/v1",
            "allow_local_endpoint": True,
        },
        headers={},
    ).json()
    profile = client.post(
        f"/api/v1/settings/providers/{connection['id']}/profiles",
        json={"model_id": "fake-echo", "temperature": 0.3},
        headers={},
    ).json()

    async def _setup() -> UUID:
        from test_stage1_api import _seed_two  # pyright: ignore[reportPrivateUsage]

        from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
        from worldsim.domain.time import utcnow

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                ids = await _seed_two()
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=ids["world"],
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            # Shape emitted by stories.create._snapshot_payload.
                            "art": {
                                "profile_id": profile["id"],
                                "profile_revision": profile["revision"],
                            },
                        },
                        content_hash="a05-created-shape",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
                await uow.commit()
                return ids["world"]
        finally:
            await engine.dispose()

    world_id = asyncio.run(_setup())

    async def _resolve() -> SamplingParams:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return await resolve_sampling(uow, world_id)
        finally:
            await engine.dispose()

    sampling = asyncio.run(_resolve())
    assert sampling.temperature == 0.3
    assert sampling.profile_id == profile["id"]


def test_preferences_versioned_and_probe_redacted(client: ApiClient) -> None:
    current = client.get("/api/v1/settings/preferences", headers={})
    assert current.status_code == 200, current.text
    assert current.json()["version"] == 0
    stale = client.patch(
        "/api/v1/settings/preferences",
        json={"gameplay": {"pacing": "brisk"}, "expected_version": 9},
        headers={},
    )
    assert stale.status_code == 409, stale.text
    saved = client.patch(
        "/api/v1/settings/preferences",
        json={
            "gameplay": {"pacing": "brisk", "autoplay_dwell": "fast"},
            "accessibility": {"font_scale": 112, "motion": "reduce"},
            "expected_version": 0,
        },
        headers={},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["version"] == 1
    assert body["gameplay"]["pacing"] == "brisk"
    bad = client.patch(
        "/api/v1/settings/preferences",
        json={"accessibility": {"font_scale": 500}, "expected_version": 1},
        headers={},
    )
    assert bad.status_code == 422, bad.text


def test_probe_shape_and_cache_scopes(client: ApiClient) -> None:
    made = client.post(
        "/api/v1/settings/providers",
        json={
            "adapter": "fake",
            "name": "Demo",
            "endpoint": "http://127.0.0.1:7145/v1",
            "allow_local_endpoint": True,
        },
        headers={},
    )
    assert made.status_code == 200, made.text
    probe = client.post(f"/api/v1/settings/providers/{made.json()['id']}/test", json={}, headers={})
    assert probe.status_code == 200, probe.text
    assert probe.json()["text_ready"] == "demo (scripted), never live"
    assert "tested_config_revision" in probe.json()

    caches = client.get("/api/v1/settings/cache", headers={})
    assert caches.status_code == 200, caches.text
    assert caches.json()[0]["scope"] == "image_derived"
    unknown = client.post("/api/v1/settings/cache/clear", json={"scope": "world_rows"}, headers={})
    assert unknown.status_code == 422, unknown.text
    cleared = client.post(
        "/api/v1/settings/cache/clear", json={"scope": "image_derived"}, headers={}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["removed"] >= 0

def test_created_story_executes_with_pinned_sampling(migrated_db: None) -> None:
    """Creation -> resolution -> execution stays connected.

    A story created with a profile pin advances through a recording
    gateway carrying the pin\u2019s temperature and cap; the resolved model
    stays on the pinned revision after the profile head moves; an
    unpinned story uses defaults.
    """
    seen: list[CompletionRequest] = []
    # Gateway model differs from the pinned row on purpose: the model
    # assertions below must come from the pin, not the injected gateway.
    gateway = FakeGateway(
        profile=FAKE_TEST_PROFILE.model_copy(update={"model_id": "gateway-env-model"})
    )

    def _route(request: CompletionRequest) -> str:
        seen.append(request)
        return ('{"family": "wait", "character_id": "00000000-0000-0000-0000-000000000000",'
            ' "snapshot_id": "00000000-0000-0000-0000-000000000000"}')

    gateway.route = _route
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )

    async def _ensure() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await ensure_builtin_presets(uow)
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(_ensure())
    with TestClient(app) as raw:
        api = ApiClient(raw)
        connection = api.post(
            "/api/v1/settings/providers",
            json={
                "adapter": "fake",
                "name": "Demo",
                "endpoint": "http://127.0.0.1:7144/v1",
                "allow_local_endpoint": True,
            },
            headers={},
        ).json()
        pin = api.post(
            f"/api/v1/settings/providers/{connection['id']}/profiles",
            json={"model_id": "fake-echo", "temperature": 0.2, "max_tokens": 4096},
            headers={},
        ).json()

        def _draft(ai: dict) -> str:
            created = api.post(
                "/api/v1/story-drafts",
                json={
                    "payload": {
                        "world": {"preset_id": WORLD_PRESET_ID, "preset_revision": 2},
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
                        "story": {"title": "Pin probe"},
                        "ai": ai,
                    },
                    "current_step": "review",
                },
                headers={},
            )
            assert created.status_code == 200, created.text
            return created.json()["id"]

        def _create(draft_id: str, key: str) -> str:
            created = api.post(
                "/api/v1/stories",
                json={"draft_id": draft_id, "expected_draft_version": 1},
                headers={"Idempotency-Key": key},
            )
            assert created.status_code == 200, created.text
            return created.json()["world_id"]

        def _advance(world_id: str, index: int) -> None:
            response = api.post(
                "/api/v1/stage1/advance",
                json={"world_id": world_id, "absolute_index": index},
                headers={"X-Worldsim-Role": "watcher"},
            )
            assert response.status_code == 200, response.text

        def _sampling(world_id: str) -> SamplingParams:
            async def _inner() -> SamplingParams:
                engine = create_engine(Settings())
                try:
                    async with create_unit_of_work(engine) as uow:
                        return await resolve_sampling(uow, UUID(world_id))
                finally:
                    await engine.dispose()

            return asyncio.run(_inner())

        pinned = _create(
            _draft(
                {
                    "art_source": "curated",
                    "profile_id": pin["id"],
                    "profile_revision": pin["revision"],
                }
            ),
            "pin-key",
        )
        setup = api.get(f"/api/v1/stories/{pinned}/setup", headers={}).json()
        assert setup["payload"]["art"]["profile_id"] == pin["id"]
        _advance(pinned, 1)
        assert seen, "expected recorded model requests"
        assert pin["model_id"] == "fake-echo"
        assert all(r.temperature == 0.2 for r in seen)
        assert all(r.max_tokens == 4096 for r in seen)
        resolved = _sampling(pinned)
        assert resolved.model_id == "fake-echo", (
            "runtime model must come from the pin, not the gateway"
        )
        assert resolved.profile_revision == pin["revision"]

        def _executed_models(world_id: str, index: int) -> list[str]:
            async def _inner() -> list[str]:
                from sqlalchemy import select as sa_select
                from sqlalchemy.ext.asyncio import AsyncSession

                from worldsim.application.orchestration.service import derive_run_id
                from worldsim.infrastructure.models.calls import ModelCallRow

                engine = create_engine(Settings())
                try:
                    async with AsyncSession(engine) as session:
                        rows = (
                            (
                                await session.execute(
                                    sa_select(ModelCallRow).where(
                                        ModelCallRow.phase_run_id
                                        == derive_run_id(UUID(world_id), index)
                                    )
                                )
                            )
                            .scalars()
                            .all()
                        )
                        return [str(row.result.get("model")) for row in rows]
                finally:
                    await engine.dispose()

            return asyncio.run(_inner())

        executed = _executed_models(pinned, 1)
        assert executed, "expected audited model calls for the pinned run"
        assert all(model == "fake-echo" for model in executed), (
            "executed model must come from the pin, not the gateway: "
            f"{executed}"
        )

        moved = api.post(
            f"/api/v1/settings/providers/{connection['id']}/profiles",
            json={"model_id": "fake-echo-2", "temperature": 0.9},
            headers={},
        ).json()
        assert moved["revision"] == pin["revision"] + 1
        seen.clear()
        _advance(pinned, 2)
        assert seen, "expected recorded model requests"
        assert all(r.temperature == 0.2 for r in seen)
        assert all(r.max_tokens == 4096 for r in seen)
        moved_on = _sampling(pinned)
        assert moved_on.model_id == "fake-echo", (
            "selected model must stay pinned after the head moves"
        )
        assert moved_on.profile_revision == pin["revision"]
        assert moved_on.temperature == 0.2

        plain = _create(_draft({"art_source": "curated"}), "plain-key")
        seen.clear()
        _advance(plain, 1)
        assert seen, "expected recorded model requests"
        assert all(r.temperature is None for r in seen)
        assert all(r.max_tokens == 512 for r in seen)


def test_pinned_profile_selects_gateway_model_on_wire(
    migrated_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pinned sampling must select the runtime gateway, not just resolve.

    Environment model A against pinned model B through the real
    selection path: the adapter HTTP transport is intercepted, pinned
    and unpinned stories advance interleaved, and every outbound body
    must carry its own story model plus pinned sampling. After the
    profile head moves to C, the pinned story still sends B. Audit rows
    record the requested pin next to the executed model and provider.
    """
    from uuid import uuid4

    import httpx

    from worldsim.application.orchestration.service import derive_run_id
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.settings.resolution import PinnedRuntime
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.application.transactions.canonical import CanonicalTransaction
    from worldsim.domain.settings import (
        AdapterKind,
        ProviderConnection,
        ProviderProfileRevision,
    )
    from worldsim.infrastructure.model_gateway.selection import (
        gateway_for_pin,
        gateways_for_settings,
    )
    from worldsim.infrastructure.models.calls import ModelCallRow, ModelProfileRow
    from worldsim.infrastructure.settings import ProviderSettings

    monkeypatch.setenv("WORLDSIM_TEST_PIN_KEY", "pin-secret")
    bodies: list[dict[str, object]] = []

    wait_text = (
        '{"family": "wait",'
        ' "character_id": "00000000-0000-0000-0000-000000000000",'
        ' "snapshot_id": "00000000-0000-0000-0000-000000000000"}'
    )
    beats_text = json.dumps([{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}])

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        body = json.loads(request.content.decode("utf-8"))
        bodies.append(body)
        system = ""
        for message in body.get("messages", []):
            if isinstance(message, dict) and message.get("role") == "system":
                system = str(message.get("content", ""))
        text = beats_text if "You narrate" in system else wait_text
        return httpx.Response(
            200,
            json={
                "id": "mock-call",
                "model": body.get("model", "unknown"),
                "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    settings = Settings(
        provider=ProviderSettings(
            active_profile="openrouter",
            openrouter_api_key=SecretStr("test-key"),
            openrouter_model="env-model-A",
        )
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    env_gateways, env_profiles = gateways_for_settings(settings, None, client=client)

    async def _inner() -> None:
        from test_stage1_api import _seed_two  # pyright: ignore[reportPrivateUsage]

        from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
        from worldsim.domain.time import utcnow
        from worldsim.infrastructure.tracing.langsmith import NullExporter

        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731

            def _for_role(role: str):
                return env_gateways[role]

            def _for_pin(role: str, pin: PinnedRuntime):
                return gateway_for_pin(role, pin.profile, pin.connection, client=client)

            orch = Stage1Orchestrator(
                factory,
                CanonicalTransaction(factory),
                TaskService(factory),
                TraceService(factory, NullExporter()),
                _for_role,
                env_profiles,
                pin_gateway_factory=_for_pin,
            )

            pinned_ids = await _seed_two()
            plain_ids = await _seed_two()
            pinned_world = pinned_ids["world"]
            plain_world = plain_ids["world"]

            connection = ProviderConnection(
                id=uuid4(),
                adapter=AdapterKind.OPENROUTER,
                name="Pin",
                endpoint="http://127.0.0.1:7144/v1",
                credential_env="WORLDSIM_TEST_PIN_KEY",
                allow_local_endpoint=True,
            )
            revision_b = ProviderProfileRevision(
                id=uuid4(),
                connection_id=connection.id,
                revision=1,
                model_id="pinned-model-B",
                temperature=0.2,
                max_tokens=4096,
                capabilities=["chat", "json_mode", "temperature", "top_p", "top_k"],
            )
            async with create_unit_of_work(engine) as uow:
                await uow.settings.add_connection(connection)
                await uow.settings.add_profile(revision_b)
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=pinned_world,
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            "art": {
                                "profile_id": str(revision_b.id),
                                "profile_revision": 1,
                            },
                        },
                        content_hash="wire-pin",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
                await uow.commit()

            def _models() -> list[str]:
                return [str(body.get("model")) for body in bodies]

            await orch.advance_phase(pinned_world, 1)
            assert bodies, "expected outbound calls for the pinned story"
            assert all(model == "pinned-model-B" for model in _models()), _models()
            assert all(body.get("temperature") == 0.2 for body in bodies)
            assert all(body.get("max_tokens") == 4096 for body in bodies)
            bodies.clear()

            await orch.advance_phase(plain_world, 1)
            assert bodies, "expected outbound calls for the unpinned story"
            assert all(model == "env-model-A" for model in _models()), _models()
            assert all("temperature" not in body for body in bodies)
            assert all(body.get("max_tokens") == 512 for body in bodies)
            bodies.clear()

            revision_c = revision_b.model_copy(
                update={"revision": 2, "model_id": "pinned-model-C", "temperature": 0.9}
            )
            async with create_unit_of_work(engine) as uow:
                await uow.settings.add_profile(revision_c)
                await uow.commit()

            await orch.advance_phase(pinned_world, 2)
            assert bodies, "expected outbound calls after the head moves"
            assert all(model == "pinned-model-B" for model in _models()), _models()
            assert all(body.get("temperature") == 0.2 for body in bodies)
            bodies.clear()

            await orch.advance_phase(plain_world, 2)
            assert bodies, "expected outbound calls for the unpinned story"
            assert all(model == "env-model-A" for model in _models()), _models()
            bodies.clear()

            assert env_gateways["narrator"].profile.model_id == "env-model-A"
            assert env_profiles["narrator"].model_id == "env-model-A"

            from sqlalchemy import select as sa_select
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(engine) as session:
                pinned_rows = (
                    await session.execute(
                        sa_select(ModelCallRow).where(
                            ModelCallRow.phase_run_id == derive_run_id(pinned_world, 2)
                        )
                    )
                ).scalars().all()
                assert pinned_rows, "expected audited calls for the pinned run"
                for row in pinned_rows:
                    sampling = row.request["sampling"]
                    assert sampling["model_id"] == "pinned-model-B"
                    assert sampling["pin_profile_id"] == str(revision_b.id)
                    assert sampling["pin_profile_revision"] == 1
                    assert row.result["model"] == "pinned-model-B"
                profile_row = await session.get(
                    ModelProfileRow, (pinned_rows[0].profile_name, pinned_rows[0].profile_version)
                )
                assert profile_row is not None
                assert profile_row.adapter == "openrouter"
                assert profile_row.model_id == "pinned-model-B"
                plain_rows = (
                    await session.execute(
                        sa_select(ModelCallRow).where(
                            ModelCallRow.phase_run_id == derive_run_id(plain_world, 2)
                        )
                    )
                ).scalars().all()
                assert plain_rows, "expected audited calls for the unpinned run"
                for row in plain_rows:
                    sampling = row.request["sampling"]
                    assert sampling["model_id"] == "env-model-A"
                    assert "pin_profile_id" not in sampling
                    assert row.result["model"] == "env-model-A"
        finally:
            await engine.dispose()
        await client.aclose()

    asyncio.run(_inner())


def test_explicit_pin_missing_revision_fails_closed(migrated_db: None) -> None:
    """A setup naming a nonexistent pin revision must fail before generation.

    Broken explicit pins are actionable errors, never silent environment
    fallback: advance raises 409 and the environment provider sees zero
    calls, because resolution runs before probing or generation.
    """
    from uuid import uuid4

    from test_stage1_orchestration import _orchestrator, _role_gateways, _seed

    from worldsim.domain.errors import ErrorCode
    from worldsim.domain.settings import (
        AdapterKind,
        ProviderConnection,
        ProviderProfileRevision,
    )
    from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
    from worldsim.domain.time import utcnow

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        orch = _orchestrator(gateways)
        engine = create_engine(Settings())
        try:
            connection = ProviderConnection(
                id=uuid4(),
                adapter=AdapterKind.FAKE,
                name="Pin",
                endpoint="http://127.0.0.1:7144/v1",
                allow_local_endpoint=True,
            )
            revision = ProviderProfileRevision(
                id=uuid4(),
                connection_id=connection.id,
                revision=1,
                model_id="pinned-fake",
            )
            async with create_unit_of_work(engine) as uow:
                await uow.settings.add_connection(connection)
                await uow.settings.add_profile(revision)
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=ids["world"],
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            "art": {
                                "profile_id": str(revision.id),
                                "profile_revision": 99,
                            },
                        },
                        content_hash="broken-pin-revision",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
                await uow.commit()
            with pytest.raises(DomainError) as caught:
                await orch.advance_phase(ids["world"], 1)
            assert caught.value.code is ErrorCode.PRECONDITION_FAILED
            assert caught.value.details["profile_revision"] == 99
            for gateway in gateways.values():
                assert gateway.sent_requests == []
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_explicit_pin_missing_connection_fails_closed(migrated_db: None) -> None:
    """A pin whose provider connection is gone must fail before generation.

    Like a missing revision, an unresolvable connection is an actionable
    error, never silent environment fallback: advance raises 409 and the
    environment provider sees zero calls.
    """
    from unittest import mock
    from uuid import uuid4

    from test_stage1_orchestration import _orchestrator, _role_gateways, _seed

    from worldsim.domain.errors import ErrorCode
    from worldsim.domain.settings import (
        AdapterKind,
        ProviderConnection,
        ProviderProfileRevision,
    )
    from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
    from worldsim.domain.time import utcnow
    from worldsim.infrastructure.repositories.settings import SqlAlchemySettingsRepository

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        orch = _orchestrator(gateways)
        engine = create_engine(Settings())
        try:
            connection = ProviderConnection(
                id=uuid4(),
                adapter=AdapterKind.FAKE,
                name="Pin",
                endpoint="http://127.0.0.1:7144/v1",
                allow_local_endpoint=True,
            )
            revision = ProviderProfileRevision(
                id=uuid4(),
                connection_id=connection.id,
                revision=1,
                model_id="pinned-fake",
            )
            async with create_unit_of_work(engine) as uow:
                await uow.settings.add_connection(connection)
                await uow.settings.add_profile(revision)
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=ids["world"],
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            "art": {
                                "profile_id": str(revision.id),
                                "profile_revision": 1,
                            },
                        },
                        content_hash="broken-pin-connection",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
                await uow.commit()

            real_get_connection = SqlAlchemySettingsRepository.get_connection

            async def _gone(self, connection_id):
                if connection_id == connection.id:
                    raise DomainError(ErrorCode.NOT_FOUND, "connection removed")
                return await real_get_connection(self, connection_id)

            with mock.patch.object(
                SqlAlchemySettingsRepository, "get_connection", _gone
            ):
                with pytest.raises(DomainError) as caught:
                    await orch.advance_phase(ids["world"], 1)
            assert caught.value.code is ErrorCode.PRECONDITION_FAILED
            assert caught.value.details["connection_id"] == str(connection.id)
            for gateway in gateways.values():
                assert gateway.sent_requests == []
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_broken_pin_advance_leaves_no_open_run(migrated_db: None) -> None:
    """A rejected fresh advance must not leave an orphan open run.

    Runtime resolution runs before admission: the broken pin raises
    before any run row exists, so reconciliation sees no stale open
    run and a later retry starts clean.
    """
    from uuid import uuid4

    from test_stage1_orchestration import _orchestrator, _role_gateways, _seed

    from worldsim.application.orchestration.service import derive_run_id
    from worldsim.domain.errors import ErrorCode
    from worldsim.domain.settings import (
        AdapterKind,
        ProviderConnection,
        ProviderProfileRevision,
    )
    from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
    from worldsim.domain.time import utcnow

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        orch = _orchestrator(gateways)
        engine = create_engine(Settings())
        try:
            connection = ProviderConnection(
                id=uuid4(),
                adapter=AdapterKind.FAKE,
                name="Pin",
                endpoint="http://127.0.0.1:7144/v1",
                allow_local_endpoint=True,
            )
            revision = ProviderProfileRevision(
                id=uuid4(),
                connection_id=connection.id,
                revision=1,
                model_id="pinned-fake",
            )
            async with create_unit_of_work(engine) as uow:
                await uow.settings.add_connection(connection)
                await uow.settings.add_profile(revision)
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=ids["world"],
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            "art": {
                                "profile_id": str(revision.id),
                                "profile_revision": 99,
                            },
                        },
                        content_hash="broken-pin-no-orphan",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
                await uow.commit()
            run_id = derive_run_id(ids["world"], 1)
            with pytest.raises(DomainError) as caught:
                await orch.advance_phase(ids["world"], 1)
            assert caught.value.code is ErrorCode.PRECONDITION_FAILED
            async with create_unit_of_work(engine) as uow:
                assert await uow.phases.find_open_run(ids["world"]) is None
                with pytest.raises(DomainError):
                    await uow.phases.get_run(run_id)
            for gateway in gateways.values():
                assert gateway.sent_requests == []
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_failed_probe_leaves_no_run_and_retry_succeeds(migrated_db: None) -> None:
    """Provider preflight runs before admission: a down provider leaves
    no run row, and the same index advances cleanly once it recovers.
    """
    from unittest import mock

    from test_stage1_orchestration import _orchestrator, _role_gateways, _seed

    from worldsim.application.orchestration.service import derive_run_id
    from worldsim.application.ports.model_gateway import ProbeResult
    from worldsim.domain.errors import ErrorCode

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        orch = _orchestrator(gateways)
        engine = create_engine(Settings())
        try:
            run_id = derive_run_id(ids["world"], 1)
            dead = mock.AsyncMock(
                return_value=ProbeResult(
                    ok=False, profile="fake", latency_ms=0, detail="provider down"
                )
            )
            with mock.patch.object(gateways["narrator"], "probe", dead):
                with pytest.raises(DomainError) as caught:
                    await orch.advance_phase(ids["world"], 1)
            assert caught.value.code is ErrorCode.PRECONDITION_FAILED
            async with create_unit_of_work(engine) as uow:
                assert await uow.phases.find_open_run(ids["world"]) is None
                with pytest.raises(DomainError):
                    await uow.phases.get_run(run_id)
            report = await orch.advance_phase(ids["world"], 1)
            assert report.run_id == run_id
            assert not report.duplicate
            async with create_unit_of_work(engine) as uow:
                run = await uow.phases.get_run(run_id)
                assert run.state.value == "completed"
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_failed_resume_preserves_open_run(migrated_db: None) -> None:
    """A resume blocked by configuration keeps the existing open run.

    The admitted run is committed progress: a later preflight failure
    must neither delete it nor advance its state, so fixing the
    configuration can resume the same run.
    """
    from uuid import uuid4

    from test_stage1_orchestration import _orchestrator, _role_gateways, _seed

    from worldsim.domain.errors import ErrorCode
    from worldsim.domain.settings import (
        AdapterKind,
        ProviderConnection,
        ProviderProfileRevision,
    )
    from worldsim.domain.stories import SetupProvenance, StoryInitialSetup
    from worldsim.domain.time import utcnow

    async def _inner() -> None:
        ids = await _seed()
        gateways = _role_gateways(ids)
        orch = _orchestrator(gateways)
        engine = create_engine(Settings())
        try:
            admitted = await orch._admit_run(ids["world"], 1)  # pyright: ignore[reportPrivateUsage]
            connection = ProviderConnection(
                id=uuid4(),
                adapter=AdapterKind.FAKE,
                name="Pin",
                endpoint="http://127.0.0.1:7144/v1",
                allow_local_endpoint=True,
            )
            revision = ProviderProfileRevision(
                id=uuid4(),
                connection_id=connection.id,
                revision=1,
                model_id="pinned-fake",
            )
            async with create_unit_of_work(engine) as uow:
                await uow.settings.add_connection(connection)
                await uow.settings.add_profile(revision)
                await uow.stories.put_setup(
                    StoryInitialSetup(
                        world_id=ids["world"],
                        payload={
                            "schema_version": 1,
                            "provenance": "created",
                            "art": {
                                "profile_id": str(revision.id),
                                "profile_revision": 99,
                            },
                        },
                        content_hash="broken-pin-preserve-run",
                        created_at=utcnow(),
                        provenance=SetupProvenance.CREATED,
                    )
                )
                await uow.commit()
            with pytest.raises(DomainError) as caught:
                await orch.advance_phase(ids["world"], 1)
            assert caught.value.code is ErrorCode.PRECONDITION_FAILED
            async with create_unit_of_work(engine) as uow:
                kept = await uow.phases.find_open_run(ids["world"])
                assert kept is not None
                assert kept.id == admitted.id
                assert kept.state.value == admitted.state.value
            for gateway in gateways.values():
                assert gateway.sent_requests == []
        finally:
            await engine.dispose()

    asyncio.run(_inner())
