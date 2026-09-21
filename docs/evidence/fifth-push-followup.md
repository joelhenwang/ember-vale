# Fifth-push follow-up — evidence (departure races + evidence gaps), 2026-09-21

Follow-up against the lead's two-race review note on top of
`docs/reviews/Ember_Vale_Fifth_Push_Review_and_Guide.md`.
No backend changes, no styling changes.

## 1. Stale save clearing newer recovery (reproduced, fixed)

Recovery snapshots now carry the canonical snapshot they cover.
A successful save clears the entry only on exact-snapshot match, so a
delayed older PATCH resolving after newer edits were snapshotted retains
the newer entry; the covering save clears it. Legacy entries without a
snapshot token are validated out and hygienically cleared.

Regression (`useStoryDraft.spec.ts`): hold Older PATCH → snapshot Newest
via the leave path → release → server holds Older, recovery still reads
Newest → covering save clears to null.

## 2. Leaving during creation can no longer redirect (fixed)

- `useStoryDraft.dispose()` invalidates the controller lifecycle on view
  departure/disposal. Already-issued server operations still complete and
  reconcile their owning draft's receipts; completions change no mounted
  state.
- The wizard calls `dispose()` in `onUnmounted`, and `create()` returns
  without navigating unless the current route is still the wizard *and*
  the mounted draft is still the workflow's owner.
- Regression: held create → dispose → release with success resolves null
  with the receipt reconciled and no error.
- Browser (`createleave`, deterministic via `docker pause` held response):
  Begin → Creating… → Home → release → the user remains Home.

## Evidence gaps closed

- The reopened-wizard test now stubs persistent storage and resets module
  memory mid-test (simulated full reload): the new controller recovers the
  receipt from storage and replays the original ID/version/key with zero
  PATCHes.
- The dirtynav post-failure block now edits the title *after* the failure
  before leaving; reopen asserts the newest title value plus the cast
  count.

## Gates

- Frontend: 113/113 vitest (16 files), `vue-tsc` clean, `eslint` clean,
  Prettier clean on touched files.
- Walkthrough: 29/29 live checks green (headless Edge, dev server +
  compose stack), results in `docs/evidence/walkthrough/results.json`.
  Two flakes met during the run were scenario bugs, not product bugs: a
  post-restart wait that was too short, and an assertion looking for
  step-2 text on the restored step-4 view.
- Backend: unchanged, no rerun.
