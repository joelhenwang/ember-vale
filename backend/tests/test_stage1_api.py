"""Stage 1 API perspective and command checks (owned by S1-API-001)."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from worldsim.application.ports.model_gateway import CompletionRequest, ModelUnavailableError
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.ids import (
    derive_attempt_id,
    derive_intent_id,
    derive_reaction_id,
    new_card_id,
    new_character_id,
    new_location_id,
    new_world_id,
)
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"


class ApiClient:
    def __init__(self, raw: TestClient) -> None:
        self._raw = raw

    def _raw_any(self) -> Any:
        return self._raw

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().get(url, **kwargs))

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().post(url, **kwargs))

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().patch(url, **kwargs))

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return cast(httpx.Response, self._raw_any().delete(url, **kwargs))


@pytest.fixture
def api(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway, dict[str, UUID]]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(),
        seed_dir=SEED_DIR,
        migrations_dir=MIGRATIONS,
        gateway_factory=lambda: gateway,
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway, {}


async def _seed_two() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="Api", seed_version="s1-test"))
            hearth, market = new_location_id(), new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            await uow.locations.add(Location(id=market, world_id=wid, name="Market"))
            wren, ash = new_character_id(), new_character_id()
            for cid, name, place in ((wren, "Wren", hearth), (ash, "Ash", market)):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name, version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=place,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.versions.ensure(wid, wid, "world")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def _route_for(ids: dict[str, UUID], snapshots: dict[int, UUID]):
    def _route(request: CompletionRequest) -> str | None:
        prompt, system = request.prompt, request.system or ""
        if "You narrate" in system:
            return json.dumps([{"text": "The phase passes.", "cited_fact_keys": ["attempt:wait"]}])
        if "You resolve" in system:
            return json.dumps(
                {
                    "outcome": "success",
                    "effects": [
                        {
                            "schema_version": 1,
                            "affected_ids": [str(ids["wren"])],
                            "expected_versions": {str(ids["wren"]): 0},
                            "effect_type": "record_observation",
                            "observer_character_id": str(ids["wren"]),
                            "facts": [{"key": "greeting", "value": "dawn patrol"}],
                        }
                    ],
                    "rationale": "Wren hears the call.",
                }
            )
        snapshot = snapshots.get(1, next(iter(snapshots.values())) if snapshots else uuid.uuid4())
        if "You react" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "observe",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": str(snapshot),
                        "focus": "Ash",
                    }
                )
            return json.dumps(
                {"family": "wait", "character_id": str(ids["ash"]), "snapshot_id": str(snapshot)}
            )
        if "You decide" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "wait",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": str(snapshot),
                    }
                )
            if "Ash" in prompt:
                return json.dumps(
                    {
                        "family": "wait",
                        "character_id": str(ids["ash"]),
                        "snapshot_id": str(snapshot),
                    }
                )
        return None

    return _route


def _watcher() -> dict[str, str]:
    return {"X-Worldsim-Role": "watcher"}


def _player(character: UUID) -> dict[str, str]:
    return {"X-Worldsim-Role": "player", "X-Worldsim-Character": str(character)}


def _advance(
    client: ApiClient,
    world: UUID,
    index: int,
    player_intents: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"world_id": str(world), "absolute_index": index}
    if player_intents:
        body["player_intents"] = player_intents
    return client.post("/api/v1/stage1/advance", json=body, headers=headers or _watcher())


def test_watcher_and_player_views_differ(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    assert report.json()["duplicate"] is False

    run_id = report.json()["run_id"]
    watcher_scenes = client.get(
        "/api/v1/stage1/scenes", params={"phase_run_id": run_id}, headers=_watcher()
    )
    assert watcher_scenes.status_code == 200
    assert len(watcher_scenes.json()) == 2

    wren_scenes = client.get(
        "/api/v1/stage1/scenes", params={"phase_run_id": run_id}, headers=_player(ids["wren"])
    )
    assert wren_scenes.status_code == 200
    assert len(wren_scenes.json()) == 1

    ash_scene_id = next(
        s["id"] for s in watcher_scenes.json() if s["id"] != wren_scenes.json()[0]["id"]
    )
    forbidden = client.get(f"/api/v1/stage1/scenes/{ash_scene_id}", headers=_player(ids["wren"]))
    assert forbidden.status_code == 403


def test_player_intent_detail_scoped(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    snapshot = snapshots[1]
    player = {
        str(ids["ash"]): {
            "family": "communicate",
            "character_id": str(ids["ash"]),
            "snapshot_id": str(snapshot),
            "target_character_id": str(ids["wren"]),
            "topic": "dawn patrol",
        }
    }
    report = _advance(client, ids["world"], 1, player, _player(ids["ash"]))
    assert report.status_code == 200, report.text
    scene_id = report.json()["scenes"][0]["scene_id"]

    wren_view = client.get(f"/api/v1/stage1/scenes/{scene_id}", headers=_player(ids["wren"]))
    assert wren_view.status_code == 200
    intents = {i["author_character_id"]: i for i in wren_view.json()["intents"]}
    assert intents[str(ids["wren"])]["detail"] is not None
    assert intents[str(ids["ash"])]["detail"] is None

    watcher_view = client.get(f"/api/v1/stage1/scenes/{scene_id}", headers=_watcher())
    watcher_intents = {i["author_character_id"]: i for i in watcher_view.json()["intents"]}
    assert watcher_intents[str(ids["ash"])]["detail"]["topic"] == "dawn patrol"


def test_model_runs_watcher_only(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    report = _advance(client, ids["world"], 1)
    run_id = report.json()["run_id"]

    forbidden = client.get(
        "/api/v1/stage1/model-runs", params={"phase_run_id": run_id}, headers=_player(ids["wren"])
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        "/api/v1/stage1/model-runs", params={"phase_run_id": run_id}, headers=_watcher()
    )
    assert allowed.status_code == 200
    assert len(allowed.json()) >= 2
    assert all("rendered_hash" in call for call in allowed.json())


def test_character_card_scoped(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, _gateway, _ = api
    ids = asyncio.run(_seed_two())

    watcher = client.get(f"/api/v1/stage1/characters/{ids['wren']}", headers=_watcher())
    assert watcher.json()["card"] is not None

    other = client.get(f"/api/v1/stage1/characters/{ids['ash']}", headers=_player(ids["wren"]))
    assert other.json()["card"] is None
    assert other.json()["name"] == "Ash"

    own = client.get(f"/api/v1/stage1/characters/{ids['wren']}", headers=_player(ids["wren"]))
    assert own.json()["card"] is not None


def test_duplicate_and_stale_advance_stable(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    first = _advance(client, ids["world"], 1)
    second = _advance(client, ids["world"], 1)
    assert second.json()["duplicate"] is True
    assert [s["event_id"] for s in second.json()["scenes"]] == [
        s["event_id"] for s in first.json()["scenes"]
    ]

    gap = _advance(client, ids["world"], 5)
    assert gap.status_code == 422
    gap_again = _advance(client, ids["world"], 5)
    assert gap_again.status_code == 422
    assert gap_again.json()["error"]["code"] == gap.json()["error"]["code"]


def test_pause_resume_commands(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    run_id = str(derive_run_id(ids["world"], 1))
    engine = create_engine(Settings())
    try:
        from worldsim.domain.phases import PhaseRun

        async def _create() -> None:
            async with create_unit_of_work(engine) as uow:
                await uow.phases.create_run(
                    PhaseRun(id=UUID(run_id), world_id=ids["world"], absolute_index=1)
                )
                await uow.commit()

        asyncio.run(_create())
    finally:
        asyncio.run(engine.dispose())
    paused = client.post("/api/v1/stage1/pause", json={"run_id": run_id}, headers=_watcher())
    assert paused.status_code == 200
    blocked = _advance(client, ids["world"], 1)
    assert blocked.status_code == 409
    resumed = client.post("/api/v1/stage1/resume", json={"run_id": run_id}, headers=_watcher())
    assert resumed.status_code == 200
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200


def test_event_cursor_reconnects(api: tuple[ApiClient, FakeGateway, dict[str, UUID]]) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)
    _advance(client, ids["world"], 1)
    first = client.get("/api/v1/world/events", params={"after": 0, "limit": 1}, headers=_watcher())
    assert first.status_code == 200
    cursor = first.json()["next_after"]
    second = client.get(
        "/api/v1/world/events", params={"after": cursor, "limit": 50}, headers=_watcher()
    )
    full = client.get("/api/v1/world/events", params={"after": 0, "limit": 50}, headers=_watcher())
    assert [e["sequence"] for e in second.json()["entries"]] == [
        e["sequence"] for e in full.json()["entries"] if e["sequence"] > cursor
    ]


def test_ts_client_current() -> None:
    result = subprocess.run(
        [sys.executable, "backend/scripts/gen_ts_client.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


MARKET_ANSWER = "The Market holds stalls, wind, and trade."


async def _seed_two_at_hearth() -> dict[str, UUID]:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            wid = new_world_id()
            await uow.worlds.add(World(id=wid, name="ApiSpeech", seed_version="s1-test"))
            hearth = new_location_id()
            await uow.locations.add(Location(id=hearth, world_id=wid, name="Hearth"))
            wren, ash = new_character_id(), new_character_id()
            for cid, name in ((wren, "Wren"), (ash, "Ash")):
                await uow.characters.add_identity(cid, wid, name)
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name=name, version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name=name,
                        card_version=1,
                        location_id=hearth,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
            await uow.versions.ensure(wid, wid, "world")
            await uow.commit()
            return {"world": wid, "wren": wren, "ash": ash}
    finally:
        await engine.dispose()


def _snapshots(ids: dict[str, UUID]) -> dict[int, UUID]:
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    return {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}


def _speech_route(ids: dict[str, UUID], snapshots: dict[int, UUID], narrator: str = "speak"):
    """Ash answers Wren; the narrator voices the committed answer."""

    def _route(request: CompletionRequest) -> Any:
        prompt, system = request.prompt, request.system or ""
        snapshot = snapshots[1]
        if "You decide" in system:
            if "Wren" in prompt:
                return json.dumps(
                    {
                        "family": "communicate",
                        "character_id": str(ids["wren"]),
                        "snapshot_id": str(snapshot),
                        "target_character_id": str(ids["ash"]),
                        "topic": "Ask Ash what the Market holds today.",
                    }
                )
            return json.dumps(
                {
                    "family": "wait",
                    "character_id": str(ids["ash"]),
                    "snapshot_id": str(snapshot),
                }
            )
        if "You react" in system:
            if "Wren says to Ash" in prompt:
                return json.dumps(
                    {
                        "family": "communicate",
                        "character_id": str(ids["ash"]),
                        "snapshot_id": str(snapshot),
                        "target_character_id": str(ids["wren"]),
                        "topic": f'"{MARKET_ANSWER}"',
                    }
                )
            return json.dumps(
                {
                    "family": "wait",
                    "character_id": str(ids["wren"]),
                    "snapshot_id": str(snapshot),
                }
            )
        if "You resolve" in system:
            return json.dumps(
                {"outcome": "success", "effects": [], "rationale": "The question is heard."}
            )
        if "You narrate" in system:
            if narrator == "outage":
                return ModelUnavailableError("provider down")
            key = re.search(r"reaction:[0-9a-f-]{36}", prompt).group(0)  # type: ignore[union-attr]
            return json.dumps(
                [
                    {
                        "speaker_id": str(ids["ash"]),
                        "kind": "dialogue",
                        "text": MARKET_ANSWER,
                        "cited_fact_keys": [key],
                    }
                ]
            )
        return None

    return _route


def _expected_reaction_key(ids: dict[str, UUID]) -> str:
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    run = derive_run_id(ids["world"], 1)
    snapshot = derive_snapshot_id(run)
    intent = derive_intent_id(ids["world"], snapshot, ids["wren"])
    attempt = derive_attempt_id(intent)
    return f"reaction:{derive_reaction_id(attempt, ids['ash'])}"


def _narration_beats(client: ApiClient, scene_id: str) -> Any:
    res = client.get(f"/api/v1/stage1/scenes/{scene_id}/narration", headers=_watcher())
    assert res.status_code == 200, res.text
    return res.json()


def _stored_citations(scene_id: str, event_id: str) -> Any:
    async def _read() -> Any:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                return await uow.scenes.narrations_for_event(UUID(event_id))
        finally:
            await engine.dispose()

    return asyncio.run(_read())


def test_committed_communication_narrated_with_attribution(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two_at_hearth())
    snapshots = _snapshots(ids)
    gateway.route = _speech_route(ids, snapshots)
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    assert report.json()["duplicate"] is False
    assert len(report.json()["scenes"]) == 1
    scene_id = report.json()["scenes"][0]["scene_id"]

    expected_key = _expected_reaction_key(ids)
    narrator_reqs = [
        r for r in gateway.sent_requests if "reaction:" in r.prompt and "Event " in r.prompt
    ]
    assert len(narrator_reqs) == 1
    assert expected_key in narrator_reqs[0].prompt
    assert "Ash" in narrator_reqs[0].prompt
    assert str(ids["ash"]) in narrator_reqs[0].prompt

    feed = client.get(
        "/api/v1/stage2/timeline",
        params={"world_id": str(ids["world"]), "after": 0, "limit": 20},
        headers=_watcher(),
    )
    assert feed.status_code == 200, feed.text
    snippets = [e["snippet"] for e in feed.json()["entries"] if e["snippet"]]
    assert any("Ash:" in s and MARKET_ANSWER in s for s in snippets)
    reaction_reqs = [r for r in gateway.sent_requests if "Known characters" in r.prompt]
    assert reaction_reqs, "roster missing from reaction prompt"
    assert str(ids["wren"]) in reaction_reqs[0].prompt
    assert str(ids["ash"]) in reaction_reqs[0].prompt

    beats = _narration_beats(client, scene_id)
    spoken = [b for b in beats if b["kind"] == "dialogue"]
    assert len(spoken) == 1
    assert spoken[0]["speaker_id"] == str(ids["ash"])
    assert spoken[0]["text"] == MARKET_ANSWER

    stored = _stored_citations(scene_id, spoken[0]["source_event_id"])
    cited = [b for b in stored if b.kind == "dialogue"]
    assert len(cited) == 1
    assert cited[0].cited_fact_keys == [expected_key]
    assert cited[0].speaker_id == ids["ash"]

    assert _narration_beats(client, scene_id) == beats
    dup = _advance(client, ids["world"], 1)
    assert dup.json()["duplicate"] is True
    assert _narration_beats(client, scene_id) == beats


def test_narrator_outage_keeps_attributed_answer(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    client, gateway, _ = api
    ids = asyncio.run(_seed_two_at_hearth())
    snapshots = _snapshots(ids)
    gateway.route = _speech_route(ids, snapshots, narrator="outage")
    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    scene_id = report.json()["scenes"][0]["scene_id"]

    expected_key = _expected_reaction_key(ids)
    beats = _narration_beats(client, scene_id)
    spoken = [b for b in beats if b["kind"] == "dialogue"]
    assert len(spoken) == 1
    assert spoken[0]["speaker_id"] == str(ids["ash"])
    assert spoken[0]["text"] == MARKET_ANSWER

    stored = _stored_citations(scene_id, spoken[0]["source_event_id"])
    cited = [b for b in stored if b.kind == "dialogue"]
    assert len(cited) == 1
    assert cited[0].cited_fact_keys == [expected_key]

    assert _narration_beats(client, scene_id) == beats
    dup = _advance(client, ids["world"], 1)
    assert dup.json()["duplicate"] is True
    assert _narration_beats(client, scene_id) == beats


def test_stale_player_submission_rejected_at_admission(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    """A grant change during preflight rejects the stale submission.

    Wren files a question, provider preflight holds, the grant moves to
    Ash, then preflight releases: admission must reject the Wren action
    with 403, commit nothing for Wren, and leave no orphan run behind,
    so the same index stays retryable for Ash.
    """
    import threading

    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
    from worldsim.application.ports.model_gateway import ProbeResult
    from worldsim.domain.errors import DomainError

    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    gateway.route = _route_for(ids, snapshots)

    selected = client.post(
        "/api/v1/stage2/roles/select",
        json={
            "world_id": str(ids["world"]),
            "role": "player",
            "character_id": str(ids["wren"]),
        },
        headers=_watcher(),
    )
    assert selected.status_code == 200, selected.text

    snapshot = snapshots[1]
    wren_question = {
        str(ids["wren"]): {
            "family": "communicate",
            "character_id": str(ids["wren"]),
            "snapshot_id": str(snapshot),
            "target_character_id": str(ids["ash"]),
            "topic": "dawn patrol",
        }
    }

    arrived = threading.Event()
    release = threading.Event()
    real_probe = gateway.probe
    probe_calls = {"count": 0}

    async def _held_probe() -> ProbeResult:
        probe_calls["count"] += 1
        if probe_calls["count"] == 1:
            arrived.set()
            await asyncio.to_thread(release.wait, 120)

        return await real_probe()

    gateway.probe = _held_probe  # type: ignore[method-assign]
    outcomes: dict[str, Any] = {}

    def _advance_in_thread() -> None:
        try:
            outcomes["response"] = _advance(
                client, ids["world"], 1, wren_question, _player(ids["wren"])
            )
        except Exception as exc:  # recorded for the verdict
            outcomes["error"] = exc

    thread = threading.Thread(target=_advance_in_thread)
    try:
        thread.start()
        assert arrived.wait(timeout=120), "advance never reached preflight"
        switched = client.post(
            "/api/v1/stage2/roles/select",
            json={
                "world_id": str(ids["world"]),
                "role": "player",
                "character_id": str(ids["ash"]),
            },
            headers=_watcher(),
        )
        assert switched.status_code == 200, switched.text
        release.set()
        thread.join(timeout=300)
        assert not thread.is_alive(), "stale advance hung"
    finally:
        release.set()
        gateway.probe = real_probe  # type: ignore[method-assign]

    assert "error" not in outcomes, outcomes.get("error")
    rejected = outcomes["response"]
    assert rejected.status_code == 403, rejected.text
    assert rejected.json()["error"]["code"] == "FORBIDDEN"
    assert "stale" in rejected.json()["error"]["message"].lower()

    run_id = derive_run_id(ids["world"], 1)

    async def _inspect() -> dict[str, Any]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                events = await uow.events.count_events(ids["world"])
                open_run = await uow.phases.find_open_run(ids["world"])
                try:
                    await uow.phases.get_run(run_id)
                    run_missing = False
                except DomainError:
                    run_missing = True
                try:
                    await uow.scenes.get_intent(
                        derive_intent_id(ids["world"], snapshot, ids["wren"])
                    )
                    intent_missing = False
                except DomainError:
                    intent_missing = True
                return {
                    "events": events,
                    "open_run": open_run,
                    "run_missing": run_missing,
                    "intent_missing": intent_missing,
                }
        finally:
            await engine.dispose()

    state = asyncio.run(_inspect())
    assert state["events"] == 0
    assert state["open_run"] is None
    assert state["run_missing"] is True
    assert state["intent_missing"] is True

    ash_question = {
        str(ids["ash"]): {
            "family": "communicate",
            "character_id": str(ids["ash"]),
            "snapshot_id": str(snapshot),
            "target_character_id": str(ids["wren"]),
            "topic": "dusk patrol",
        }
    }
    retry = _advance(client, ids["world"], 1, ash_question, _player(ids["ash"]))
    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicate"] is False

    async def _verify_retry() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                retry_snapshot = UUID(retry.json()["snapshot_id"])
                ash_intent = await uow.scenes.get_intent(
                    derive_intent_id(ids["world"], retry_snapshot, ids["ash"])
                )
                assert ash_intent.action.family.value == "communicate"
                wren_intent = await uow.scenes.get_intent(
                    derive_intent_id(ids["world"], retry_snapshot, ids["wren"])
                )
                assert wren_intent.action.family.value == "wait"
                calls = await uow.traces.list_for_phase_run(UUID(retry.json()["run_id"]))
                assert not [
                    call
                    for call in calls
                    if call.role == "character_decision" and call.actor_id == ids["ash"]
                ]
        finally:
            await engine.dispose()

    asyncio.run(_verify_retry())


def test_open_run_freezes_grant_for_fresh_resume(
    api: tuple[ApiClient, FakeGateway, dict[str, UUID]],
) -> None:
    """An admitted-but-unfinished run refuses role changes and resumes frozen.

    Each HTTP request builds a new Stage1Orchestrator, so the completing
    advance is a fresh orchestrator resuming the open run: Wren stays
    protected by the grant admission captured, with no persisted ownership
    field, because selection is refused while the run is open.
    """
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
    from worldsim.domain.errors import DomainError
    from worldsim.domain.phases import PhaseRun

    client, gateway, _ = api
    ids = asyncio.run(_seed_two())
    snapshots = {1: derive_snapshot_id(derive_run_id(ids["world"], 1))}
    base_route = _route_for(ids, snapshots)

    def _guarded_route(request: CompletionRequest) -> Any:
        if "You decide" in (request.system or "") and "Wren" in request.prompt:
            raise AssertionError("controlled Wren must not reach model decision")
        return base_route(request)

    gateway.route = _guarded_route

    selected = client.post(
        "/api/v1/stage2/roles/select",
        json={
            "world_id": str(ids["world"]),
            "role": "player",
            "character_id": str(ids["wren"]),
        },
        headers=_watcher(),
    )
    assert selected.status_code == 200, selected.text

    run_id = str(derive_run_id(ids["world"], 1))
    engine = create_engine(Settings())
    try:
        from uuid import UUID as _UUID

        async def _admit_bare() -> None:
            async with create_unit_of_work(engine) as uow:
                await uow.phases.create_run(
                    PhaseRun(id=_UUID(run_id), world_id=ids["world"], absolute_index=1)
                )
                await uow.commit()

        asyncio.run(_admit_bare())
    finally:
        asyncio.run(engine.dispose())

    refused = client.post(
        "/api/v1/stage2/roles/select",
        json={
            "world_id": str(ids["world"]),
            "role": "player",
            "character_id": str(ids["ash"]),
        },
        headers=_watcher(),
    )
    assert refused.status_code == 409, refused.text
    refused_watcher = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "watcher"},
        headers=_watcher(),
    )
    assert refused_watcher.status_code == 409, refused_watcher.text

    report = _advance(client, ids["world"], 1)
    assert report.status_code == 200, report.text
    assert report.json()["duplicate"] is False

    async def _verify() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                snapshot = UUID(report.json()["snapshot_id"])
                try:
                    await uow.scenes.get_intent(
                        derive_intent_id(ids["world"], snapshot, ids["wren"])
                    )
                    wren_protected = False
                except DomainError:
                    wren_protected = True
                assert wren_protected, "resumed run must keep Wren free of model intents"
                calls = await uow.traces.list_for_phase_run(UUID(report.json()["run_id"]))
                assert not [
                    call
                    for call in calls
                    if call.role in ("character_decision", "reaction")
                    and call.actor_id == ids["wren"]
                ]
        finally:
            await engine.dispose()

    asyncio.run(_verify())

    reopened = client.post(
        "/api/v1/stage2/roles/select",
        json={"world_id": str(ids["world"]), "role": "watcher"},
        headers=_watcher(),
    )
    assert reopened.status_code == 200, reopened.text
