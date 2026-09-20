# Delivery B (backend slice) — journey evidence, 2026-09-20

Frontend wiring (Library/New Story/Home/Stories/story view) is still open;
this slice proves every backend path that wiring will call, against the
running compose stack (db `embervale_app`@localhost:5433, api :8101, head
`0032_starter_travel`).

## Inherited travel gap — fixed and tested

- `backend/.../library/builtins.py`: starter world now declares directed
  `travel=[["hearth","market"],["market","hearth"]]` (was `[]`).
- `backend/.../stories/create.py` (`_materialize_travel`): each pair is
  validated (two known endpoints, no loops, no duplicates) and persisted as a
  `travel_route` row (duration 1 phase, 0 stamina) INSIDE the creation
  transaction — bad travel fails creation with no partial world.
- `backend/migrations/versions/0032_starter_travel.py`: seed-content
  correction updating the existing world builtin rev-1 payload (only rows
  still carrying `"travel": []`; content_hash `builtin-v1`→`builtin-v2`).
  Fresh installs converge through 0030→0032; `builtins.py` agrees for
  `ensure_builtin_presets`.
- `backend/tests/test_story_travel.py` (4 tests): both directed legs
  materialize with (1, 0); a created leg serves a real `start_activity`
  TRAVEL (Wren Hearth→Market); unknown endpoint rolls creation back
  (catalog count unchanged, draft unconsumed); migrated seed revision itself
  carries both legs.
- Results: `test_story_travel` + `test_revamp_a06` (atomic/idempotent
  creation) **9 passed**. `alembic check` clean at single head `0032`.
- Ruff: changed files clean (`ruff check` + `format --check`). Full-tree
  `ruff check backend` reports 17 errors, ALL in untouched vendored files
  (interventions.py, ports/repositories.py, revamp/s5 tests) — pre-existing
  donor lint debt under the resolved ruff version, left alone deliberately.

## Live HTTP journey (dev DB, scripts in scratch, not repo)

1. `GET /stories?status=all` → `[]` (true empty state, no seeded play history).
2. `POST /story-drafts` (Ember Vale rev 1, Wren@hearth, Ash@market, watcher)
   → draft v1.
3. `POST /stories` + `Idempotency-Key: e2-first-<run>` → 200, role watcher,
   `replayed: false`.
4. Same key replay → 200, `replayed: true`, same world id (no duplicate).
   A reused key with a DIFFERENT draft correctly conflicts (observed).
5. `POST /world/phases/advance` → 200, `event_cursor: 2`, not a replay.
6. `GET /world/events` → `world_seeded(1), world_ticked(2)`.
7. `docker compose restart api` → ready at `0032` (status flipped
   `degraded`→`ready` once a world exists — confirming the seed check is
   world-count advisory, not an onboarding gate).
8. Resume: story `A Morning in Ember Vale` day 1 sunrise intact; advance
   again → cursor 3; `/stories/{id}` + `/stories/{id}/setup` (provenance
   `created`, hash `608f7a2ea2cf`) agree.
9. `GET /library/presets` → 5 builtins; world rev 1 serves the fixed travel
   pairs over HTTP.

## Dev-DB note

One probe story ("A Morning in Ember Vale", watcher) remains in the local
compose database from this verification. It is probe data, not seed: fresh
installs still start with an empty shelf (step 1 above was observed empty).

## Still open (frontend slice)

Generated TS contract (`content/schemas/openapi.json` +
`content/clients/worldsim.ts` via `make contracts` equivalent), draft
persistence in New Story, Home/Stories on real records + empty state, story
view with advance control, failure/concurrency UI states, journey
screenshots. No UI files were changed in this slice.
