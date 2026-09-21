# Fourth-push corrections — evidence (P1/P2 + browser), 2026-09-21

Follow-up against `docs/reviews/Ember_Vale_Fourth_Push_Review_and_Guide.md`.
No backend changes this pass; styling untouched except functional additions
(Load-more button, save-state footer, notices).

## Fixes by finding

- **P1 frozen mutation context** (`src/composables/useStory.ts`): advance
  and travel freeze an immutable operation context (world, index/args,
  role, actor, generation, signal) at start. Attempts, timeout retries and
  reconciliation use only that context. A timeout retries only while its
  own generation is still current — never after navigation or disposal.
  Travel reconciliation reads the operation's own world (its notice is
  dropped if the room moved on, so B never shows A's message; re-entering
  A reloads committed state). `cancel()`/new `load()` always release
  advancing/traveling flags. Regression tests: A-timeout→B (no B request),
  timeout-after-disposal (no retry, flags clear), same-story retry (frozen
  world/index/role/actor), reconcile-scoped-to-A, re-entry without
  duplication (`useStory.spec.ts`, 16 tests).
- **P2 history cap** (`useStory.ts`, `PlayView.vue`): explicit “Load older
  history” continuation from the stored cursor (25×50 per continuation);
  a cursor that stops progressing with nothing new terminates instead of
  looping. Copy no longer mixes visible entries with source totals
  (“Showing N loaded events” + “Older history remains on the server”).
  Tests: 1,300-event source reached via Load more, empty advancing page,
  stuck cursor (2 requests, returns).
- **P2 pinned presets** (new `usePinnedPresets.ts`, wired into the wizard):
  request identity frozen before fetch, generation-guarded, results keyed
  by preset ID _and_ revision; failures are explicit errors that block
  Begin (no silent latest substitution; location selects lock). Older
  pinned character revisions resolve for display; latest stays live for
  browsing. World changes adopt the latest revision deliberately, reset
  invalid starting places via the tested `rehomeInvalidLocations` rule,
  name the reset, and persist. 7 composable tests + 1 drafting test cover
  slow-A/B, failed loads, shared revision numbers, old char revs.
- **Wizard durability** (`useStoryDraft.ts`, `NewStoryView.vue`): saveState
  clean/saving/unsaved/failed against a canonical acknowledged snapshot;
  footer shows saved/unsaved/failed states with a Retry action; beforeunload
  guards unsaved work; failed saves store a timestamped local recovery
  draft that boot restores when newer than the server state; Quick Start
  checks its persist and never claims undurable prefill; `?draft=` changes
  reboot the wizard for the new draft (own first assignment excluded).
  Queued saves were already synchronous via the chained tail.
- **Body-read identity** (`src/api/http.ts`): timeout/cancellation during
  body consumption keeps its classification (mutation recovery selects on
  REQUEST_TIMEOUT); only malformed bodies are transport errors. Tested for
  stalled-body timeout and mid-body abort.
- **Frozen submission retention** (`useStoryDraft.ts`): a doubly-timed-out
  create keeps its frozen values; the next Begin replays them (same
  version/key, zero PATCHes) instead of a fresh save that could
  double-create. Definitive failures clear the ambiguity. Tested.
- **Journey cursor semantics** (`scripts/journey.mjs`): the artifact now
  records source `next_after`/`total` alongside the entry count; resume
  asserts all three (legacy artifacts without them still verify by count).

## Live bug found by the browser

The first walkthrough probe rendered only the top bar: Vite returned 500
for `NewStoryView.vue` — Prettier had split a multi-statement `@click`
across lines without its semicolon. Fixed by extracting `chooseWorld()`;
all other templates were scanned for the same pattern (none found) and a
route-compile gate (all routes, no 500s) is now part of the walkthrough.

The same probe caught a stale server-validation issue on a filled Review
(validate raced the Quick Start save); step-6 saves now revalidate, and
the walkthrough asserts zero stale issue blocks.

## Browser evidence (recorded, not claimed)

`node scripts/walkthrough.mjs` (headless Edge via playwright-core against
the dev server + compose stack) — 21/21 checks in
`docs/evidence/walkthrough/results.json`, with room/review screenshots:

- observer: Quick Start review → Begin → Wren travel → beat 1 commits →
  Wren in Market → 5 feed events → reload continues → Home features it.
- player: grant badge “Player”, “Playing as Wren”, Who locked to Wren
  (Ash sorts first), movement commits.
- failedsave: API stopped mid-wizard → failed state with input kept →
  Retry offered → API restarted → retry saves (“· saved”).
- routes: / /new-story /stories /library /settings compile with no 500s.
- narrow (390px): review + room render, screenshots kept.

HTTP journey: fresh create (null-intents 422 probe included) then API
restart and `--resume` — clock, location, entry count _and_ source
cursor/total matched; story continued; second story's beat added nothing
to the first.

## Gates

- Frontend: 106/106 vitest (17 files), `vue-tsc` clean, `eslint` clean,
  Prettier clean on touched files.
- Backend: unchanged this pass; suite green from the repo root last pass.
- New dev dependency: `playwright-core` (driver only; uses installed Edge,
  no browser download) for the committed walkthrough.

Covered by focused tests rather than live browser, as agreed with the
review's scoping: pending-A-advance-then-B-timeout, older-preset failure
paths, and beyond-cap history. The walkthrough records exactly which
scenarios ran live.
