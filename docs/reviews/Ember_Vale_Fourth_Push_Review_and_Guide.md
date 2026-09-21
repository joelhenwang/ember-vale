# Ember Vale — fourth-push review and focused follow-up

**Reviewed commit:** `7ad97c470c1d695dd8120b323db3a66b3fad1097` (“fourth push”).  
**Verdict:** keep the implementation. Most third-push blockers are addressed. Fix the remaining mutation-lifecycle issue and the bounded follow-up items below, then verify the actual Player/Observer browser journey before expanding scope.

## 1. What the fourth push resolves

The pushed source now:

- Omits empty player_intents and distinguishes optional from nullable generated fields.
- Uses a guarded persist → validate → frozen submission workflow, with in-memory operation keys.
- Defaults the credential-injecting dev proxy to loopback.
- Resolves the controlled actor by persisted runtime ID.
- Reads activities from members and reconciles matching actor/kind/destination.
- Pages through server history cursors and deduplicates events.
- Distinguishes initial fetch network failures from cancellation.
- Records explicit story opens and filters archived stories from Home.
- Adds a same-story resume mode to the HTTP journey script.

These are meaningful corrections, supported by new targeted tests. Do not reopen completed work or redo the backend/frontend architecture.

The report's 85 frontend passes and green backend suite are agent-reported results. This review inspected pinned source and ran isolated reproductions for the mutation retry and history-cap issues. It did not rerun the complete stack or browser suite.

The report’s “uncommitted” wording is stale relative to GitHub: the reviewed changes are in the commit above. Any newer local edits are outside this review.

## 2. P1 — freeze the mutation target and stop stale retries

**Source:** [src/composables/useStory.ts](https://github.com/joelhenwang/ember-vale/blob/7ad97c470c1d695dd8120b323db3a66b3fad1097/src/composables/useStory.ts).

advance() captures the beat index and lifecycle generation, but its attempt closure reads the reactive id() each time. It also retries REQUEST_TIMEOUT without first checking whether the lifecycle has changed.

A generation check around state updates does not protect a request sent to the wrong world.

**Independent reproduction using the actual composable body with substituted reactive/API dependencies:**

1. Load A at absolute index 3.
2. Begin advance for A, target index 4; hold its response.
3. Cancel that lifecycle, change the reactive story ID to B and load B.
4. Reject A’s held request with REQUEST_TIMEOUT.
5. Observe the retry target.

Actual calls:

```json
[
  {"id": "A", "index": 4},
  {"id": "B", "index": 4}
]
```

Whether the backend accepts the second request depends on B’s state. It is still incorrect to send A’s operation to B. The per-story remount does not eliminate this risk: an unresolved promise from the old instance can retain a computed value backed by the changing route.

### Required change

At mutation start, capture an immutable operation context: world ID, target index or activity arguments, effective role, controlled runtime ID, lifecycle generation and relevant signal. Every attempt and reconciliation request must use this context.

Before retrying, check that the operation is still active in the intended lifecycle. If the user has left the story, do not automatically retry into another view. The original request may already have committed; reconcile against its original world when appropriate or on next entry.

Apply the same principle to travel reconciliation and multi-page reads: source IDs must be stable for the operation, not re-read from mutable route state after an await.

Ensure request-lifecycle cleanup cannot leave a reusable composable permanently advancing/traveling after cancellation.

### Required regression tests

- A advance times out after navigation to B: no request targets B.
- A advance times out after unmount: no automatic retry from the disposed lifecycle.
- Same-story timeout: retry uses the same world, index, role and actor.
- Navigation during travel/reconciliation: reads remain scoped to A or are cancelled.
- Re-entering A loads committed state without duplicating the operation.

Do not consider the existing late-GET test sufficient: it tests stale read assignment, not a pending mutation retry.

## 3. P2 — finish history pagination at the cap

**Sources:** [src/composables/useStory.ts](https://github.com/joelhenwang/ember-vale/blob/7ad97c470c1d695dd8120b323db3a66b3fad1097/src/composables/useStory.ts), [src/views/PlayView.vue](https://github.com/joelhenwang/ember-vale/blob/7ad97c470c1d695dd8120b323db3a66b3fad1097/src/views/PlayView.vue).

The first-page defect is corrected. The remaining issue occurs at MAX_PAGES=25 with PAGE_LIMIT=50.

The room says “reload to fetch the rest,” but load() resets the cursor to zero. Reload therefore repeats the same first 1,250 source events and cannot reach the remainder.

**Independent reproduction:** with a mocked 1,300-event source, the first load ends at cursor 1,250; a second load again ends at 1,250 with hasMore=true.

### Required change

Keep the bounded fetch; provide an explicit “Load more”/continue-history action using the stored cursor, or an appropriate latest-history query. Do not rely on a gameplay mutation to fetch the remaining history.

Distinguish scanned source counts from visible entries. Under Player filtering, “N of M events” can mix visible entries with all-world source totals; label it accurately and avoid exposing unnecessary hidden counts.

### Tests

- More than 1,250 source events; the read-only history action reaches the remaining events.
- Empty visible page with an advancing source cursor.
- No-progress cursor response does not loop indefinitely.
- Reload and continuation copy accurately describe what the UI can retrieve.

This is a bounded integration fix, not a request for unlimited eager history loading.

## 4. P2 — make pinned-preset loading exact and race-safe

**Source:** [src/views/NewStoryView.vue](https://github.com/joelhenwang/ember-vale/blob/7ad97c470c1d695dd8120b323db3a66b3fad1097/src/views/NewStoryView.vue).

The draft’s older world revision is fetched, but refreshPinnedWorld():

- Uses mutable sel.worldRev after the awaited request to label the response.
- Has no request-generation check for the selected preset/revision.
- Falls back silently to latest-world places when fetching the pinned revision fails.
- Exposes pinnedWorld.places based only on a revision-number match, without also matching the preset ID.
- Is invoked during boot; there is no selection watcher to keep it synchronized with subsequent world/revision changes.

An older A response arriving after selecting B can therefore be mislabeled with the current revision or supply A’s places under B. A failed old-revision request can show current places while the submitted payload remains pinned to the old revision.

The cast picker still loads current character revisions; existing selected members can reference older ones. Avoid describing all pinned revisions as fully supported until the selected character presentation is also resolved correctly.

### Required change

- Capture preset ID and revision before requesting.
- Cache or identify results by both ID and revision.
- Assign only if that pair remains selected and the request is current.
- Show a specific unresolved-preset error on failure; do not substitute latest content under an old revision.
- Resolve pinned selected-character details where displayed; latest versions remain appropriate for browsing new additions.
- Update selected locations deliberately when the user changes worlds, with validation for removed locations.

### Tests

Slow A followed by B; failed pinned revision; two presets sharing revision number 1; old selected character revision; selected location absent from the new world.

## 5. Optimistic wizard navigation: acceptable with explicit durability

**Sources:** [src/views/NewStoryView.vue](https://github.com/joelhenwang/ember-vale/blob/7ad97c470c1d695dd8120b323db3a66b3fad1097/src/views/NewStoryView.vue), [src/composables/useStoryDraft.ts](https://github.com/joelhenwang/ember-vale/blob/7ad97c470c1d695dd8120b323db3a66b3fad1097/src/composables/useStoryDraft.ts).

Moving visually to the next step before a save completes is a valid UX choice. Creation now correctly stops after a failed save. There is no need to reverse that improvement.

However, retaining selections only in the mounted component does not make them safe across leaving or reloading after a failed save. A revision number alone is not a reliable unsaved indicator. The navigation caveat needs an implemented durability contract, not only a report note.

### Required change

- Track clean/saving/unsaved/failed states against the last acknowledged draft snapshot.
- On save failure, keep the user’s choices and present a retry action.
- Before leaving/reloading with unsaved changes, either protect the transition or persist a clearly identified local recovery draft. Do not imply server persistence succeeded.
- Capture queued save inputs as immutable snapshots.
- Use a synchronous navigation/queued-save guard if rapid actions can enqueue work before busy becomes true.
- Keep creation hard-gated on acknowledged save and validation.

Quick Start also calls persist() without checking its result. If that save fails, it must not claim that the prefill is durable.

### Draft query changes

The routed wizard is keyed by path, and boot runs on mount. Changing only ?draft= from draft A to B does not trigger a reload of the wizard.

Implement an explicit draft-ID transition or a deliberate route key. Avoid rebooting accidentally during the wizard’s own first assignment of ?draft=. Test URL and loaded draft agreement with Back/Forward and explicit draft-link navigation.

These corrections allow optimistic navigation to remain; they do not require hard-blocking every step transition.

## 6. P2 — preserve cancellation/timeout identity while reading a body

**Source:** [src/api/http.ts](https://github.com/joelhenwang/ember-vale/blob/7ad97c470c1d695dd8120b323db3a66b3fad1097/src/api/http.ts).

Initial fetch classification is improved. However, the successful-response res.json() catch maps every exception to REQUEST_TRANSPORT. A timeout or external abort during body consumption therefore loses its timeout/cancellation classification.

For a mutation this matters: create/travel timeout reconciliation is selected by REQUEST_TIMEOUT, so body-read timeouts can bypass the intended recovery path.

Use the same abort/timeout classification across fetching and body consumption. Treat an actual malformed JSON response as a transport/protocol error. Test a response whose body stalls after headers, with both timeout and outer cancellation.

Keep the frozen submission available until an ambiguous outcome is reconciled. A later user retry should not blindly start with a fresh save/version/key if the previous create may have committed.

## 7. Close the browser evidence gap

Manual browser testing is acceptable for this milestone if performed and recorded. “Remains manual” is not evidence that it happened.

The composable tests do not mount NewStoryView or PlayView. The remaining issues above occur precisely where route state, view watchers, controls and composables interact.

Run and record:

1. Observer: create → start travel → advance → leave → reload → continue.
2. Player as Wren while Ash sorts first: verify the selected runtime actor and successful movement.
3. Failed wizard save: optimistic navigation, visible unsaved state, retry and leave/reload recovery.
4. Pending A advance followed by B navigation and timeout.
5. Older world preset, including a failed pinned-content fetch.
6. History beyond the page cap, without advancing the game just to load it.
7. Same-story API restart and resume, using the saved artifact.
8. Representative desktop and narrow viewport; finish the already-known zoom check when assessing visual readiness.

Browser automation can make these repeatable, but the immediate requirement is an actual end-to-end observation with accurate evidence. Do not label the entire milestone verified solely from formatter/adapter/composable tests.

Preserve the successful HTTP create/resume script. Its artifact currently uses a page’s entry count as an event cursor; strengthen long-history checks to use actual source cursor/total semantics and runtime actor IDs when extending it.

## 8. Delivery order and exit criteria

| Order | Work | Completion evidence |
|---|---|---|
| 1 | Freeze mutation identity and guard retries | Delayed A→B mutation regression |
| 2 | Correct pinned revisions and draft transitions | Out-of-order/failed-load tests; draft URL matches content |
| 3 | Provide history continuation and durable unsaved state | Cap continuation; failed-save recovery |
| 4 | Correct body-read error classification | Timeout/cancellation tests after headers |
| 5 | Perform browser Player/Observer journeys | Recorded walkthrough with outcomes |

Keep these as focused corrections. Do not rewrite the backend, add director mode, or expand image generation to satisfy this review.

Once the tests and actual browser journey pass, accept the persistent-story foundation and continue to the next planned product milestone. Further review should then focus on that milestone, rather than endlessly expanding the acceptance scope of this one.

