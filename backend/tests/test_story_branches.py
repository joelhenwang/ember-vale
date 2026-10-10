"""Branch a story from any kept turn (story-branches-001, migration 0058).

A real story (the built-in vale, Wren as the player) plays five turns with a
scripted fake model: people talk, move and look, the director opens a
rumour. Then it branches from turn 2 and the tests check that:

* the branch's changeable state equals the source's state as it stood right
  after turn 2 (row for row, once the branch's ids are renamed back);
* the source is unchanged byte for byte, by the branch and by turns played
  on the branch;
* no row of the branch names a row of the source (only the provenance row
  and the shared picture files are allowed to);
* the same key replays, another body with that key conflicts;
* a turn whose state was not kept, or not played, is refused plainly;
* the branch plays on with the fake model.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_stage1_api import ApiClient

from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.application.stories.branch import NOT_KEPT, NOT_PLAYED, branch_story
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.checkpoints import STATE_TABLES
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

ROOT = Path(__file__).parent.parent.parent
SEED_DIR = ROOT / "content" / "seeds" / "stage0"
MIGRATIONS = ROOT / "backend" / "migrations"

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"
WREN_PRESET_ID = "20000000-0000-4000-8000-000000000101"
ASH_PRESET_ID = "20000000-0000-4000-8000-000000000102"
PLACEHOLDER_SNAPSHOT = "00000000-0000-4000-8000-000000000000"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")

#: Every table holding a story's rows, and how to find them.
_ROWS_OF = [(table, where.replace("t.", "t.")) for table, where in STATE_TABLES] + [
    ("world_config", "t.world_id = :w"),
    ("phase_run", "t.world_id = :w"),
    ("phase_snapshot", "t.world_id = :w"),
    (
        "phase_snapshot_character",
        "t.snapshot_id IN (SELECT id FROM phase_snapshot WHERE world_id = :w)",
    ),
    ("world_event", "t.world_id = :w"),
    ("event_effect", "t.event_id IN (SELECT id FROM world_event WHERE world_id = :w)"),
    ("user_command", "t.world_id = :w"),
    ("task_run", "t.world_id = :w"),
    ("observation", "t.world_id = :w"),
    ("recent_memory", "t.world_id = :w"),
    ("long_term_memory", "t.world_id = :w"),
    ("daily_summary", "t.world_id = :w"),
    ("scene", "t.world_id = :w"),
    ("scene_participant", "t.scene_id IN (SELECT id FROM scene WHERE world_id = :w)"),
    ("character_intent", "t.world_id = :w"),
    ("attempt", "t.world_id = :w"),
    ("reaction", "t.world_id = :w"),
    ("resolution", "t.world_id = :w"),
    ("narration", "t.world_id = :w"),
    ("model_call", "t.world_id = :w"),
    ("context_manifest", "t.world_id = :w"),
    ("outbox_message", "t.world_id = :w"),
    ("asset_record", "t.world_id = :w"),
    ("image_job", "t.world_id = :w"),
    ("scene_picture", "t.world_id = :w"),
    ("recall_vector", "t.world_id = :w"),
    ("autoplay", "t.world_id = :w"),
    ("story_catalog", "t.world_id = :w"),
    ("story_initial_setup", "t.world_id = :w"),
    ("story_prompts", "t.world_id = :w"),
    ("character_image_prompt", "t.world_id = :w"),
    ("story_checkpoint", "t.world_id = :w"),
    ("story_branch", "t.world_id = :w"),
]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _dump(
    world_id: UUID, tables: list[tuple[str, str]] | None = None
) -> dict[str, list[str]]:
    """Every row of a story as canonical JSON text, per table, sorted."""
    engine = create_engine(Settings())
    out: dict[str, list[str]] = {}
    try:
        async with engine.connect() as conn:
            for table, where in tables or _ROWS_OF:
                raw = (
                    await conn.execute(
                        text(
                            "SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)::text"
                            f' FROM "{table}" t WHERE {where}'
                        ),
                        {"w": world_id},
                    )
                ).scalar_one()
                out[table] = sorted(json.dumps(r, sort_keys=True) for r in json.loads(raw))
    finally:
        await engine.dispose()
    return out


async def _sql(statement: str, **params: Any) -> list[Any]:
    engine = create_engine(Settings())
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(statement), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


@dataclass
class Cast:
    wren: UUID
    ash: UUID
    places: list[UUID]
    market: UUID | None = None


def _script(cast: Cast, calls: dict[str, int] | None = None):
    """The scripted model; ``calls`` carries on the counts of a story played before."""
    calls = calls if calls is not None else {"decide": 0, "director": 0}

    def route(request: CompletionRequest) -> str | None:
        system, prompt = request.system or "", request.prompt
        if system.startswith("You narrate") or "You narrate" in system:
            keys = re.findall(r'key "([^"]+)"', prompt)[:1] or ["place"]
            return json.dumps([{"text": "The square hums with talk.", "cited_fact_keys": keys}])
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "As tried."})
        if "You react" in system:
            return json.dumps({"family": "observe", "focus": "the speaker"})
        if "You direct" in system:
            calls["director"] += 1
            return json.dumps(
                {
                    "action": "propose_hook",
                    "title": f"A lost ledger {calls['director']}",
                    "purpose": "The miller lost his ledger near the market and wants it back.",
                }
            )
        if "You summarize" in system:
            # Cite the first two sources: cited ones gain salience, as in play.
            tags = re.findall(r"^\[([om]\d+)\]", prompt, re.MULTILINE)[:2]
            return json.dumps({"text": "A day of talk.", "source_ids": tags})
        if "You distill" in system:
            return json.dumps({"memories": []})
        if "You decide" in system:
            calls["decide"] += 1
            n = calls["decide"]
            ids = set(_UUID.findall(prompt))
            places = [p for p in cast.places if str(p) in ids]
            if n % 3 == 0 and places:
                return json.dumps({"family": "move", "destination_location_id": str(places[0])})
            if n % 3 == 1:
                return json.dumps(
                    {
                        "family": "communicate",
                        "target_character_id": str(cast.wren),
                        "topic": f"asks about the road, turn {n}",
                        "intention": f"find the ledger ({n})",
                    }
                )
            return json.dumps({"family": "observe", "focus": "the square"})
        return None

    return route


@dataclass
class Played:
    client: ApiClient
    source: UUID
    cast: Cast
    after_turn: dict[int, dict[str, list[str]]]


def _create(client: ApiClient, title: str, key: str) -> dict[str, Any]:
    draft = client.post(
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
                "mode": {"role": "player", "controlled_cast_key": "cast-wren"},
                "story": {"title": title},
            },
            "current_step": "review",
        },
        headers={},
    ).json()
    created = client.post(
        "/api/v1/stories",
        json={"draft_id": draft["id"], "expected_draft_version": 1},
        headers={"Idempotency-Key": key},
    )
    assert created.status_code == 200, created.text
    return created.json()


async def _cast(world_id: UUID) -> Cast:
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            people = {c.name: c.id for c in await uow.characters.list_for_world(world_id)}
            locations = await uow.locations.list_for_world(world_id)
    finally:
        await engine.dispose()
    market = next(loc.id for loc in locations if "market" in loc.name.lower())
    return Cast(
        wren=people["Wren"], ash=people["Ash"], places=[loc.id for loc in locations], market=market
    )


def _advance(client: ApiClient, world_id: UUID, index: int, cast: Cast) -> None:
    family: dict[str, Any] = (
        {"family": "communicate", "target_character_id": str(cast.ash), "topic": "the ledger"}
        if index % 2
        else {"family": "observe", "focus": "the square"}
    )
    if index == 3 and cast.market is not None:
        # Wren walks to the market after the turn the branch is taken from.
        family = {"family": "move", "destination_location_id": str(cast.market)}
    response = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": index,
            "player_intents": {
                str(cast.wren): {
                    **family,
                    "character_id": str(cast.wren),
                    "snapshot_id": PLACEHOLDER_SNAPSHOT,
                }
            },
        },
        headers={},
    )
    assert response.status_code == 200, response.text


#: What a test needs to know about the played Ledger story.
@dataclass
class Ledger:
    world: UUID
    cast: Cast
    calls: dict[str, int]
    #: the story's changeable state (LEDGER_STATE) after each turn
    after_turn: dict[int, dict[str, list[str]]]


#: Changeable state, plus the rows whose salience a day's end moves.
LEDGER_STATE = [
    *STATE_TABLES,
    ("world_config", "t.world_id = :w"),
    ("observation", "t.world_id = :w"),
    ("recent_memory", "t.world_id = :w"),
]


def _play_ledger(turns: int = 5) -> Ledger:
    """The Ledger: Wren and Ash, played ``turns`` turns with the scripted model."""
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        client = ApiClient(raw)
        story = _create(client, "The Ledger", "ledger")
        world = UUID(story["world_id"])
        cast = _run(_cast(world))
        calls = {"decide": 0, "director": 0}
        gateway.route = _script(cast, calls)
        after: dict[int, dict[str, list[str]]] = {}
        for index in range(1, turns + 1):
            _advance(client, world, index, cast)
            after[index] = _run(_dump(world, LEDGER_STATE))
    return Ledger(world, cast, dict(calls), after)


def ledger_client(ledger: Ledger) -> tuple[ApiClient, TestClient, FakeGateway]:
    """An app over a copy of the Ledger whose model carries on where it stopped."""
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    gateway.route = _script(ledger.cast, dict(ledger.calls))
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    raw = TestClient(app)
    return ApiClient(raw), raw, gateway


@pytest.fixture
def played(snapshot_db: Any) -> Iterator[Played]:
    """The Ledger after five turns: played once per worker, copied per test."""
    ledger: Ledger = snapshot_db("ledger-5", _play_ledger)
    client, raw, _ = ledger_client(ledger)
    branch_state = {t for t, _ in STATE_TABLES} | {"world_config"}
    after = {
        index: {table: rows for table, rows in dump.items() if table in branch_state}
        for index, dump in ledger.after_turn.items()
    }
    with raw:
        yield Played(client, ledger.world, ledger.cast, after)


def _unmap(value: str, inverse: dict[str, str]) -> str:
    value = _UUID.sub(lambda m: inverse.get(m.group(0), m.group(0)), value)

    def bare(match: re.Match[str]) -> str:
        found = inverse.get(str(UUID(match.group(0))))
        return UUID(found).hex if found else match.group(0)

    return _HEX.sub(bare, value)


def test_branch_is_the_source_at_that_turn_and_isolated(played: Played) -> None:
    client, source = played.client, played.source
    # The turns played were all kept.
    points = client.get(f"/api/v1/stories/{source}/branch-points", headers={})
    assert points.status_code == 200, points.text
    assert points.json()["turns"] == [1, 2, 3, 4, 5]
    # Something actually changed after turn 2, or equality proves little:
    # Wren walked off (place, stamina) and a second rumour opened.
    for table in ("character_state", "narrative_hook", "world_clock"):
        assert played.after_turn[2][table] != played.after_turn[5][table], table

    before = _run(_dump(source))

    async def _branch() -> Any:
        engine = create_engine(Settings())
        try:
            return await branch_story(
                lambda: create_unit_of_work(engine), source, 2, None, "local", "direct-key"
            )
        finally:
            await engine.dispose()

    result = _run(_branch())
    assert result.copy is not None
    branch = result.world_id
    assert result.title == "The Ledger — from Day 1, morning"
    assert result.role == "player"
    inverse = {new: old for old, new in result.copy.remap.items()}
    assert result.character_id is not None
    assert inverse[str(result.character_id)] == str(played.cast.wren)

    # 1. The branch's changeable state is the source's state right after turn 2.
    state_now = _run(_dump(branch, [*STATE_TABLES, ("world_config", "t.world_id = :w")]))
    restored = {
        table: sorted(json.dumps(json.loads(_unmap(row, inverse)), sort_keys=True) for row in rows)
        for table, rows in state_now.items()
    }
    for table, rows in played.after_turn[2].items():
        assert restored[table] == rows, f"{table} differs from the state after turn 2"

    # History up to the turn came along, nothing after it.
    events = _run(
        _sql(
            "SELECT count(*) FROM world_event e JOIN story_checkpoint c"
            " ON c.world_id = e.world_id AND c.absolute_index = 2"
            " WHERE e.world_id = :w AND e.sequence <= c.event_sequence",
            w=source,
        )
    )[0][0]
    branch_events = _run(_sql("SELECT count(*) FROM world_event WHERE world_id = :w", w=branch))
    assert branch_events[0][0] == events > 0
    for table in ("scene", "narration", "observation", "phase_run"):
        count = _run(_sql(f"SELECT count(*) FROM {table} WHERE world_id = :w", w=branch))[0][0]
        assert count > 0, table
    runs = _run(_sql("SELECT max(absolute_index) FROM phase_run WHERE world_id = :w", w=branch))
    assert runs[0][0] == 2
    autoplay = _run(_sql("SELECT count(*) FROM autoplay WHERE world_id = :w", w=branch))
    assert autoplay[0][0] == 0

    # 2. The source is untouched.
    assert _run(_dump(source)) == before

    # 3. No row of the branch names a row of the source.
    source_ids = {r[0] for r in _run(_source_ids(source))}
    assert str(source) in source_ids
    leaks: list[str] = []
    for table, rows in _run(_dump(branch)).items():
        for row in rows:
            data = json.loads(row)
            if table == "story_branch":
                data.pop("source_world_id")
            if table == "asset_record":
                data.pop("content_ref")
            blob = json.dumps(data)
            found = set(_UUID.findall(blob)) | {str(UUID(h)) for h in _HEX.findall(blob)}
            leaks += [f"{table}: {f}" for f in found & source_ids]
    assert not leaks, leaks[:10]

    # 4. The branch plays on; the source still does not move.
    branch_cast = Cast(
        wren=UUID(result.copy.remap[str(played.cast.wren)]),
        ash=UUID(result.copy.remap[str(played.cast.ash)]),
        places=[UUID(result.copy.remap[str(p)]) for p in played.cast.places],
        market=None,
    )
    for index in (3, 4):
        _advance(client, branch, index, branch_cast)
    assert _run(_dump(source)) == before
    assert client.get(f"/api/v1/stories/{branch}/branch-points", headers={}).json()["turns"] == [
        1,
        2,
        3,
        4,
    ]

    # 5. The list and the detail say where it came from.
    detail = client.get(f"/api/v1/stories/{branch}", headers={}).json()
    assert detail["branched_from"] == {
        "story_id": str(source),
        "title": "The Ledger",
        "absolute_index": 2,
        "time_label": "Day 1, morning",
    }
    listed = client.get("/api/v1/stories", params={"status": "all"}, headers={}).json()
    by_id = {item["story_id"]: item for item in listed["items"]}
    assert by_id[str(branch)]["branched_from"]["absolute_index"] == 2
    assert by_id[str(source)]["branched_from"] is None


async def _source_ids(world_id: UUID) -> list[Any]:
    from worldsim.infrastructure.repositories.checkpoints import SqlAlchemyCheckpointRepository

    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            repo = uow.checkpoints
            assert isinstance(repo, SqlAlchemyCheckpointRepository)
            ids = await repo._source_ids(world_id)  # pyright: ignore[reportPrivateUsage]
    finally:
        await engine.dispose()
    return [(i,) for i in ids]


def test_branch_route_is_idempotent_and_refuses_plainly(played: Played) -> None:
    client, source = played.client, played.source
    url = f"/api/v1/stories/{source}/branch"
    first = client.post(url, json={"absolute_index": 3}, headers={"Idempotency-Key": "b-1"})
    assert first.status_code == 200, first.text
    again = client.post(url, json={"absolute_index": 3}, headers={"Idempotency-Key": "b-1"})
    assert again.status_code == 200, again.text
    assert again.json()["story_id"] == first.json()["story_id"]
    assert again.json()["replayed"] is True
    other = client.post(url, json={"absolute_index": 4}, headers={"Idempotency-Key": "b-1"})
    assert other.status_code == 409, other.text
    assert "different request" in other.json()["error"]["message"]

    titled = client.post(
        url, json={"absolute_index": 1, "title": "What if"}, headers={"Idempotency-Key": "b-2"}
    )
    assert titled.status_code == 200, titled.text
    assert titled.json()["title"] == "What if"

    later = client.post(url, json={"absolute_index": 9}, headers={"Idempotency-Key": "b-3"})
    assert later.status_code == 409
    assert later.json()["error"]["message"] == NOT_PLAYED

    # A turn played before turns were kept: refused, never rebuilt.
    _run(_sql("DELETE FROM story_checkpoint WHERE world_id = :w AND absolute_index = 4", w=source))
    old = client.post(url, json={"absolute_index": 4}, headers={"Idempotency-Key": "b-4"})
    assert old.status_code == 409
    assert old.json()["error"]["message"] == NOT_KEPT
    points = client.get(f"/api/v1/stories/{source}/branch-points", headers={}).json()
    assert points["turns"] == [1, 2, 3, 5]

    missing_key = client.post(url, json={"absolute_index": 3}, headers={})
    assert missing_key.status_code == 422


def test_the_turn_that_ends_a_day_keeps_its_summaries(played: Played) -> None:
    """Midnight's day-end work (summaries, digests) belongs to that turn."""
    client, source = played.client, played.source
    for index in range(6, 11):
        _advance(client, source, index, played.cast)
    summaries = _run(_sql("SELECT count(*) FROM daily_summary WHERE world_id = :w", w=source))
    assert summaries[0][0] > 0
    url = f"/api/v1/stories/{source}/branch"
    at_night = client.post(url, json={"absolute_index": 8}, headers={"Idempotency-Key": "n-8"})
    at_midnight = client.post(url, json={"absolute_index": 9}, headers={"Idempotency-Key": "n-9"})
    assert at_night.status_code == 200, at_night.text
    assert at_midnight.status_code == 200, at_midnight.text
    count = "SELECT count(*) FROM daily_summary WHERE world_id = :w"
    assert _run(_sql(count, w=UUID(at_night.json()["world_id"])))[0][0] == 0
    assert _run(_sql(count, w=UUID(at_midnight.json()["world_id"])))[0][0] == summaries[0][0]
    # The midnight branch's next turn starts day 2.
    branch = UUID(at_midnight.json()["world_id"])
    detail = client.get(f"/api/v1/stories/{branch}", headers={}).json()
    assert detail["absolute_index"] == 9
    assert detail["branched_from"]["time_label"] == "Day 1, midnight"

    # Salience moved at day's end; a turn of day 2 is restored with it.
    for index in (11,):
        _advance(client, source, index, played.cast)
    bumped = _run(
        _sql("SELECT count(*) FROM observation WHERE world_id = :w AND salience > 1.0", w=source)
    )[0][0]
    day_two = client.post(url, json={"absolute_index": 11}, headers={"Idempotency-Key": "n-11"})
    assert day_two.status_code == 200, day_two.text
    total = (
        "SELECT round(sum(salience)::numeric, 4), count(*) FROM observation o"
        " WHERE o.world_id = :w AND o.created_phase_index <= 11"
    )
    assert bumped > 0
    assert _run(_sql(total, w=UUID(day_two.json()["world_id"]))) == _run(_sql(total, w=source))
