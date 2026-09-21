# Ember Vale — Fifth-push review and focused handoff

Reviewed commit: [ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43](https://github.com/joelhenwang/ember-vale/commit/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43)

## Decision

Most of the previous correction work is present in this commit. Keep the current architecture, styling, and completed fixes. Complete the two bounded corrections below before marking the creation/resume foundation accepted, then resume the existing product implementation plan.

This review inspected committed source and evidence and independently reproduced the ambiguous-submission defect with the actual composable body and mocked API/ref dependencies. It did not rerun the full application, 106 Vitest tests, or live walkthrough. Those successful runs remain agent-reported and committed evidence.

## What can move forward

- Story operations capture their world, actor, role, beat, and lifecycle context.
- Pinned preset retrieval has a dedicated composable and explicit failure handling.
- History has a user-visible continuation and protection against non-progressing cursors.
- Draft save status, recovery storage, and same-submission replay are implemented.
- Browser evidence exercises real creation, movement, beat advancement, reload, and a stopped-API save failure/retry.

Do not reopen these areas for speculative redesign. The remaining problems are concentrated in draft ownership and navigation durability.

## 1. High priority: keep creation and queued work owned by their draft

Source: [useStoryDraft.ts](https://github.com/joelhenwang/ember-vale/blob/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43/src/composables/useStoryDraft.ts), [NewStoryView.vue](https://github.com/joelhenwang/ember-vale/blob/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43/src/views/NewStoryView.vue).

### Reproduced failure

1. Open draft A.
2. Begin creation; both attempts time out. The controller retains A's frozen submission.
3. Open draft B using the same controller, as the wizard does on a draft-query transition.
4. Begin creation for B.
5. The controller replays A's pending submission before considering B.

Observed output from the isolated reproduction:

```json
{"displayedDraft":"B","createdOrResumed":"story-A","requestTargets":["A","A","A"]}
```

The problem is the unqualified `if (pendingFrozen)` branch in `createWorkflow`, together with `openExisting` retaining that state. An unresolved submission from one draft must never become another draft's Begin action.

### Required correction

- Scope pending submission receipts, create errors, acknowledgment state, and operation ownership to draft identity.
- Preserve A's unresolved receipt for reconciliation; simply deleting it on navigation loses the protection against duplicate creation.
- Replay only a receipt belonging to the draft being acted upon. Preserve its exact draft ID, version, and idempotency key.
- Capture target draft identity and an immutable payload/step when enqueueing a save. Serialized saves must obtain the next acknowledged version for that same draft; do not freeze one obsolete version for all queued saves.
- Guard load/save/validation/create completions by their owning draft and lifecycle. A late completion from A must not replace B's controller state or navigate the user into A.
- Keep unresolved creation recoverable across leaving and reopening the wizard. Reconcile a completed draft or replay its original receipt before issuing a fresh save/create.
- Cleanup must affect only the owning draft's recovery and remembered state.

The queue and load issues are related source-level risks: queued `doSave` currently reads mutable `draft.value` when it executes, and `openExisting` assigns its response without a controller-level generation check. Address them in the same ownership correction.

### Focused regression cases

- Ambiguous A → open B → Begin B never sends A's receipt.
- Return to ambiguous A → retry uses exactly A's original ID/version/key.
- Queue A saves → open B → resolve the queue: B is neither patched with A's input nor replaced by A's response.
- Slow A load → fast B load → A completes: B remains active.
- Reopen after an ambiguous creation: reconcile/replay without a fresh submission identity.

## 2. Medium priority: protect edits during in-app navigation

Source: [NewStoryView.vue](https://github.com/joelhenwang/ember-vale/blob/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43/src/views/NewStoryView.vue), [useStoryDraft.ts](https://github.com/joelhenwang/ember-vale/blob/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43/src/composables/useStoryDraft.ts).

The wizard installs a browser `beforeunload` guard. Vue Router navigation through Home, Library, or another draft does not trigger that event. Recovery is written when a save fails, so it does not necessarily contain an unsaved edit made before navigating away, or a newer edit made after that failure.

### Required correction

Choose one coherent behavior using the existing visual language:

- Save or persist a local recovery snapshot before leaving a dirty draft; or
- Intercept route leave/update and offer Save, Leave with recovery, or Stay.

Apply this to top-level navigation and draft-query changes. Store recovery per draft; one global recovery slot lets separate drafts overwrite each other. Snapshot the latest selections and step, validate recovered data, show that recovery is local, and clear only recovery covered by the matching successful acknowledgment. If storage fails, keep the user informed and retain the mounted input.

Do not mark recovery as a successful server save. Do not overwrite an unresolved create receipt with a newer editable snapshot.

### Acceptance cases

- Edit a title, navigate Home without pressing Save, reopen: the latest edit is recoverable or navigation was explicitly prevented.
- Fail a save, edit again, leave/reopen: the newest edit survives.
- Recover drafts A and B independently.
- Confirm ordinary clean navigation stays immediate.

## Verification and evidence

Extend the existing walkthrough rather than introducing another harness:

1. Create a Player story through the wizard, explicitly select Wren, and verify the persisted grant and locked actor after reload.
2. Exercise dirty in-app navigation and recovery, including edits made after a failed save.
3. Keep the current Observer, movement, beat, reload, and API-failure checks.

The present Player walkthrough seeds its story through the API, so it verifies the Player room but not Player selection/creation in the wizard. The current failed-save check proves Retry, not recovery after navigation or reload. Narrow screenshots are useful evidence but do not alone establish overflow or 200% zoom accessibility.

Report the exact tested commit, commands, outcomes, and remaining limitations. Rerun the affected composable/workflow tests, existing frontend gates, and the extended browser journey. Rerun backend gates if backend behavior changes or the repository requires them.

## Exit condition

Close the two corrections with the focused regressions and browser evidence. Then continue the established product milestones. Preserve the existing Ember Vale components and styling; do not restart the frontend migration or expand this correction into the deferred studios, image provider, or director/deity feature work.

Evidence: [walkthrough script](https://github.com/joelhenwang/ember-vale/blob/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43/scripts/walkthrough.mjs), [recorded results](https://github.com/joelhenwang/ember-vale/blob/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43/docs/evidence/walkthrough/results.json), [push report](https://github.com/joelhenwang/ember-vale/blob/ad7cc5b04c7eb77bb80bb73ad09fc885c172eb43/docs/evidence/fourth-push-corrections.md).

