# E6 execution: directions drain through beats — evidence, 2026-09-21

Follow-up to `e6-director-interventions.md` against the review of
0d559782. The queue now executes through the normal advance endpoint
with interruption and retry guarantees. Recovery correction stays
closed; no styling changes.

## 1. Honest UI (PlayView)

The panel states what the build does: directions submit/edit/cancel;
queued directions apply when beats commit; starting travel begins a
journey and arrival follows when it completes. The `advance()`
comment describes the real flow (drain during the beat, re-read
after). The interim "not available yet" copy was replaced by
connected behavior in the same slice.

## 2. Queue execution inside beat advancement

`POST /stage1/advance` no longer claims/applies before the beat.
`advance_phase(..., drain_queue=True)` drains past its duplicate
replay: claim (QUEUED→EXECUTING, version-guarded; conflicts are
owned elsewhere and skipped), pre-decision effects, post-seal
attempt planning merged into the decision, and attempt completion
recorded per scene commit with the committed event id.

- Beat replay cannot double-apply: the duplicate path returns before
  the drain; completed steps are skipped; every effect carries a
  durable per-step identity, so a replayed step adopts its recorded
  outcome instead of duplicating it — activities by `direct_step_key`
  (migration 0034), hooks/arcs by the step's command receipt,
  overrides by step-derived idempotency keys, conditions by
  `source_step_key` (migration 0034). Titles and labels are display
  text and never identify an effect.
- Restart cannot lose a recorded effect: stranded EXECUTING items
  re-list; the per-step gate (`direct:<step>:<seq>`) elects one owner
  and rolls its session back on conflict; recovery re-derives through
  the per-step receipts above, which read across every status — an
  interrupted, completed, or expired effect still proves its step.
  Attempts stay queued until a beat records them.
- Concurrency: beats serialize per world+phase in `guarded()`; claim
  and step writes are version-guarded. Overlapping appliers of one
  step converge by database identity: two appliers held inside the
  effect window together persist exactly one travel activity (proven
  at controlled barriers); hook/arc races collide on the step's
  command receipt; override races collide on the step-derived key;
  condition races collide on `source_step_key`. The loser adopts the
  winner's recorded effect in every case.
- Attempts complete only with the scene event as proof — never when
  merely returned to the caller.
- Travel start vs arrival: the step completes with
  `result_activity_id` when the journey starts; arrival is the
  activity completing on a later beat, observed via the map.

## 3. Submission identity (useInterventions)

Pending filings freeze owning world + seat header. A fresh key is
refused while one is unresolved; retry is refused after a world or
seat change; selecting an item reconciles pending only when its
`client_request_id` and world match the filing — selecting an
unrelated direction preserves Retry/Discard; `discardPending()` only
stops tracking the local filing (it never cancels a possibly accepted
server operation) and is the explicit path to filing anew.

## 4. Interpretation contract (server-side identities)

Attempt validation stamps the step's actor and a nil snapshot over
any model-supplied values, then validates shape with the outer family
last, so model JSON cannot choose authority; `plan_attempts` stamps
the sealed snapshot the same way and reserves the actor, so a second
attempt for one actor fails deterministically instead of silently
overwriting. Model output never needs technical IDs. Genuine
ambiguity (unknown actor, destination, scope) stays clarification.

## Acceptance (all observed)

- HTTP (`test_intervention_advance.py`, deterministic
  name-resolving director gateway, dev stand-ins elsewhere): submit
  "Send Wren to Market" → queued → advance 1 → completed with
  activity → advance 2 → Wren at Market → duplicate replay untouched
  (version-stable) → queue empty. Cancel-before-application applies
  nothing. Player directing others is 403.
- Service (`test_intervention_queue.py`): interruption recovery
  without loss/duplication, same-key replay, player-own spar with
  server-stamped identities, chaining, enforcement, clarification,
  edit conflict, cancel, plague persistence.
- Gates (re-run 2026-09-21, default sandbox, no live stack needed):
  vitest 126/126 across 17 files, `vue-tsc` clean, eslint clean;
  backend 69/69 across the execution-identity file (10),
  intervention advance + queue (13), stage1 orchestration + api (17),
  scene commit (6), s2 director + roles (10), db migrations +
  activities (6), s2 activity (7); `ruff check` clean on all touched
  files; `gen_ts_client.py --check` clean. Walkthrough PASSED
  (inherited from the previous push, not re-run).

## Remaining gaps (stated, not redesigned)

- A crash between scene commits re-runs the whole beat on retry;
  scene re-commit idempotency there is pre-existing beat behavior
  covering player intents equally — directed steps converge via
  deterministic intent ids and conflict-tolerant marking, but event
  duplication on mid-commit retry is not newly proven.
- The dev gateway never returns a plan, so the browser walkthrough
  still exercises submit/clarify/edit/cancel only; live execution
  proof is the deterministic integration above, per direction.

## Follow-up: E6-A..E6-D corrections, E6-C completed (2026-09-21)

E6-A, E6-B and E6-D stand as implemented in commit a9a96a9: stamped
actor/snapshot/family at validation and plan time; deterministic
actor reservation; pending reconciled by `client_request_id` + world.
Recovery and creation-departure stay closed.

E6-C is now finished with durable per-step effect identity plus
result retrieval independent of active status:

- Migration 0034 adds `activity.direct_step_key` (backfilled from
  payload) and `world_condition.source_step_key`, each guarded by a
  partial unique index. Lookups (`get_by_direct_step_key`,
  `get_by_step_key`) read across every status, so an interrupted,
  completed, or expired effect still proves its step. Labels and
  titles are display text only.
- Racers collide on the step identity and adopt: activities roll back
  and adopt the winner on `uq_activity_direct_step_key`;
  hooks/arcs collide on the step's command receipt; overrides collide
  on the step-derived key; conditions roll back and adopt on
  `uq_condition_source_step_key`.
- Fixed along the way: `_claim_step_gate` rolls back on
  `IDEMPOTENCY_CONFLICT` (a caught integrity failure still poisons
  its transaction — without this the caller's commit raised
  `PendingRollbackError`); the asyncpg constraint-name walk is shared
  in `repositories/_common.py` (`unique_violation`).
- Three regressions in `test_intervention_execution_fixes.py` (now
  10 tests): same-label condition steps in one intervention keep
  separate scopes/severities/step keys, and reapplying a step whose
  condition went inactive adopts it (2 conditions, never 3);
  an interrupted activity is adopted by id with no second activity;
  two appliers held at controlled barriers inside the effect window
  together (call assertion proves the overlap) persist exactly one
  activity.

Verified interruption/concurrency boundaries: gate-taken-then-apply;
effect-persisted-but-unmarked (adopted); hook overlap (adopted);
same title/label across filings (separate); same label within one
filing (separate); inactive-effect adoption for activities and
conditions; genuine overlap at barriers; override key replay;
cancel-before-application and unauthorized/player cases via the
preserved HTTP/service suites. Explicitly NOT covered: crash between
scene commits (pre-existing beat behavior, see Remaining gaps);
live-provider prose; browser execution of directions (the dev gateway
returns no plans, so the walkthrough still covers
submit/clarify/edit/cancel only).
