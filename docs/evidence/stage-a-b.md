# Stages A+B — evidence (second review), 2026-09-20

## Stage A: preset revision repair

Problem: 0032 rewrote world builtin rev 1 in place (`builtin-v2`), breaking
revision identity. Fix: corrected starter ships as **rev 2**; rev 1 is history.

- `backend/.../domain/presets.py`: new `canonical_payload_hash` — the single
  canonical algorithm. `routes/library.py` delegates its `_hash` to it;
  `builtins.py` uses it for new revisions.
- `backend/.../library/builtins.py`: `builtin_definitions()` again returns the
  original rev 1 set (travel `[]`); new `builtin_revision_updates()` defines
  world rev 2 (Hearth↔Market legs) and template rev 2 (pins world rev 2);
  `ensure_builtin_presets` converges missing rows/revisions without rewriting
  (fresh inserts start at `current_revision` 2; bumping pre-existing readonly
  rows stays migration-managed).
- `backend/migrations/versions/0033_preset_travel_rev2.py`: restores a
  0032-mutated rev 1 to exact 0030 content (guarded by hash+payload predicates;
  anything else untouched), inserts world+template rev 2 with frozen canonical
  hashes (`06f664…`, `d2dc3b…` — independently recomputed in tests), sets
  `current_revision` 2 where rev 2 exists. Downgrade removes rev 2 rows and
  resets current to 1; it never touches rev 1 content either way.
- Characters/style presets unchanged; world/template/character numbers kept
  distinct; drafts keep exact revision refs (no silent upgrade).

Upgrade matrix (`backend/tests/test_preset_revisions.py`, 3 tests):
fresh head (rev1 original + canonical rev2, template pins 1→1/2→2, ensure
repeatable with zero additions), pre-0032 DB with draft+story (rev1 untouched,
snapshot byte-identical, draft still rev 1, new rev-2 story gets legs),
post-0032 DB with draft+story (rev1 restored, snapshot byte-identical, draft
refs preserved — documented ambiguity: mutation-window drafts now resolve the
restored original).
Live dev DB (had 0032 applied): migrated 0032→0033, rev1 `travel: []`,
`current_revision: 2`, old probe story intact.

Related fixes found while proving the paths:
- `repositories/stories.py::save_draft` never persisted `created_world_id`,
  so consumed drafts could create again under a new key. Now persisted;
  covered by `test_consumed_draft_cannot_create_again` (403 FORBIDDEN, one story).
- Same-key commit race could surface 403/409 to the loser instead of
  replaying. `create_story` now re-checks the receipt after a consumed-draft
  read and after a VERSION_CONFLICT inside instantiate (genuine conflicts
  still raise). Concurrency test: 2/6 failures on old code → 8/8 green plus
  full trio green repeatedly (pre-existing race, now closed; both outcomes
  verified by stash/restore experiment).
- Invalid travel tightened: 422 `VALIDATION_FAILED` envelope plus unchanged
  world/location/route/draft row counts (no orphans).
- Creation now also embeds directed `Route` records on locations (the map
  reads embedded routes, the rules read `travel_route`); both carry the same
  legs. Map test asserts Hearth→Market route renders.

Results: preset_revisions + story_travel + travel_completion + a06 + tx +
stage0/1 gates + scene_commit + migrations + seed + uow + leases —
**56 passed, 1 skipped** (opt-in live case), plus 8/8 concurrency loop.

## Stage B: orchestration decision + completed-travel proof

Decision (traced, not assumed):
- UI “Advance” = `POST /stage1/advance {world_id, absolute_index}`. The Stage 1
  orchestrator seals state, runs decisions/reactions/resolution/narration,
  ticks conditions and completes due activities — one atomic beat per index,
  idempotent replay via the phase-run guard. No extra Stage 0 tick (that route
  stays infrastructure-only; calling both would double-advance the clock).
- A travel action = `POST /stage2/activities {kind: travel, to_location_id}`
  (leg validated synchronously; one active activity per character), completed
  by the next stage1 advance (`ACTION_RESOLVED` + `MoveEntityEffect`,
  activity → COMPLETED under an `activity_complete:` idempotency key).
- Watcher headers drive the test; the engine grants watchers
  MANAGE_ACTIVITIES+ADVANCE. Mapping that onto Observer/Director product
  powers is E5/E6 work, documented here as a known reconciliation item.

`backend/tests/test_travel_completion.py` (10 review steps): rev-2 draft →
atomic create → Wren@Hearth verified → travel submitted/committed → stage1
advance → fresh session shows Wren@Market, Ash still Market, activity
terminal, `action_resolved` with effects, clock advanced → same-index retry
changes nothing → timeline shows the outcome, map shows Wren in Market with
the Hearth→Market route. Deterministic fake models with WAIT decisions and
one scripted narration beat; the frontend must label dev generation as such.

## Open (Stages C+D)

Frontend wiring (contracts, presets/drafts, creation, story view,
Home/Stories) and the repo-committed journey script + browser evidence.
No Vue files changed yet. Dev DB holds one watcher probe story from the
first push; fresh installs still start empty (proven at the HTTP layer).
