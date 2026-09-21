# E6 Director/God interventions — evidence, 2026-09-21

First E6 vertical slice: the backend queue existed with no frontend
surface and no queue tests. Scoped to seats + queue UI and queue proof;
no styling changes (existing `play__` tokens only), no orchestration
redesign.

## What shipped

- `src/api/worldsim.ts`: typed `selectSeat`, `submitIntervention`
  (caller-supplied idempotency key), `listInterventions`,
  `readIntervention`, `editIntervention` (version-checked),
  `cancelIntervention`.
- `src/composables/useInterventions.ts` (+ 6-test spec): queue state,
  submit with a fresh key, `retry()` reusing the failed key so a
  transport failure replays instead of duplicating, clarification and
  failure notices, stale-edit reload, cancel, mid-flight dispose.
- `src/views/PlayView.vue`: operating-seat card (Director/God seats via
  `POST /stage2/roles/select`; never offered while a player seat is
  bound; mid-run switches surface the server refusal) and a direction
  panel (file with seat-fixed mode, queue with step states, edit before
  claim, cancel before application). Badge reflects the grant seat.
- `content/clients/worldsim.ts`: regenerated via the sanctioned
  generator after adding the omitted `InterventionEditRequest` to its
  WANTED list (+6 lines, no other drift; `gen_ts_client.py --check` was
  green before and after).
- `backend/tests/test_intervention_queue.py` (8 tests): deity travel
  queues/chains/applies (activity started, step completed), same-key
  resubmission replays with no duplicate steps, multi-leg chaining via
  `after_seq`, role/mode enforcement (watcher forbidden, director
  force mismatch, director travel fails with God-mode note),
  clarification on unmappable output, edit version conflict, cancel
  preserves history, spar directs an attempt for advance, world
  condition persists.

## Live walkthrough (`director`, 5 steps, all passing)

Seat grant → file → deterministic `needs_clarification` (the dev
gateway returns fixed beat JSON, never a plan) → edit bumps to v1 →
cancel → return to observer. No fake success anywhere.

## Gates (observed this session)

- `npx vitest run`: 17 files, 121 tests, all passed.
- `npx vue-tsc --noEmit`: exit 0. `npx eslint` on touched files:
  exit 0. Touched `src` files prettier-clean.
- Backend: 18 passed (8 new + director/roles neighbors); `ruff
  check` clean on touched files.
- `node scripts/walkthrough.mjs`: exit 0, WALKTHROUGH PASSED.

## Honest gaps (not redesigned this turn)

- `claim_for_boundary`/`apply_batch` have no callers: queued items do
  not drain into beats yet. Live execution proof is service-level;
  drain-on-advance wiring is the next backend step.
- Model plans cannot supply `snapshot_id`/`character_id` inside
  `direct_attempt.action` (the interpret prompt never mentions them),
  so live attempts always clarify; validation requires what apply
  defaults. Flagged, not changed.
- Pre-existing, untouched: prettier flags 3 files I did not modify
  (`HeroCard`, `SetupDialog`, `StoriesView`); `ruff format` flags one
  pre-existing generator line.
