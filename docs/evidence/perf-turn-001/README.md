# perf-turn-001: fewer database statements a turn

## Question

The test-speed work found that a turn with fake models costs about 1–1.4 s and 250–350 SQL
statements. Every statement costs 2–4 ms against the dev Postgres, and SQL time is most of a
turn that waits on no model. Which statements repeat, and which can go without changing behaviour?

## Setup

- **Bench:** `backend/scripts/beat_bench.py` with the scripted fake gateway. Cast 3 on 6 places, 30
  turns, plus cast 10 for 15 turns.
- **Party story:** `--party` (new) seats the first two of the cast as a linked level-1 party, so
  every scene they share narrates and rolls as a combat story's.
- **Before:** commit `54dfb96`, a detached worktree.
- **After:** `feat/turnspeed`. The two were run alternately, back to back on the same machine.
- **Which code runs:** `backend/.venv` in a worktree is main's venv, whose editable `worldsim`
  points at main's `src`. Every command here ran with `PYTHONPATH=<that tree>/backend/src`, and the
  imported path was checked first.
- **Attribution:** `--sql-callers` (new) attributes each statement to the application functions
  that issued it. SQLAlchemy runs the driver in a greenlet, so the async caller is the parent
  greenlet's live stack. At the end of a run it prints the mean per turn.
- The first two turns of each run are left out as warm-up.
- The scripted cast picks its actions from call order, so each run makes a different number of
  model calls. Statements per turn are steady run to run (±2). Milliseconds swing with machine load:
  per-statement latency ran from 2.0 to 4.2 ms during these runs.

## What repeated (before, statements per turn, cast 3)

| source | per turn | what it was |
|---|---|---|
| decision task rows (`_track_task` / `_finish_task`) | ~22 | each decision: find by key, insert, `SELECT … FOR UPDATE`, an archive lock on `story_catalog`, an update, then another locked select and update to finish; two transactions |
| `set_run_state` | ~14 | a `SELECT` of the run before each of ~7 state updates a turn |
| narration helpers | ~12 | each scene read its own event three times (place, recap, last spot), the 40-event window twice, its place by id after listing all places, and its intents one by one |
| item lists in contexts | ~10 | one query per character (carried) and one per place (lying there), in each phase view |
| intentions | 2 per character | the director and the wanted-place step fetched each character's intention one by one |
| dice step, party scenes only | ~8 a scene | the phase run read twice, each linked member's character fetched one by one (2 statements each), intents one by one |

## What changed

- **Task rows:**
  - `TaskRepository.start_running` inserts the decision's audit row already claimed, in one
    statement (`INSERT … ON CONFLICT DO NOTHING RETURNING`).
  - A resumed turn whose row exists takes the old create-and-claim path.
  - `finish` is one guarded `UPDATE … WHERE owner AND state='running' RETURNING`, and reads the
    row only when that matches nothing.
  - The archive lock is skipped on the fast path: admission refuses an archived story, and a story
    cannot be archived while a turn is open (revamp A09).
- **`set_run_state`:** one `UPDATE … RETURNING`.
- **Narration:** reads the scene's event, the places and the recent window once.
  - `_previously` and `_last_spot` take the event and window.
  - `_place_of` finds the place in the list already read.
  - The intents come from one `get_intents`.
- **Items:** one world list per phase view (`_world_items`), filtered for what a character carries
  (`_carried`) and what lies at a place (`_items_at`) in the same order the per-owner and
  per-place queries return. `list_for_owner` now breaks ties by id, so the fresh and shared paths
  agree byte for byte.
- **Intentions:** `IntentionRepository.list_for_world`, one query.
- **Dice step:** one read of the phase run, one character list for everyone's place, and one
  `get_intents`.

**Byte identity:** `--verify-reads` ran 30 turns at cast 3 and 20 at cast 10 with no difference
between shared and fresh contexts.

## Results (statements and ms per turn, mean of turns 3–30)

| run | before | after | change |
|---|---|---|---|
| cast 3, statements | 342 (341, 342, 344) | **297** (297, 299, 295) | −13% |
| cast 3, SQL ms | 780 | 633 | −19% |
| cast 3, wall ms | 1,004 | 890 | −11% |
| cast 3, statements per model call | 33.6 | 26.9 | −20% |
| party story, statements (paired runs 3–4) | 386 (389, 383) | **336** (330, 342) | −13% |
| party story, wall ms (paired runs 3–4) | 1,870 | 1,546 | −17% (noisy) |
| cast 10, statements (15 turns) | 818 | **688** | −16% |
| cast 10, wall ms | 2,565 | 2,305 | −10% |

The JSON files are the runs.
- Party runs 1–2 "after" were measured before the dice-step change, so they are left out. Their
  "before" twins are kept but not used in the table.
- Cast-3 "after" runs did not need re-running for the dice change: a scene without a party
  returns before the code it touches.

## Rejected or left

- **Canonical commit**: 3–4 `user_command` statements per scene commit. The command row and the
  event refer to each other, so the result link is a later `UPDATE`. Left as is; it is the
  idempotency core.
- **Tracing**: 4 statements per model call (the call row, the manifest, the finishing update, the
  cost row). Batching them was already rejected in perf-beat-001: it delays the record that a call
  started.
- **`_answered`'s clock read** (one per decision) could use the phase view. It was left alone
  because the repeat guard is being changed there in main at the same time.
- **The per-character mind reads** (observations, memories, relationships, long-term memories:
  4 per character per phase view) are four tables; one query would need a union of unlike rows.
  Not done.
- **Sessions per turn** fell only from about 111 to 100. Each shared load and each task row still
  opens its own session.

## Verdict

About one statement in seven is gone from every turn, more at larger casts, with no change in
what any role sees. The wall-time gain (10–17%) is real but noisy on this shared machine. The
statement counts are the dependable figure.
