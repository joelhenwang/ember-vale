# Complete recovery across save → edit → leave → reopen — evidence, 2026-09-21

Supersedes `recovery-version-arbitration.md` (intermediate state); the
creation-departure finding stays closed. Scoped to recovery ownership
and restoration: no backend changes, no styling changes, no new
features.

## Mechanism

- `RecoveryDraft.baseVersion`: the acknowledged server version the
  snapshot's local edits build on. Timestamps are display-only; no
  decision reads `at` or `updated_at`.
- `latestSeen`: the most recently seen local edit snapshot (canonical
  content token) per draft, updated on every `save()` enqueue and every
  `storeRecovery()` write. The token establishes content equality, not
  chronological recency — editing A → B → A returns the same token.
  What the failure path needs is seen-order: a leave snapshot written
  after a save was enqueued supersedes it, so a delayed save's failure
  handler stores its own snapshot only when nothing newer was seen
  since. An older operation neither overwrites newer recovery nor makes
  it ineligible for restoration, on success (exact-snapshot clear) or
  failure alike.
- `planBootRecovery(server, recovery)` is the wizard's actual
  restoration logic, shared by the view and the tests: `none` (nothing
  stored), `covered` (server already holds the edits → clear the
  entry), or `restore` with the kept selections plus a `conflict` flag
  and the preserved server state.
- Conflict choice (`NewStoryView.vue`): the kept choices display
  immediately; both versions are preserved and the wizard offers Keep
  my kept choices (stay local, entry still clears only via a covering
  save) or Use server version (re-hydrate the retained server state,
  discard the entry). Built from the existing `nsv__world`
  option-button pattern — no new styling.

## Sequences (regressions in `useStoryDraft.spec.ts`)

Each test clears module memory with `resetDraftMemoryForTests()`,
retains persistent storage (stubbed `localStorage` map), creates a
fresh controller, and drives `planBootRecovery` — the function the
wizard boots with:

- Delayed success: submit Older → edit Newest → leave → Older commits
  at v2 → reopen plans `restore` + `conflict` with selections titled
  Newest and the Older server payload preserved → save Newest →
  server holds the Newest payload, recovery entry null → second reopen
  loads the draft from the server with plan `none`.
- Delayed failure: same shape with the Older PATCH failing → reopen
  onto the unchanged v1 server plans `restore` without conflict →
  save Newest → server holds it, entry clears → second reopen loads
  from the server.
- `planBootRecovery` marks server-held edits `covered`.

## Gates (observed this session)

- `npx vitest run`: 16 files, 115 tests, all passed.
- `npx vue-tsc --noEmit`: exit 0. `npx eslint` on touched files:
  exit 0. `npx prettier --check` on touched files: clean.
- `node scripts/walkthrough.mjs` against the live stack: exit 0,
  WALKTHROUGH PASSED, including `dirtynav` leave/reopen restore,
  post-failure edit, `createleave`, and `failedsave` scenarios.
