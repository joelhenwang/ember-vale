# rewind-001: checkpoint retention and "Go back to this turn"

## Question

The owner approved two follow-ups to story-branches-001:

1. **Retention.** Every turn keeps a checkpoint. How many should a long story keep?
2. **Going back in place.** The same story continues from an earlier kept turn, and later
   turns are removed from it. Nothing may be lost.

## Decisions (made for the owner, as briefed)

* **What is kept:** a checkpoint for each of the newest 200 turns. Before those, only the turn
  that ends each day (midnight, `absolute_index % 10 == 9`) is kept. The rule is
  `keeps_turn` / `KEEP_RECENT_TURNS` in `domain/branches.py`.
  `SqlAlchemyCheckpointRepository.prune` runs right after each capture in
  `Stage1Orchestrator._keep_turn`. It is one indexed range delete in its own transaction, so a
  failure is logged and only leaves a few extra rows. A turn never waits on or fails because of
  pruning. Day-end turns are the ones that stay, which also keeps valid the salience pointer
  that turns inside a day hold (story-branches-001).
* **Pruned turns are not offered.** `branch-points` lists only kept turns, so the UI shows no
  action on them. The API refuses them in plain words: "For older days only each day's last
  turn is kept. Choose the last turn of that day (midnight) instead." A turn played before 0058,
  or one whose keeping failed, still gets the old message.
* **Going back saves the discarded future first**, in the **same transaction**. The story as
  it stands is copied as a branch from its newest turn (`copy_into_new_story`, shared with
  branching), titled "<story> — the path not taken (Day N, time)" after the turn that path ends
  at. If that copy fails, nothing changes. Because it is one transaction, an Idempotency-Key
  replay can never report a rewind that did not happen.
* **How it goes back** (`checkpoints.rewind`, over the same table lists the checkpoint uses):
  1. The world's commands let go of later events.
  2. Every state table except the "anchors" is emptied.
  3. Everything hanging off removed turns is deleted: pictures of removed scenes; model
     calls, costs and manifests of removed runs; outbox rows of later events; later
     checkpoints.
  4. History after the turn goes, children first. The rule is the same one a branch copies by
     (`NOT coalesce(<up to the turn>, false)`). User commands follow the branch's rule: those
     the kept events came from stay.
  5. The anchors (`world`, `entity`, `location`, `character`, `character_card_version`) are
     upserted from the checkpoint, and the ones made later are deleted.
  6. The other state tables are reinserted from the checkpoint, and salience is restored.
  7. Image jobs and asset rows whose subject no longer exists, recall vectors of removed rows,
     and task runs of removed turns are deleted. Execution slots `phase:>N` and the
     character-decision tasks of removed model calls go too.
  8. Autoplay is paused with "Went back to an earlier turn."
* **Concurrency:** the rewind holds the execution slot of the next turn (`phase:<latest+1>`).
  A Step, an autoplay beat or a second tab then gets a plain "A turn is being played right
  now". It refuses while this process still writes narration or day-end work, when the
  newest turn's checkpoint is missing, or when the newest turn has scenes without words. It
  also refuses the newest turn itself, a turn not played, and a turn not kept.
* **Pictures and files:** asset rows of removed scenes go. **No stored file is deleted.**
  Branches, including the path-not-taken story made in the same transaction, share files by
  `content_ref`, so nearly every removed picture is still referenced. A file that no row
  references any more is left on disk; there is no file garbage collection.
* **Migration 0060** (`0060_rewind_snapshots`, `down_revision = '0058_story_checkpoints'`).
  `phase_snapshot` has an immutability trigger (0002). It now allows DELETE only when the
  transaction set `worldsim.rewind = on` (`set_config(..., true)`, transaction-local), and
  UPDATE stays forbidden. No other way existed: a later snapshot left behind would collide
  with the derived snapshot id of the replayed turn. **Merge:** re-chain 0060 onto a parallel
  0059 if one lands.

## What changed

* Backend:
  * `POST /stories/{id}/rewind` takes `{absolute_index}` and `Idempotency-Key`. It returns
    `saved_story_id`, `saved_title`, `role`, `removed_turns` and `replayed`. The same key and
    body replays the answer; the same key with another body is a 409.
  * `GET /stories/{id}/branch-points` now also returns `latest_turn`.
  * `application/stories/rewind.py`, and `checkpoints.rewind`, `prune` and
    `latest_completed`.
  * `beat_bench.py --keep-turns N` reports checkpoint storage.
* Frontend:
  * "Go back to this turn" sits beside "Branch from here" on Adventure turn headings, on the
    Watch feed and in the event view. It shows only for a kept turn before a kept newest turn
    (`canRewind`).
  * `BranchDialog mode="rewind"` explains what happens: the story continues from the end of
    this turn, the N later turns are removed from it and kept as a separate story you can
    open from Stories, and pictures still being painted are dropped. It names that story,
    then shows "Gone back" with "Open the path not taken" / "Carry on here".
  * The view then reloads the story in place (`load()` of `useAdventure` / `useObservatory`).
  * `IconRewind.vue`, `pathNotTakenTitle`.

## Verification

* `tests/test_story_rewind.py` has 6 tests. The real built-in vale is used, Wren is the
  player, and the model is a scripted fake.
  * **State equal to the checkpoint.** After 5 turns and a few pictures (a painted one of turn
    1, a painted one of turn 4, and one of turn 5 still painting), the story goes back to
    turn 2. Its state tables, world_config, observations and recent memories are then equal,
    row for row, to the dump taken right after turn 2. Its history up to turn 2 is
    byte-identical.
  * **Nothing later remains.** No later run, snapshot, event, scene, narration, attempt,
    reaction, resolution, model call, checkpoint or `phase:3..5` slot is left. Only turn 1's
    picture, job and asset remain.
  * **The path not taken** equals the pre-rewind state once its ids are renamed back. It has
    turns up to 5 and keeps the turn-4 picture file, and the pending painting was not copied.
    The Stories list shows it with its title and "Branched from … at Day 1, sunset".
  * **Untouched elsewhere.** A branch of the same story that shares a picture file is
    byte-identical before and after.
  * **Plays on.** Turns 3 and 4 play on the fake gateway. `branch-points` is then
    `[1,2,3,4]` with `latest_turn` 4.
  * **Refusals** (each leaves the story unchanged): the newest turn, a turn not played, no
    key (422), writing still running, the next turn's slot held, a missing checkpoint, and
    the newest turn not kept.
  * **Idempotency:** a replay returns the same saved story, and the same key with another
    body is a 409. Exactly one path-not-taken story exists.
  * **Autoplay** is paused with the detail "Went back to an earlier turn."
  * **Retention over 32 turns** (window lowered to 6 with monkeypatch): kept turns
    `[9,19,27..32]` equal `keeps_turn`. A branch from day end 9 succeeds; a branch from
    pruned turn 12 is refused with the plain message. Going back to day end 19 restores it
    exactly, salience included after day 3's bumps, and keeps daily summaries up to day 2.
    The saved story carries the same retained turns.
  * **Guard:** every table with a `world_id` is classified as state, history, extras or
    known. A new story table, such as the combat worker's, fails this test until it is added
    to `STATE_TABLES` or another list.
  * `test_retention_rule` checks the pure rule at turn 450.
* Full backend suite: 952 tests collected, 0 failed, 1 skipped (`-n 4`). Ruff check and
  format are clean, basedpyright reports 0 errors, and the TS client `--check` is clean.
  `test_story_branches` still passes. Its "not kept" case now goes through the
  pruned-or-missing distinction.
* Frontend: prettier, eslint and vue-tsc are clean. vitest: 473 passed, 1 skipped, including
  `canRewind` and `pathNotTakenTitle`. The vite build succeeds.
* Screenshots (headless Edge, scratch API on 8104 with the fake provider; `setup-story.mjs`
  then `rewind-shots.mjs`; results in `shots.json`, with no page errors):
  * `1-adventure-turn-actions`: each earlier turn has both actions; the newest has only
    "Branch from here".
  * `2-rewind-confirmation`
  * `3-gone-back`
  * `4-story-after-going-back`: only Day 1 sunrise and morning remain.
  * `5-stories-path-not-taken`
  * `6-watch-feed`
  * `7-confirmation-phone`

## Retention cost and storage (`beat_bench.py --cast 6 --beats 320 --cite 0.3`)

The bench was run twice on a throwaway database: once with the default window of 200, and
once with `--keep-turns 1000000`, which prunes nothing. Numbers are in `bench-retention.json`.

| | keep 200 + day ends | keep all |
|---|---|---|
| Checkpoints kept for the 320-turn story | 212 (200 + 12 day ends) | 320 |
| Stored (`pg_column_size`, compressed) | 1.51 MB | 1.89 MB |
| JSON size | 3.2 MB | 4.4 MB |
| `story_checkpoint` table on disk | 2.2 MB (pruned rows not yet vacuumed) | 2.4 MB |
| Checkpoint step (capture + prune), turns 201–320 | p50 16 ms, p95 32 ms, mean 23.7 ms | p50 16 ms, p95 32 ms, mean 22.5 ms |
| Prune alone, nothing to delete | 5.5 ms p50 (own transaction) | 5.9 ms |
| Beat wall p50 (fake model) | 2.05 s | 2.13 s |

The prune cannot be told apart from noise in a beat; it is about 1 ms of mean, inside a
2-second instant-model beat. Storage stops growing at about 10 checkpoints a day: past turn
200 each day adds one checkpoint instead of ten. At 320 turns that already saves 20% of what
is stored, and at 1 000 turns the story keeps 280 checkpoints instead of 1 000.

## Known gaps

* ~~Removed turns' model-call cost rows leave the story.~~ **Changed in review:** the
  model calls of removed turns stay, with their cost and manifest, and only their links to
  the removed run and task are cleared (a replayed turn derives the same run and task ids).
  The money was spent, so the story's spend must not drop on a rewind;
  `test_going_back_restores_the_turn_and_keeps_the_path_not_taken` asserts the cost rows and their
  sum are unchanged.
* Picture files nobody references any more stay on disk (no file garbage collection).
* An image job the runner is painting at the moment of a rewind may finish onto a deleted
  job row; its asset then has no picture pointing at it.
* Director/God seats (PlayView) do not show the action. It is player and watcher only, as
  briefed; the API serves any seat.
* Rewind holds the next turn's slot. A beat already waiting on a long model call in another
  process is caught by "newest turn not kept / still being written", not by the slot.
