# Recovery version arbitration — evidence (creation-departure follow-up), 2026-09-21

Follow-up against the lead's single remaining recovery finding: the
save → edit → leave → reopen sequence was still decided by wall-clock
timestamps (`recovery.at > server.updated_at`), with two unprotected
branches. No backend changes, no styling changes.

## 1. Success branch (reproduced, fixed)

Ordering: submit Older (01:00:00) → leave with Newest recovery
(01:00:01) → server commits Older (01:00:02). On reopen the timestamp
comparison is false, so the wizard ignored Newest even though the
server holds Older, not Newest.

Fix: recovery entries now stamp `baseVersion` — the acknowledged
server version the snapshot's edits build on. Reopening arbitrates via
`resolveRecovery(serverPayload, serverVersion, recovery)`:

- server payload already equals the recovery's rebuilt payload →
  `covered`, entry cleared;
- otherwise the outstanding local edits restore; when the server moved
  past the base version with different content the wizard says so
  explicitly (`conflict` notice), never silently drops them.

## 2. Failure branch (reproduced, fixed)

The same ordering with the Older PATCH failing: the catch handler
called `storeRecovery()` with Older, overwriting the Newest leave
snapshot.

Fix: a per-draft `latestSeen` snapshot, updated on every `save()`
enqueue and every `storeRecovery()` write. A failure stores its own
snapshot only when it is still the latest — the newer leave snapshot
wins, just as on the success path. Sequential failures still work: a
later save updates `latestSeen` at enqueue, so its failure stores.

## 3. Regression coverage (`useStoryDraft.spec.ts`)

- Delayed success through a fresh controller + reopen: Older commits
  at v2 after the Newest snapshot → decision is `conflict`, stored
  title reads Newest → saving Newest clears to null.
- Delayed failure through a fresh controller + reopen: Older PATCH
  fails after the Newest leave snapshot → recovery still reads Newest,
  decision against the unchanged v1 server is `restore` → saving
  Newest clears to null.
- `resolveRecovery` marks server-held edits `covered`.
- Legacy storage entries without `baseVersion` validate to `null`
  (conflict-safe), never crash the restore path.

## 4. Gates (observed this session)

- `npx vitest run`: 16 files, 115 tests, all passed.
- `npx vue-tsc --noEmit`: clean. `npx eslint` on touched files: clean.
  `npx prettier --check` on touched files: clean.
- `node scripts/walkthrough.mjs` against the live stack (compose API +
  DB, local vite): WALKTHROUGH PASSED, including the `dirtynav`
  leave/reopen restore and post-failure edit scenarios.
