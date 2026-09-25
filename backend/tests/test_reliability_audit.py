"""Reliability-baseline audit surface (owned by REL-BASE-001).

Covers the read-only observability the latency baseline depends on:
per-call latency/error/task/attempt/budget/pin attribution on the
watcher-only model-runs view, failed-call token preservation, and the
admission/execution timing split on the advance endpoint. Prompts,
models, budgets, and retry behavior are unchanged; these tests pin the
measurement contract only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient, _advance, _route_for, _seed_two, _watcher
from test_trace_audit import (
    PROFILE,
    _engine,
    _factory_for,
    _seeded_world,
    _spec,
)

from worldsim.application.execution import guarded, guarded_timed, phase_scope
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelUnavailableError,
)
from worldsim.application.tracing.service import TraceService
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import NullExporter
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


@pytest.fixture
def api(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_failed_call_preserves_usage_and_attempts(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            gateway = FakeGateway(profile=PROFILE)
            gateway.enqueue_error(
                ModelUnavailableError(
                    "provider down",
                    detail={
                        "http_status": 503,
                        "usage": {"prompt_tokens": 9, "completion_tokens": 3},
                        "attempts": [{"attempt": 1, "error": "ModelUnavailableError"}],
                    },
                )
            )
            service = TraceService(_factory_for(engine), NullExporter())
            spec = _spec(world_id)
            with pytest.raises(ModelUnavailableError):
                await service.run_call(spec, gateway, CompletionRequest(prompt="Narrate the tick."))
            async with create_unit_of_work(engine) as uow:
                calls = await uow.traces.list_for_phase_run(spec.phase_run_id)
                assert len(calls) == 1
                stored = calls[0]
                assert stored.status == "failed"
                assert stored.error_code == "unavailable"
                assert stored.prompt_tokens == 9
                assert stored.completion_tokens == 3
                attempts = await uow.traces.get_call_attempts(stored.id)
                assert attempts == [{"attempt": 1, "error": "ModelUnavailableError"}]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_call_carries_transmitted_budget_and_pin(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            gateway = FakeGateway(profile=PROFILE)
            gateway.enqueue_text("Dawn settles.", 12, 7)
            service = TraceService(_factory_for(engine), NullExporter())
            spec = replace(_spec(world_id), pin_profile_id="pin-1", pin_profile_revision=4)
            traced = await service.run_call(
                spec, gateway, CompletionRequest(prompt="Narrate the tick.", max_tokens=64)
            )
            async with create_unit_of_work(engine) as uow:
                call = await uow.traces.get_call(traced.call_id)
                assert call.max_tokens == 64
                assert call.pin_profile_id == "pin-1"
                assert call.pin_profile_revision == 4
                assert call.latency_ms >= 0
                assert call.error_code is None
                assert await uow.traces.get_call_attempts(traced.call_id) == []
                manifest = await uow.traces.get_manifest(traced.call_id)
                assert manifest.budgets == {"sections": 4}
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_guarded_timed_matches_guarded(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            factory = _factory_for(engine)

            async def _ok() -> str:
                return "ok"

            assert await guarded(factory, world_id, phase_scope(501), "owner-a", None, _ok) == "ok"
            result, admission_ms, execution_ms = await guarded_timed(
                factory, world_id, phase_scope(502), "owner-b", None, _ok
            )
            assert result == "ok"
            assert admission_ms >= 0
            assert execution_ms >= 0

            async def _invalid() -> str:
                raise DomainError(ErrorCode.VALIDATION_FAILED, "bad input")

            with pytest.raises(DomainError):
                await guarded(factory, world_id, phase_scope(503), "owner-c", None, _invalid)
            with pytest.raises(DomainError):
                await guarded_timed(factory, world_id, phase_scope(504), "owner-d", None, _invalid)
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_advance_reports_timing_headers(api: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    assert int(report.headers["x-worldsim-slot-claim-ms"]) >= 0
    assert int(report.headers["x-worldsim-execution-ms"]) >= 0


def test_model_runs_carry_baseline_attribution(api: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    run_id = report.json()["run_id"]
    runs = client.get(
        "/api/v1/stage1/model-runs", params={"phase_run_id": run_id}, headers=_watcher()
    )
    assert runs.status_code == 200
    views = runs.json()
    assert len(views) >= 2
    roles = {view["role"] for view in views}
    assert "director" in roles
    assert any(role.startswith("character") for role in roles)
    # Attribution holds even for calls stuck outside the failure taxonomy
    # (the scripted fake leaves the director call 'started'): the baseline
    # must surface unfinished calls, not hide them.
    assert any(view["status"] == "succeeded" for view in views)
    for view in views:
        assert view["status"] in ("started", "succeeded", "failed")
        assert view["latency_ms"] >= 0
        assert view["task_run_id"] is not None
        assert isinstance(view["attempts"], list)
        assert isinstance(view["budgets"], dict)
        assert view["max_tokens"] is not None
        assert isinstance(view["reasoning_tokens"], int)
        assert "finish_reason" in view
        assert "content_type" in view
        assert "content_length" in view
        assert "reasoning_only" in view
        if view["status"] == "succeeded":
            assert view["error_code"] is None
            assert view["reasoning_only"] is False


def test_failed_character_call_exports_failure_layer(api: tuple[ApiClient, FakeGateway]) -> None:
    """A reasoning-exhausted provider failure exports its exact layer.

    finish_reason 'length' plus reasoning_only True distinguishes
    reasoning exhaustion from truncated JSON reaching validation; usage
    tokens (including reasoning) are preserved on the failed call. The
    phase still commits through fallback decisions.
    """
    client, gateway = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    base = _route_for(ids, snapshots)

    def _route(request):  # type: ignore[no-untyped-def]
        if "You decide" in (request.system or "") and "Wren" in request.prompt:
            raise ModelUnavailableError(
                "reasoning exhausted",
                detail={
                    "http_status": 200,
                    "finish_reason": "length",
                    "content_type": "NoneType",
                    "content_length": None,
                    "reasoning_only": True,
                    "usage": {
                        "prompt_tokens": 2805,
                        "reasoning_tokens": 512,
                        "completion_tokens": 512,
                    },
                },
            )
        return base(request)

    gateway.route = _route
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    run_id = report.json()["run_id"]
    runs = client.get(
        "/api/v1/stage1/model-runs", params={"phase_run_id": run_id}, headers=_watcher()
    )
    assert runs.status_code == 200
    decisions = [view for view in runs.json() if view["role"] == "character_decision"]
    assert len(decisions) >= 1
    failed = next(view for view in decisions if view["status"] == "failed")
    assert failed["error_code"] == "unavailable"
    assert failed["finish_reason"] == "length"
    assert failed["reasoning_only"] is True
    assert failed["reasoning_tokens"] == 512
    assert failed["prompt_tokens"] == 2805
    assert failed["completion_tokens"] == 512
    assert failed["content_type"] == "NoneType"
    assert failed["content_length"] is None
