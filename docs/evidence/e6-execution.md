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
  the drain; completed steps are skipped; travel reuses the running
  activity; hooks/titles, condition labels, and deterministic
  override keys collide instead of duplicating.
- Restart cannot lose: stranded EXECUTING items re-list; per-step
  first-writer gate rows plus verify-or-apply effects re-derive the
  outcome; attempts stay queued until a beat records them.
- Concurrency: beats serialize per world+phase in `guarded()`; claim
  and step writes are version-guarded; gate rows converge appliers.
- Attempts complete only with the scene event as proof — never when
  merely returned to the caller.
- Travel start vs arrival: the step completes with
  `result_activity_id` when the journey starts; arrival is the
  activity completing on a later beat, observed via the map.

## 3. Submission identity (useInterventions)

Pending filings freeze owning world + seat header. A fresh key is
refused while one is unresolved; retry is refused after a world or
seat change; inspecting a filed item reconciles; `discardPending()`
is the explicit path to filing anew (Discard button next to Retry).

## 4. Interpretation contract (server-side identities)

Attempt validation defaults the actor from the step and checks shape
with a nil snapshot that never persists; `plan_attempts` stamps the
sealed snapshot and actor before real adapter validation. Model
output never needs technical IDs. Genuine ambiguity (unknown actor,
destination, scope) stays clarification.

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
- Gates: vitest 125/125, `vue-tsc` clean, eslint clean, touched
  `src` prettier-clean; backend 13 intervention + 30
  orchestration-neighbor tests green; `ruff check` clean on touched
  files (one pre-existing E501 left alone); walkthrough PASSED.

## Remaining gaps (stated, not redesigned)

- A crash between scene commits re-runs the whole beat on retry;
  scene re-commit idempotency there is pre-existing beat behavior
  covering player intents equally — directed steps converge via
  deterministic intent ids and conflict-tolerant marking, but event
  duplication on mid-commit retry is not newly proven.
- The dev gateway never returns a plan, so the browser walkthrough
  still exercises submit/clarify/edit/cancel only; live execution
  proof is the deterministic integration above, per direction.
