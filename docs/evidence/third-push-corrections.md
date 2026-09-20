# Third-push corrections — evidence (R1–R10), 2026-09-20

Integration correction pass against `docs/reviews/Ember_Vale_Third_Push_Review_and_Guide.md`.
Styling and screenshots are untouched; no backend import, no live providers.

## Fixes by finding

- **R1 advance payload + generator**: `backend/scripts/gen_ts_client.py` now
  emits `| null` only when the schema explicitly permits null
  (anyOf/oneOf null variant or null type); omission renders as `?`.
  Regenerated `content/clients/worldsim.ts` (`--check` passes): e.g.
  `player_intents?: Record<…>` (no null), while genuinely nullable fields
  (`resolution?`, required `character_id: string | null` on RoleGrantView)
  keep theirs. `advanceStory` omits `player_intents` when there are no
  intents; `createDraft` passes payload through instead of `?? null`;
  `validateDraft` uses `DraftValidationView`. Other request DTOs reviewed:
  patch/create bodies were already non-null. Pinned server-side by
  `backend/tests/test_advance_optional_contract.py` (omit/empty accepted,
  null rejected for advance intents and draft payload) and by
  `src/api/worldsim.spec.ts` capturing the actual adapter bodies.
- **R2 guarded workflow**: `useStoryDraft.createWorkflow` sets its guard
  synchronously, persists selections+step, stops on failed save (zero create
  requests, input kept, conflict notice), validates the acknowledged draft,
  then submits frozen id/version/key with same-value timeout retry.
  In-memory key store sits in front of localStorage so storage failure
  cannot mint a fresh key mid-retry. Saves serialize through a chained tail;
  wizard navigation is disabled while busy/creating. Tested:
  failed-PATCH, stale-draft, invalid-draft, double-click-once,
  same-key-timeout-retry, chained-save-versions (`useStoryDraft.spec.ts`).
  Navigation moves optimistically then persists (serialized); failures
  surface a notice with input retained and the footer draft-rev shows
  staleness — creation alone hard-stops.
- **R3 dev proxy**: `vite.config.ts` binds `127.0.0.1` by default with no
  `allowedHosts` wildcard; wider binds need explicit `EMBER_VALE_DEV_HOST`
  (file or process env) plus their own access control. Pinned by
  `src/devserver.spec.ts` asserting the effective config. Verified live:
  `npm run dev` printed only `http://127.0.0.1:5173/`, `/` served 200 on
  loopback, and `/api/v1/library/presets` returned data with no client
  credential (proxy injection intact).
- **R4 identity/role**: the room loads GET `/stage2/roles` (new `getRole`)
  and matches `grant.character_id` directly against map occupant ids — no
  name inference. Travel syncs to the controlled id when the grant resolves
  (Ash sorting first no longer wins). Player mutation buttons stay disabled
  until the grant loads. The "View as" dropdown is gone: the badge shows the
  grant-derived effective role read-only. Backend enforcement untouched.
  Tested: grant-over-alphabet, header role/character on advance,
  missing-occupant honesty via `controlledMissing` notice.
- **R5 feed**: `useStory` pages through `next_after`/`has_more` (50/page,
  25-page cap, dedupe by `event_id`, zero-entry pages still followed),
  refreshes incrementally from the cursor after beats, and shows an honest
  "showing N of M" line if the cap ever hits. The room shows the development
  model profile line, same as the wizard.
- **R6 transport**: only a real outer-signal abort reports
  `REQUEST_ABORTED`/cancelled; network failures and unreadable bodies report
  retryable `REQUEST_TRANSPORT`; timeouts keep `REQUEST_TIMEOUT`. A cancelled
  client request no longer implies anything about the server mutation.
  Tested: outage, body failure, timeout, native AbortError (`transport.spec.ts`).
- **R7 activities**: `listActivities` returns the generated
  `ActivityListResponse` (`members`). 409 reconciles actor+kind+destination
  against active members and otherwise surfaces the genuine backend message;
  timed-out starts reconcile before any retry (single POST asserted).
- **R8 lifecycle**: `useStory` takes a reactive story id, every state update
  is generation-guarded, mutations carry the story signal and stay pending
  through refresh; `App.vue` remounts the room per story id (other routes
  keyed by path, so `?draft=` doesn't reboot the wizard). Tested: A→B with a
  hung A (late response ignored, advance sends B, open recorded for B only).
- **R9 wizard**: starts at World (step 1), restores the persisted
  `current_step` (defined as the visible step), Quick Start lands on Review
  with prefilled+saved choices and an explicit notice, pinned older world
  revisions are fetched and shown (places dropdown + notice), completed
  drafts redirect to their existing story, boot is generation-scoped.
- **R10 continuation**: room entry records one explicit `openStory` per
  story (last_played_at advances without gameplay; asserted once-per-story
  in tests); Home's Continue hero and recent list exclude archived stories
  (never-opened sort last, matching the "Last played" label); archived tales
  remain behind the shelf's archived filter.

## Acceptance evidence

- Frontend: 85/85 vitest pass (15 files), `vue-tsc --noEmit` clean,
  `eslint .` clean, `prettier --check` clean on touched files.
- Backend: `test_advance_optional_contract.py` 4/4; full suite green from
  the repo root (exit 0, 2 pre-existing skips, zero failures). Note: the
  suite must run from the repo root — `content/dnd/*.json` resolve via a
  relative path, so a `backend/`-CWD run fails with FileNotFoundError.
  That CWD mistake caused a false alarm during this pass; it is not a code
  regression.
- Journey create: ok (world rev 2, travel→beat committed, same-beat replay
  stable, null-intents probe rejected with 422, artifact written).
- API restarted without DB reset; journey resume: same story resumed
  (clock/location/cursor matched), continued with a new beat, second story
  created, B's beat added nothing to A.
- Browser click-through of Player/Observer advance, travel, reload and the
  failure paths remains manual (no browser automation in this environment);
  the faulty paths are covered by the composable/adapter specs above.
