"""Go back to a kept turn in place, and checkpoint retention (rewind-001).

The same story as the branch tests (the built-in vale, Wren as the player,
a scripted fake model) plays five turns; then it goes back to turn 2. The
tests check that:

* the story's changeable state equals its checkpoint of turn 2, table for
  table, and its history up to turn 2 is exactly what it was;
* nothing after turn 2 remains (runs, events, scenes, narration, model
  calls, pictures and their jobs, checkpoints, execution slots);
* the removed turns live on as "the path not taken", equal to the story as
  it stood before going back;
* other stories, including a branch sharing picture files, are untouched;
* the story plays on; refusals are plain; the same key replays;
* retention keeps exactly the newest turns and the last turn of older days,
  and a branch or rewind from a kept day end still matches.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import ApiClient
from test_story_branches import (
    _ROWS_OF,
    MIGRATIONS,
    SEED_DIR,
    Cast,
    _advance,
    _cast,
    _create,
    _dump,
    _run,
    _script,
    _sql,
    _unmap,
)

from worldsim.application.execution import admit, new_owner, phase_scope
from worldsim.application.stories.branch import NOT_PLAYED, PRUNED, STILL_WRITING
from worldsim.application.stories.rewind import (
    ALREADY_LATEST,
    NEWEST_NOT_KEPT,
    PLAYING,
    REWIND_NOT_KEPT,
    RewindResult,
    rewind_story,
)
from worldsim.domain import branches
from worldsim.domain.branches import keeps_turn, path_not_taken_title
from worldsim.domain.time import PHASES_PER_DAY
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.checkpoints import (
    EXTRA_TABLES,
    HISTORY_TABLES,
    STATE_TABLES,
)
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app

#: Changeable state, plus the rows whose salience a day's end moves.
_STATE = [
    *STATE_TABLES,
    ("world_config", "t.world_id = :w"),
    ("observation", "t.world_id = :w"),
    ("recent_memory", "t.world_id = :w"),
]


@dataclass
class Story:
    client: ApiClient
    world: UUID
    cast: Cast
    after_turn: dict[int, dict[str, list[str]]]


def _app(gateway: FakeGateway) -> Any:
    return create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )


def _play(client: ApiClient, gateway: FakeGateway, turns: int, title: str) -> Story:
    story = _create(client, title, f"rewind-{title}")
    world = UUID(story["world_id"])
    cast = _run(_cast(world))
    gateway.route = _script(cast)
    after: dict[int, dict[str, list[str]]] = {}
    for index in range(1, turns + 1):
        _advance(client, world, index, cast)
        after[index] = _run(_dump(world, _STATE))
    return Story(client, world, cast, after)


@pytest.fixture
def story(migrated_db: None) -> Iterator[Story]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    with TestClient(_app(gateway)) as raw:
        yield _play(ApiClient(raw), gateway, 5, "The Ledger")


def _rewind(world: UUID, index: int, key: str, *, writing: bool = False) -> RewindResult:
    async def go() -> RewindResult:
        engine = create_engine(Settings())
        try:
            return await rewind_story(
                lambda: create_unit_of_work(engine), world, index, "local", key, writing=writing
            )
        finally:
            await engine.dispose()

    return _run(go())


def _one(statement: str, **params: Any) -> Any:
    return _run(_sql(statement, **params))[0][0]


def _add_picture(world: UUID, turn: int, status: str, ref: str) -> tuple[UUID, UUID, UUID]:
    """A painted (or pending) picture of one of the turn's scenes: picture, job, asset."""
    scene = _one(
        "SELECT s.id FROM scene s JOIN phase_run r ON r.id = s.phase_run_id"
        " WHERE s.world_id = :w AND r.absolute_index = :n ORDER BY s.id LIMIT 1",
        w=world,
        n=turn,
    )
    picture, job, asset = uuid4(), uuid4(), uuid4()
    ready = status == "ready"
    if ready:
        _run(
            _sql(
                "INSERT INTO asset_record (id, world_id, kind, subject_id, content_ref, mime,"
                " width, height, style_pack_version, subject_visual_version, status, version)"
                " VALUES (:a, :w, 'scene', :p, :ref, 'image/webp', 64, 64, 'anime-saga-v1',"
                " 1, 'ready', 1)",
                a=asset,
                w=world,
                p=picture,
                ref=ref,
            )
        )
    _run(
        _sql(
            "INSERT INTO image_job (id, world_id, kind, subject_id, style_pack_version,"
            " idempotency_key, status, attempt_count, result_asset_id, error, version, created_at)"
            " VALUES (:j, :w, 'scene', :p, 'anime-saga-v1', :k, :s, 0, :a, '', 1, now())",
            j=job,
            w=world,
            p=picture,
            k=f"scene:{picture}",
            s=status,
            a=asset if ready else None,
        )
    )
    _run(
        _sql(
            "INSERT INTO scene_picture (id, world_id, scene_id, job_id, moment, caption, prompt,"
            " character_ids, created_phase_index, created_at, title, raw_prompt)"
            " VALUES (:p, :w, :s, :j, 'turning', 'A moment', 'paint it', '[]'::jsonb, :n,"
            " now(), 'A moment', false)",
            p=picture,
            w=world,
            s=scene,
            j=job,
            n=turn,
        )
    )
    return picture, job, asset


def _history_up_to(world: UUID, index: int) -> dict[str, list[str]]:
    """History rows that belong to turns up to ``index`` (salience left out)."""
    seq = _one(
        "SELECT event_sequence FROM story_checkpoint WHERE world_id = :w AND absolute_index = :n",
        w=world,
        n=index,
    )
    out: dict[str, list[str]] = {}
    for table, where in HISTORY_TABLES:
        found = _run(
            _sql(
                f"SELECT coalesce(jsonb_agg(to_jsonb(t) - 'salience'), '[]'::jsonb)::text"
                f' FROM "{table}" t WHERE {where}',
                w=world,
                n=index,
                seq=seq,
                days=(index + 1) // PHASES_PER_DAY,
            )
        )[0][0]
        out[table] = sorted(json.dumps(r, sort_keys=True) for r in json.loads(found))
    return out


def test_going_back_restores_the_turn_and_keeps_the_path_not_taken(story: Story) -> None:
    client, world = story.client, story.world
    # A painted picture of turn 1 (stays), one of turn 4 (goes, its file is
    # shared with the saved story) and a picture of turn 5 still painting.
    early = _add_picture(world, 1, "ready", "generated/early.webp")
    late = _add_picture(world, 4, "ready", "generated/late.webp")
    painting = _add_picture(world, 5, "pending", "")
    # Another story that shares a picture file: a branch from turn 3.
    other = client.post(
        f"/api/v1/stories/{world}/branch",
        json={"absolute_index": 3},
        headers={"Idempotency-Key": "other"},
    )
    assert other.status_code == 200, other.text
    other_id = UUID(other.json()["world_id"])
    other_before = _run(_dump(other_id))
    history_before = _history_up_to(world, 2)
    latest_before = _run(_dump(world, _STATE))
    calls_later = _one(
        "SELECT count(*) FROM model_call c JOIN phase_run r ON r.id = c.phase_run_id"
        " WHERE c.world_id = :w AND r.absolute_index > 2",
        w=world,
    )
    assert calls_later > 0

    result = _rewind(world, 2, "go-back")
    assert result.copy is not None
    assert result.removed_turns == 3
    assert result.saved_title == path_not_taken_title("The Ledger", 5)
    assert result.saved_title == "The Ledger — the path not taken (Day 1, sunset)"

    # 1. The story's state is its checkpoint of turn 2, table for table.
    assert _run(_dump(world, _STATE)) == story.after_turn[2]
    # Its history up to turn 2 is what it was (salience is state, compared above).
    assert _history_up_to(world, 2) == history_before

    # 2. Nothing after turn 2 remains.
    assert _one("SELECT max(absolute_index) FROM phase_run WHERE world_id = :w", w=world) == 2
    assert (
        _one(
            "SELECT count(*) FROM world_event e WHERE e.world_id = :w AND e.sequence >"
            " (SELECT event_sequence FROM story_checkpoint WHERE world_id = :w"
            " AND absolute_index = 2)",
            w=world,
        )
        == 0
    )
    for table in ("phase_snapshot", "world_event"):
        later = _one(
            f"SELECT count(*) FROM {table} WHERE world_id = :w AND absolute_index > 2", w=world
        )
        assert later == 0, table
    for table in ("scene", "character_intent"):
        orphan = _one(
            f"SELECT count(*) FROM {table} t WHERE t.world_id = :w AND t.phase_run_id NOT IN"
            " (SELECT id FROM phase_run WHERE world_id = :w)",
            w=world,
        )
        assert orphan == 0, table
    for table in ("narration", "attempt", "reaction", "resolution", "scene_picture"):
        orphan = _one(
            f"SELECT count(*) FROM {table} t WHERE t.world_id = :w AND t.scene_id IS NOT NULL"
            " AND t.scene_id NOT IN (SELECT id FROM scene WHERE world_id = :w)",
            w=world,
        )
        assert orphan == 0, table
    assert (
        _one(
            "SELECT count(*) FROM model_call WHERE world_id = :w AND phase_run_id IS NOT NULL"
            " AND phase_run_id NOT IN (SELECT id FROM phase_run WHERE world_id = :w)",
            w=world,
        )
        == 0
    )
    assert (
        _one("SELECT max(absolute_index) FROM story_checkpoint WHERE world_id = :w", w=world) == 2
    )
    assert (
        _one(
            "SELECT count(*) FROM task_run WHERE world_id = :w AND idempotency_key LIKE :k"
            " AND split_part(idempotency_key, ':', 4)::integer BETWEEN 3 AND 5",
            w=world,
            k=f"execute:{world.hex}:phase:%",
        )
        == 0
    )
    pictures = {
        r[0] for r in _run(_sql("SELECT id FROM scene_picture WHERE world_id = :w", w=world))
    }
    assert pictures == {early[0]}
    jobs = {r[0] for r in _run(_sql("SELECT id FROM image_job WHERE world_id = :w", w=world))}
    assert early[1] in jobs and late[1] not in jobs and painting[1] not in jobs
    assets = {r[0] for r in _run(_sql("SELECT id FROM asset_record WHERE world_id = :w", w=world))}
    assert early[2] in assets and late[2] not in assets

    # 3. The path not taken is the story as it stood before going back.
    saved = result.saved_story_id
    inverse = {new: old for old, new in result.copy.remap.items()}
    saved_state = _run(_dump(saved, _STATE))
    restored = {
        table: sorted(json.dumps(json.loads(_unmap(row, inverse)), sort_keys=True) for row in rows)
        for table, rows in saved_state.items()
    }
    for table, rows in latest_before.items():
        assert restored[table] == rows, f"{table} of the saved story differs"
    assert _one("SELECT max(absolute_index) FROM phase_run WHERE world_id = :w", w=saved) == 5
    # The removed picture's file lives on in the saved story; the painting
    # that never finished does not come along.
    refs = {
        r[0]
        for r in _run(_sql("SELECT content_ref FROM asset_record WHERE world_id = :w", w=saved))
    }
    assert "generated/late.webp" in refs
    listed = client.get("/api/v1/stories", params={"status": "all"}, headers={}).json()
    by_id = {item["story_id"]: item for item in listed["items"]}
    assert by_id[str(saved)]["title"] == result.saved_title
    assert by_id[str(saved)]["branched_from"]["absolute_index"] == 5

    # 4. Other stories are untouched, including the branch sharing files.
    assert _run(_dump(other_id)) == other_before

    # 5. The story plays on from turn 2.
    for index in (3, 4):
        _advance(client, world, index, story.cast)
    points = client.get(f"/api/v1/stories/{world}/branch-points", headers={}).json()
    assert points["turns"] == [1, 2, 3, 4]
    assert points["latest_turn"] == 4
    detail = client.get(f"/api/v1/stories/{world}", headers={}).json()
    assert detail["absolute_index"] == 4


def test_going_back_refuses_plainly_and_replays(story: Story) -> None:
    client, world = story.client, story.world
    url = f"/api/v1/stories/{world}/rewind"

    def post(index: int, key: str | None) -> Any:
        headers = {"Idempotency-Key": key} if key else {}
        return client.post(url, json={"absolute_index": index}, headers=headers)

    latest = post(5, "r-latest")
    assert latest.status_code == 409
    assert latest.json()["error"]["message"] == ALREADY_LATEST
    later = post(9, "r-later")
    assert later.status_code == 409
    assert later.json()["error"]["message"] == NOT_PLAYED
    assert post(3, None).status_code == 422
    # Background writing still running in this process.
    with pytest.raises(Exception, match="still being written"):
        _rewind(world, 3, "r-writing", writing=True)
    assert STILL_WRITING.startswith("This turn is still being written")

    # A turn is being played: its execution slot is held.
    async def hold() -> None:
        engine = create_engine(Settings())
        try:
            await admit(lambda: create_unit_of_work(engine), world, phase_scope(6), new_owner("t"))
        finally:
            await engine.dispose()

    _run(hold())
    busy = post(3, "r-busy")
    assert busy.status_code == 409
    assert busy.json()["error"]["message"] == PLAYING
    _run(_sql("DELETE FROM task_run WHERE world_id = :w AND state = 'running'", w=world))

    # A turn whose checkpoint is missing; the newest not kept.
    _run(_sql("DELETE FROM story_checkpoint WHERE world_id = :w AND absolute_index = 2", w=world))
    missing = post(2, "r-missing")
    assert missing.status_code == 409
    assert missing.json()["error"]["message"] == REWIND_NOT_KEPT
    state5 = _run(
        _sql(
            "DELETE FROM story_checkpoint WHERE world_id = :w AND absolute_index = 5"
            " RETURNING world_id, absolute_index, event_sequence, schema_version, state::text",
            w=world,
        )
    )
    newest = post(3, "r-newest")
    assert newest.status_code == 409
    assert newest.json()["error"]["message"] == NEWEST_NOT_KEPT
    row = state5[0]
    _run(
        _sql(
            "INSERT INTO story_checkpoint (world_id, absolute_index, event_sequence,"
            " schema_version, state, created_at)"
            " VALUES (:w, :n, :s, :v, CAST(:st AS jsonb), now())",
            w=row[0],
            n=row[1],
            s=row[2],
            v=row[3],
            st=row[4],
        )
    )
    # Nothing was changed by the refusals.
    assert _run(_dump(world, _STATE)) == story.after_turn[5]

    first = post(4, "r-ok")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["removed_turns"] == 1 and body["replayed"] is False
    again = post(4, "r-ok")
    assert again.status_code == 200, again.text
    assert again.json()["saved_story_id"] == body["saved_story_id"]
    assert again.json()["replayed"] is True
    assert again.json()["removed_turns"] == 1
    other = post(3, "r-ok")
    assert other.status_code == 409
    assert "different request" in other.json()["error"]["message"]
    assert _run(_dump(world, _STATE)) == story.after_turn[4]
    stories = _one("SELECT count(*) FROM story_branch WHERE source_world_id = :w", w=world)
    assert stories == 1


def test_autoplay_stops_when_the_story_goes_back(story: Story) -> None:
    client, world = story.client, story.world
    _run(
        _sql(
            "INSERT INTO autoplay (world_id, status, delay_seconds, beats_left, beats_run, version)"
            " VALUES (:w, 'playing', 5, 10, 0, 1) ON CONFLICT (world_id) DO UPDATE"
            " SET status = 'playing'",
            w=world,
        )
    )
    done = client.post(
        f"/api/v1/stories/{world}/rewind",
        json={"absolute_index": 3},
        headers={"Idempotency-Key": "auto"},
    )
    assert done.status_code == 200, done.text
    row = _run(_sql("SELECT status, stop_detail FROM autoplay WHERE world_id = :w", w=world))[0]
    assert row[0] == "paused"
    assert row[1] == "Went back to an earlier turn."


def test_retention_rule() -> None:
    assert branches.KEEP_RECENT_TURNS == 200
    kept = [i for i in range(1, 451) if keeps_turn(i, 450)]
    assert kept == [i for i in range(1, 251) if i % 10 == 9] + list(range(251, 451))
    assert all(keeps_turn(i, 150) for i in range(1, 151))


def test_retention_keeps_the_newest_turns_and_older_day_ends(
    migrated_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A small window stands in for 200 so a long run fits in a test."""
    monkeypatch.setattr(branches, "KEEP_RECENT_TURNS", 6)
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    with TestClient(_app(gateway)) as raw:
        played = _play(ApiClient(raw), gateway, 32, "Long Road")
        client, world = played.client, played.world
        turns = client.get(f"/api/v1/stories/{world}/branch-points", headers={}).json()["turns"]
        assert turns == [i for i in range(1, 33) if keeps_turn(i, 32, 6)]
        assert turns == [9, 19, 27, 28, 29, 30, 31, 32]

        # A branch from a kept day end still matches that turn.
        branched = client.post(
            f"/api/v1/stories/{world}/branch",
            json={"absolute_index": 9},
            headers={"Idempotency-Key": "day-end"},
        )
        assert branched.status_code == 200, branched.text
        pruned = client.post(
            f"/api/v1/stories/{world}/branch",
            json={"absolute_index": 12},
            headers={"Idempotency-Key": "gone"},
        )
        assert pruned.status_code == 409
        assert pruned.json()["error"]["message"] == PRUNED

        # Going back to a kept day end restores it exactly; history after it goes.
        result = _rewind(world, 19, "back-to-19")
        assert _run(_dump(world, _STATE)) == played.after_turn[19]
        assert result.removed_turns == 13
        assert _one("SELECT max(absolute_index) FROM phase_run WHERE world_id = :w", w=world) == 19
        assert _one("SELECT max(day) FROM daily_summary WHERE world_id = :w", w=world) == 2
        # The saved story is the long road, with its own retained turns.
        saved_turns = client.get(
            f"/api/v1/stories/{result.saved_story_id}/branch-points", headers={}
        ).json()["turns"]
        assert saved_turns == turns


def test_every_story_table_is_classified(migrated_db: None) -> None:
    """A table holding story rows must be kept, copied or cleared by rewind.

    A new story table (the combat worker's, say) fails here until it is
    added to STATE_TABLES (state kept at each turn, rewound and branched
    generically) or to one of the other lists.
    """
    known = (
        {t for t, _ in STATE_TABLES}
        | {t for t, _ in HISTORY_TABLES}
        | {t for t, _ in EXTRA_TABLES}
        | {t for t, _ in _ROWS_OF}
        | {"world_config", "model_cost", "story_draft", "story_creation_receipt"}
    )

    async def tables() -> set[str]:
        engine = create_engine(Settings())
        try:
            async with engine.connect() as conn:
                from sqlalchemy import text

                rows = await conn.execute(
                    text(
                        "SELECT DISTINCT table_name FROM information_schema.columns"
                        " WHERE table_schema = current_schema()"
                        " AND column_name IN ('world_id', 'created_world_id')"
                    )
                )
                return {str(r[0]) for r in rows}
        finally:
            await engine.dispose()

    assert _run(tables()) - known == set()
