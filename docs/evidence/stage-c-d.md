# Stages C+D — evidence (second review), 2026-09-20

## Stage C: frontend wiring

- **C1 contracts**: `content/schemas/openapi.json` (97 paths) +
  `content/clients/worldsim.ts` regenerated with the documented commands
  (byte-identical: no route/DTO drift from backend fixes). `src/api/http.ts`
  centralizes envelope errors, retryability, timeouts, story-scoped
  cancellation and idempotency headers; `src/api/worldsim.ts` types every
  operation off the generated DTOs (explicit world ids, roles; never the
  single-world path; creation never gated on world-count readiness).
  Auth: dev proxy injects the loopback operator key server-side
  (`vite.config.ts` reads root `.env`); source holds no credentials.
  Durable tests: `transport.spec.ts` (headers, envelope, retryable, cancel).
- **C2 presets+drafts**: `NewStoryView` runs all six steps on a persisted
  server draft (`?draft=`, localStorage fallback, PATCH per navigation,
  version-conflict refresh preserving input, explicit save, draft-rev
  indicator). Cast/world come from persisted presets only — starter
  Wren/Ash resolve to real portraits by name, anything else gets the neutral
  scene slot; the create-character tile stays local-only with an honest
  caption. Controlled-character invariant enforced with a visible warning.
  Pure payload builder tested in `drafting.spec.ts`.
- **C3 creation**: stable per-draft-version key, button disabled while
  pending, timeout retries the same key into the replay, then routes to
  `/stories/:storyId/play`. Draft id cleared only after acknowledgement.
- **C4 story view** (`/stories/:storyId/play`, role-aware): location, cast
  with live places, timeline feed, setup dialog, travel (character +
  destination from map routes; player locked to controlled) and one advance
  control per beat (same-index retry on timeout; 409 on travel reconciles
  the activity list instead of failing; story-scoped AbortController,
  late responses ignored). Dev-model beats labeled as deterministic.
- **C5 Home/Stories**: both read real records (`records.ts` mappers +
  `format.ts`, tested). Home hero/recent populate from the list (newest
  first); empty backend renders the composed empty hero — no fabricated
  tale. Library counts come from persisted presets. Shelf cards navigate to
  the room; the information action shows the immutable setup; archive
  round-trips with the metadata version. Card blurbs use real preset
  descriptions, never invented prose.

Gates: `vue-tsc` clean, `eslint` clean, vitest **59/59**
(drafting, format, records, transport, contract + existing suites).
Pre-existing note: this tree's earlier wizard referenced components that
never existed (`ThemeBand`, `IconBack/Next`) — mapped to the real
equivalents; stepper/toolbar APIs matched to actual props.

## Stage D: acceptance

Repo script: `scripts/journey.mjs` (zero dependencies; key from
`EMBER_VALE_API_KEY`). Fresh-database run (`down -v`/`up`, migrations
0001→0033 on empty): presets rev 2 with both legs → draft → atomic create →
same-key replay → Wren Hearth→Market committed → timeline agrees → retry
adds nothing → setup `created`. Post-restart run green; both stories listed
with day/phase intact (resume proven).

| Step | Result |
|---|---|
| Drop/recreate reference DB (documented compose path) | migrations to `0033`, seed advisory `worlds:0` |
| Start with Ember Vale + Wren/Ash (no demo shelf) | empty home; counts 1/2/1 from presets |
| Create with Wren@Hearth, Ash@Market; reload; resolve IDs; same creator | draft → story; replay same id; no duplicate on retry |
| Begin travel → UI/server acknowledgment; commit through advance | activity active → beat commits; map + timeline agree |
| Restart API; return: same story/day/phase; advance continues | both journeys intact; cursor advances |
| Browser: same journey at 1440 + 390 | `stage-c/` shots, no console errors |
| Failure: duplicate create (same key), timeout retry, 409 travel, stale draft save | pytest (`a06`, travel, revisions) + UI reconcile paths |

Screenshots (`docs/evidence/stage-c/`): `d-empty-home` (honest empty),
`c-home`/`c-stories` (real records), `c-wizard-world` (quickstart prefill),
`c-play`/`d-journey-play-1440`+`-390` (movement committed, feed, populated
destinations). Earlier `c-play-1440` shows the pre-fix probe story with an
empty destination list — kept as the before/after record for the
embedded-routes fix.

Known remaining behavior (documented, not claimed): review-suggested live
provider probe, director/deity product mapping (engine allows, UI offers
Observer/Player), studio backend (E5+), 200% zoom pass.
