# perf-turn-002: the canonical commit and call tracing, in fewer statements

## Question

perf-turn-001 cut a turn from about 342 to 297 statements. It left alone the two places it called the
core of the system:
- the canonical commit, where the command row and its event point at each other, so a later UPDATE
  set the link;
- model-call tracing, at 4 statements per call.

Can either take fewer round trips without weakening idempotency, the audit trail or the order of
writes? And what else large is left?

## Setup

- **Bench:** `backend/scripts/beat_bench.py`, scripted fake gateway, first two turns left out.
  - cast 3 on 6 places, 30 turns: 3 alternating pairs;
  - party (`--party`), 20 turns: 2 pairs;
  - cast 10, 15 turns: 1 pair.
- **Before:** `12f482a` in a detached worktree. **After:** `feat/turnspeed2`. Every run used
  `PYTHONPATH=<tree>/backend/src`, and the imported path was checked.
- **Trace writes:** timed alone with the new `backend/scripts/trace_write_bench.py`: 300 calls each,
  old and new alternating, each step in its own transaction as `TraceService` does.
- **Call counts vary:** the scripted cast picks actions from call order, so runs differ in how many
  calls they make. Statement counts per turn are steady (±2). Milliseconds follow machine load.

## What changed

- **Tracing: 4 statements per call → 2.**
  - **Start:** `start_call_with_manifest` inserts the call row and its manifest in one statement: a CTE
    inserts the call, and the manifest is inserted from its `RETURNING`, so a manifest cannot exist
    without its call.
  - **Finish:** `finish_call_with_cost` finishes the call and inserts the cost from the UPDATE's
    `RETURNING`. A missing call writes nothing and raises, as `finish_call` did.
  - **Unchanged:** both stay in their own transactions at the same moments, so a call is still on
    record, committed, before the model is asked. That was perf-beat-001's reason for not batching
    per turn.
- **Canonical commit: 3 `user_command` statements + 1 per effect → 1 + 1 + 1.**
  - **Command row:** `add_new` records the command with `INSERT … ON CONFLICT (uq_command_world_key)
    DO NOTHING RETURNING id`. Only a replay or a lost race goes on to read the existing command and
    answer as the first commit did. A key held by a transaction still open waits for it, as the
    unique index did; `_race_retry` is gone.
  - **Event and link:** `append_event_completing` inserts the event and sets the command's
    `result_event_id` from its `RETURNING`. The circular foreign key is checked at the end of the
    statement, when the event exists, so **no migration** was needed and the rows are the same.
  - **Effects:** `append_effects` writes a commit's effects in one multi-row insert.
- **Version locks:** `compare_and_bump` reused the rows `check` had just locked `FOR UPDATE` in the
  same transaction. The store now remembers the locks, keyed by the sync session's transaction
  object, and reads again after any commit or rollback.
- **Narration:** a scene's beats, the fallback beats and the dice beats go in one multi-row insert
  each (`save_narrations`). Beats are read back `ORDER BY created_at`, so each gets its own instant,
  a microsecond apart in written order.
- **Budget check:** `_over_budget` ran once per scene with the same answer, loading every call row
  of the turn (prompts included) just to count them. It now runs once per turn, with
  `count_for_phase_run`.
- **`_answered`:** takes the clock from the phase's shared view when one is active (left in
  perf-turn-001 while the repeat guard was changing).

## Results

### Per turn (means of turns 3+)

| run | statements | SQL ms | wall ms |
|---|---|---|---|
| cast 3, pair 1 | 298.5 → 255.2 | 645 → 547 | 905 → 820 |
| cast 3, pair 2 | 298.0 → 257.1 | 602 → 559 | 833 → 790 |
| cast 3, pair 3 | 296.7 → 257.1 | 585 → 542 | 862 → 807 |
| **cast 3, mean** | **297.7 → 256.5 (−14%)** | **611 → 549 (−10%)** | **866 → 806 (−7%)** |
| party, pair 1 (calls 201 vs 276) | 346.4 → 285.7 | 631 → 663 | 1,002 → 1,012 |
| party, pair 2 (calls 299 vs 274) | 330.2 → 290.4 | 803 → 621 | 1,061 → 1,012 |
| **party, mean** | **338.3 → 288.1 (−15%)** | 717 → 642 | 1,031 → 1,012 (noise) |
| **cast 10** | **683.8 → 529.8 (−23%)** | 5,128 → 3,649 (−29%) | 2,320 → 2,067 (−11%) |

Against perf-turn-001's starting point (`54dfb96`: 342 statements at cast 3, 818 at cast 10), the two
passes together take a turn to about 256 (−25%) and 530 (−35%).

### One model call's trace writes (`trace_write_bench.py`, 295 calls each)

| way | median | mean |
|---|---|---|
| old: 4 statements | 17.0 ms | 18.0 ms |
| new: 2 statements, plain SQL | **12.5 ms (−26%)** | 13.1 ms |

## Rejected

- **The same statements composed with SQLAlchemy Core.**
  - This was the first try, and it made fewer statements but a slower turn. Its runs are kept in
    `rejected-core/`: wall time no better at cast 3 or for the party, SQL ms flat.
  - Timed alone, a Core CTE trace start took 8.4 ms, against 7.5 ms for the old two ORM inserts and
    5.1 ms for the same CTE as plain SQL. The extra time is compiling the statement in Python.
  - `pg_insert(...).on_conflict_do_nothing(...)` with JSON values has no cache key, so it recompiled
    on every commit.
  - The kept versions are module-level `text()` statements with typed bind parameters. JSONB values
    are bound with SQLAlchemy's JSONB type, so they serialize as before.
- **Not writing `result_event_id` at all**, deriving it from `world_event.source_command_id`. The
  macro engine and branch copies read the column. One statement does both instead.
- **Making `fk_command_result` deferrable** (a migration). Not needed once one statement inserts
  the event and sets the link, and it would have had to stay safe under the old-schema test
  (0031/0032).
- **Taking the next event sequence inside the insert** instead of `max_sequence` first. It would save
  about 3 statements a turn, but needs events built with a placeholder sequence. Not worth it.
- **Still left:**
  - the per-character mind reads (4 tables per phase view);
  - each scene's recent-event window (`_recent_window`, about 2 a scene);
  - the phase-run admission reads;
  - sessions per turn (about 94; each shared load and task row still opens its own).

## Verdict

The canonical commit and every model call now take fewer round trips with the same rows, the same
idempotency (replays and races answer as before), the same audit (a call is on record before the
model is asked) and the same contexts:
- `--verify-reads` is clean at cast 3 (30 turns), cast 10 (20) and party (20);
- the commit, replay, branch, rewind and old-schema tests pass.

A turn is 14% lighter at cast 3 and 23% at cast 10, and a model call's tracing is 26% faster.

## Files

- `before-*.json` / `after-*.json` (+ `.log`): the runs in the table.
- `rejected-core/`: the Core variant's runs.
- `backend/scripts/trace_write_bench.py`: the trace-write timer.
