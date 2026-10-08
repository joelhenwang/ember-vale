"""Make one story K times longer, for scaling benchmarks.

Copies a story's history (phase runs, snapshots, events, effects, scenes,
participants, intents, attempts, reactions, resolutions, narration,
observations, memories and scene pictures) K-1 times into its past, with
fresh ids derived from the old ones, and moves the world clock forward so
the original turns stay the newest. Characters, places and assets are
shared, so every read path sees a story with K times the turns.

Refuses any database whose name does not end in "_bench": it must never
run on real data. Make the bench copy first, e.g. inside the db container:

    dropdb --if-exists embervale_bench && createdb embervale_bench
    pg_dump embervale | psql -q embervale_bench

    python scripts/bench_amplify.py --db postgresql+asyncpg://.../embervale_bench \\
        --world <world_id> --times 100
"""

from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

PHASES_PER_DAY = 10
PHASES = (
    "dawn",
    "sunrise",
    "morning",
    "noon",
    "afternoon",
    "sunset",
    "dusk",
    "evening",
    "night",
    "midnight",
)

# m(x) is a fresh id for row x in copy :k; every reference to a copied row
# maps the same way, so copies stay internally consistent.
M = "md5(({col})::text || ':' || :k)::uuid"


def m(col: str) -> str:
    return M.format(col=col)


def copy_sql() -> list[str]:
    """Statements that insert copy :k, shifted back by :dabs phases and :dseq sequences."""
    w = "world_id = :w"
    return [
        f"""insert into phase_run (id, world_id, absolute_index, state, created_at, updated_at)
            select {m("id")}, world_id, absolute_index - :dabs, state, created_at, updated_at
            from phase_run where {w} and absolute_index >= :lo""",
        f"""insert into phase_snapshot (id, world_id, phase_run_id, absolute_index, schema_version,
              world_version, content_hash, sealed_at)
            select {m("id")}, world_id, {m("phase_run_id")}, absolute_index - :dabs, schema_version,
              world_version, md5(content_hash || ':' || :k), sealed_at
            from phase_snapshot where {w} and absolute_index >= :lo""",
        f"""insert into world_event (id, world_id, sequence, event_type, schema_version,
              absolute_index, phase_run_id, source_command_id, source_task_id, participant_ids,
              summary, visibility, random_seed, random_algorithm, random_result, created_at)
            select {m("id")}, world_id, sequence - :dseq, event_type, schema_version,
              absolute_index - :dabs,
              case when phase_run_id is null then null else {m("phase_run_id")} end,
              null, null, participant_ids, summary, visibility, random_seed, random_algorithm,
              random_result, created_at
            from world_event where {w} and sequence >= :seqlo""",
        f"""insert into event_effect (event_id, ordinal, effect_type, schema_version, payload)
            select {m("f.event_id")}, f.ordinal, f.effect_type, f.schema_version, f.payload
            from event_effect f join world_event e on e.id = f.event_id
            where e.{w} and e.sequence >= :seqlo""",
        f"""insert into scene (id, world_id, phase_run_id, snapshot_id, status, beat_budget,
              event_id, created_at, updated_at, narration_status)
            select {m("s.id")}, s.world_id, {m("s.phase_run_id")}, {m("s.snapshot_id")}, s.status,
              s.beat_budget, case when s.event_id is null then null else {m("s.event_id")} end,
              s.created_at, s.updated_at, s.narration_status
            from scene s join phase_run r on r.id = s.phase_run_id
            where s.{w} and r.absolute_index >= :lo""",
        f"""insert into scene_participant (scene_id, character_id, role)
            select {m("p.scene_id")}, p.character_id, p.role
            from scene_participant p join scene s on s.id = p.scene_id
            join phase_run r on r.id = s.phase_run_id
            where s.{w} and r.absolute_index >= :lo""",
        f"""insert into character_intent (id, world_id, snapshot_id, phase_run_id,
              author_character_id, family, intent, status, idempotency_key, created_at, updated_at)
            select {m("i.id")}, i.world_id, {m("i.snapshot_id")},
              case when i.phase_run_id is null then null else {m("i.phase_run_id")} end,
              i.author_character_id, i.family, i.intent, i.status,
              md5(i.idempotency_key || ':' || :k), i.created_at, i.updated_at
            from character_intent i join phase_snapshot n on n.id = i.snapshot_id
            where i.{w} and n.absolute_index >= :lo""",
        f"""insert into attempt (id, world_id, scene_id, intent_id, actor_character_id,
              observable_summary, status, created_at)
            select {m("a.id")}, a.world_id,
              case when a.scene_id is null then null else {m("a.scene_id")} end,
              {m("a.intent_id")}, a.actor_character_id, a.observable_summary, a.status,
              a.created_at
            from attempt a join character_intent i on i.id = a.intent_id
            join phase_snapshot n on n.id = i.snapshot_id
            where a.{w} and n.absolute_index >= :lo""",
        f"""insert into reaction (id, world_id, attempt_id, scene_id, reactor_character_id,
              reaction, status, created_at)
            select {m("x.id")}, x.world_id, {m("x.attempt_id")},
              case when x.scene_id is null then null else {m("x.scene_id")} end,
              x.reactor_character_id, x.reaction, x.status, x.created_at
            from reaction x join attempt a on a.id = x.attempt_id
            join character_intent i on i.id = a.intent_id
            join phase_snapshot n on n.id = i.snapshot_id
            where x.{w} and n.absolute_index >= :lo""",
        f"""insert into resolution (id, world_id, scene_id, resolver, outcome, profile_version,
              effects, rationale, random_seed, created_at)
            select {m("x.id")}, x.world_id, {m("x.scene_id")}, x.resolver, x.outcome,
              x.profile_version, x.effects, x.rationale, x.random_seed, x.created_at
            from resolution x join scene s on s.id = x.scene_id
            join phase_run r on r.id = s.phase_run_id
            where x.{w} and r.absolute_index >= :lo""",
        f"""insert into narration (id, world_id, scene_id, event_id, speaker_character_id, kind,
              text, emotion_hint, source_effect_ids, created_at, cited_fact_keys)
            select {m("x.id")}, x.world_id,
              case when x.scene_id is null then null else {m("x.scene_id")} end,
              {m("x.event_id")}, x.speaker_character_id, x.kind, x.text, x.emotion_hint,
              x.source_effect_ids, x.created_at, x.cited_fact_keys
            from narration x join world_event e on e.id = x.event_id
            where x.{w} and e.sequence >= :seqlo""",
        f"""insert into observation (id, world_id, event_id, observer_character_id, facts,
              created_phase_index, salience, content_hash, source_id)
            select {m("o.id")}, o.world_id, {m("o.event_id")}, o.observer_character_id, o.facts,
              o.created_phase_index - :dabs, o.salience,
              case when o.content_hash is null then null else md5(o.content_hash || ':' || :k) end,
              o.source_id
            from observation o join world_event e on e.id = o.event_id
            where o.{w} and e.sequence >= :seqlo""",
        f"""insert into recent_memory (id, world_id, owner_character_id, event_id, observation_id,
              text, visibility, created_phase_index, salience, content_hash)
            select {m("x.id")}, x.world_id, x.owner_character_id,
              case when x.event_id is null then null else {m("x.event_id")} end,
              case when x.observation_id is null then null else {m("x.observation_id")} end,
              x.text, x.visibility, x.created_phase_index - :dabs, x.salience,
              case when x.content_hash is null then null else md5(x.content_hash || ':' || :k) end
            from recent_memory x where x.{w} and x.created_phase_index >= :lo""",
        f"""insert into image_job (id, world_id, kind, subject_id, style_pack_version,
              idempotency_key, status, attempt_count, result_asset_id, error, version)
            select {m("j.id")}, j.world_id, j.kind, {m("j.subject_id")}, j.style_pack_version,
              md5(j.idempotency_key || ':' || :k), j.status, j.attempt_count, j.result_asset_id,
              j.error, j.version
            from image_job j join scene_picture p on p.job_id = j.id
            where p.{w} and p.created_phase_index >= :lo""",
        f"""insert into scene_picture (id, world_id, scene_id, job_id, moment, caption, prompt,
              character_ids, location_id, created_phase_index, created_at, title, raw_prompt,
              repaint_job_id)
            select {m("id")}, world_id, {m("scene_id")}, {m("job_id")}, moment, caption, prompt,
              character_ids, location_id, created_phase_index - :dabs, created_at, title,
              raw_prompt, null
            from scene_picture where {w} and created_phase_index >= :lo""",
    ]


async def amplify(url: str, world: str, times: int) -> None:
    name = urlparse(url.replace("+asyncpg", "")).path.lstrip("/")
    if not name.endswith("_bench"):
        raise SystemExit(f"refusing to touch {name!r}: only *_bench databases")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        # History is append-only (triggers); this bench copy is rewritten on
        # purpose, so triggers are off for this session only.
        await conn.execute(text("set local session_replication_role = replica"))
        span_abs = (
            await conn.execute(
                text(
                    "select greatest("
                    "(select max(absolute_index) from phase_run where world_id = :w),"
                    " (select max(absolute_index) from world_event where world_id = :w),"
                    " (select absolute_index from world_clock where world_id = :w)) + 1"
                ),
                {"w": world},
            )
        ).scalar_one()
        span_seq = (
            await conn.execute(
                text("select coalesce(max(sequence), 0) from world_event where world_id = :w"),
                {"w": world},
            )
        ).scalar_one()
        shift_abs, shift_seq = (times - 1) * span_abs, (times - 1) * span_seq
        # Originals move forward to stay the newest turns; copies fill the past.
        for table, col in (
            ("phase_run", "absolute_index"),
            ("phase_snapshot", "absolute_index"),
            ("world_event", "absolute_index"),
            ("observation", "created_phase_index"),
            ("recent_memory", "created_phase_index"),
            ("scene_picture", "created_phase_index"),
            ("narrative_hook", "created_phase_index"),
        ):
            await conn.execute(
                text(f"update {table} set {col} = {col} + :d where world_id = :w"),
                {"d": shift_abs, "w": world},
            )
        await conn.execute(
            text("update world_event set sequence = sequence + :d where world_id = :w"),
            {"d": shift_seq, "w": world},
        )
        clock_abs = (
            await conn.execute(
                text("select absolute_index from world_clock where world_id = :w"), {"w": world}
            )
        ).scalar_one() + shift_abs
        await conn.execute(
            text(
                "update world_clock set absolute_index = :a, day = :d, phase = :p"
                " where world_id = :w"
            ),
            {
                "a": clock_abs,
                "d": clock_abs // PHASES_PER_DAY + 1,
                "p": PHASES[clock_abs % PHASES_PER_DAY],
                "w": world,
            },
        )
        statements = copy_sql()
        for k in range(1, times):
            params = {
                "w": world,
                "k": f"{span_seq}:{k}",  # salted: a second pass makes new ids
                "lo": shift_abs,
                "seqlo": shift_seq + 1,
                "dabs": k * span_abs,
                "dseq": k * span_seq,
            }
            for sql in statements:
                await conn.execute(text(sql), params)
        counts = (
            await conn.execute(
                text(
                    "select (select count(*) from world_event where world_id = :w),"
                    " (select count(*) from scene where world_id = :w),"
                    " (select count(*) from narration where world_id = :w),"
                    " (select count(*) from observation where world_id = :w),"
                    " (select count(*) from scene_picture where world_id = :w)"
                ),
                {"w": world},
            )
        ).one()
    await engine.dispose()
    print(
        f"{world}: x{times}: events={counts[0]} scenes={counts[1]} narration={counts[2]}"
        f" observations={counts[3]} pictures={counts[4]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--times", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(amplify(args.db, args.world, args.times))


if __name__ == "__main__":
    main()
