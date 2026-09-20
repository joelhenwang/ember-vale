# Ember Vale — third-push review and correction guide

**Reviewed commit:** `5bb99b2db038944dd1014cb856749abbb967c743` (“third push”).  
**Decision:** retain this implementation, but complete a focused integration correction pass before declaring the playable milestone finished.

## 1. What is working toward the intended design

The push contains the revision-2 repair, canonical payload hashing, story-creation persistence/race fixes, completed-travel coverage, real preset/draft/story API integration, a playable route, and a committed HTTP journey script. These are substantial improvements over the second push.

The agent reports 56 backend passes with one skip, 59 frontend passes, a restart check, and screenshots. Those results are reported evidence. This review inspected the pushed source and independently reproduced three narrow failures described below; it did not rerun Docker, the full suites, or a browser.

The user-provided report says work was uncommitted. GitHub now contains the reviewed changes in the commit above; this review concerns that pushed snapshot, not any later local work.

Do not redo the backend import, redesign Ember Vale, or expand into live providers, studios or director controls yet. Correct the integration paths below and retain the current look.

## 2. Findings and priorities

| ID | Priority | Finding | User impact |
|---|---|---|---|
| R1 | P1 | Advance sends null for a non-null dictionary | Story-room advance request fails validation |
| R2 | P1 | Creation proceeds after draft save fails | A story can be created from stale/different choices |
| R3 | P1 | Credential-injecting dev proxy listens on all interfaces | A reachable dev server grants callers authenticated API access |
| R4 | P1 | Controlled actor is resolved by name; travel selection is not synchronized on initial Player load | Player can target the wrong character and receive a forbidden action |
| R5 | P2 | Feed repeatedly loads only its first page | New events disappear once history exceeds the first page |
| R6 | P2 | All non-timeout fetch failures become cancellation | Real network outages can be silently ignored |
| R7 | P2 | Activity reconciliation expects items; backend returns members | Repeated travel cannot identify the running activity |
| R8 | P2 | Story ID captured once; refresh/mutations lack complete lifecycle guards | Same-component route changes and late responses can target stale state |
| R9 | P2 | Wizard step/default and revision display are not restored consistently | Reload and New Story behavior differ from the promised flow |
| R10 | P2 | Story open operation is unused; Home includes archived stories | Last-played metadata is not updated by the room; Continue can feature archived stories |

P1 means correct before accepting the current playable milestone. P2 items belong in this same bounded integration pass because they affect normal continuation, retries or reloads.

## 3. R1 — correct advance payloads and contract generation

**Sources:** [src/api/worldsim.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/api/worldsim.ts), [src/composables/useStory.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/composables/useStory.ts), [backend/src/worldsim/interfaces/http/schemas.py](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/backend/src/worldsim/interfaces/http/schemas.py), [scripts/journey.mjs](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/scripts/journey.mjs).

The backend request declares:

```python
player_intents: dict[str, dict[str, object]] = Field(default_factory=dict)
```

The frontend calls advanceStory with null and serializes:

```ts
player_intents: intents ?? null
```

The generated TypeScript interface incorrectly permits null for this optional field. “Optional” means omission is allowed; it does not automatically mean an explicit null is allowed.

**Independent reproduction:** the extracted backend request class accepted omission and an empty dictionary, but rejected null with Pydantic error `dict_type`. This is a schema reproduction, not an HTTP-server test. The frontend's submitted null consequently cannot pass this request model.

**Implement:**

- Omit player_intents when there are none, or send an empty dictionary.
- Correct the generator’s distinction between optional and nullable, then regenerate contracts. Do not only hand-edit generated output.
- Review consumed request DTOs for the same mismatch; scope fixes to actual affected operations rather than introducing a new contract framework.
- Test the serialized body from the actual advanceStory adapter against the backend. An API-only test that constructs a different body will miss this bug.

**Pass condition:** clicking Advance in both an Observer and a Player story commits or replays the intended beat without a validation error. Capture the actual frontend request in the browser test.

The existing journey script omits the field, which explains why its success does not verify this frontend request.

## 4. R2 — make save, validate and create one guarded workflow

**Sources:** [src/views/NewStoryView.vue](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/views/NewStoryView.vue), [src/composables/useStoryDraft.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/composables/useStoryDraft.ts).

create() awaits persist() but ignores its boolean result, then calls submit(). go() and next() also proceed after failed persistence. Back starts a save without awaiting completion. Continue/step navigation is not consistently guarded by the busy state; Create is only disabled once submit begins.

On a version conflict, save() loads the newer server draft while leaving local selections unchanged. If create() continues, it can submit that server draft instead of the choices displayed to the user.

**Independent reproduction:** executing the extracted create() function with persist() returning false still called submit() and navigated.

**Implement:**

1. Set a synchronous operation guard before the first await.
2. Persist the intended selections and step.
3. If persistence fails, stop; retain input and display the conflict/error.
4. Validate the acknowledged saved draft before creation.
5. Freeze the draft ID, expected version and operation key for that submission.
6. Retry the same submission with the same frozen values.
7. Navigate only after creation acknowledgement.
8. Serialize navigation saves or disable overlapping navigation while saving.

Keep the operation key in memory as well as optional browser storage. Currently, storage failure causes storedCreateKey() to return a fresh key each call, including the timeout retry. A completed draft’s backend guard prevents some duplication, but a new key does not satisfy the replay contract and can strand a successfully created story behind an error.

**Tests:** failed PATCH means zero create requests; stale draft means no automatic creation; rapid double-click means one workflow; storage-disabled timeout retry preserves the exact key; failed saves preserve visible input.

## 5. R3 — make credential injection genuinely local

**Source:** [vite.config.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/vite.config.ts).

The proxy adds the backend operator key server-side, but Vite is configured with host 0.0.0.0 and allowedHosts true. Keeping the secret out of the browser bundle does not protect the authenticated proxy: callers who can reach the dev server can use its /api route without presenting that key themselves.

**Implement:**

- Default the credential-injecting dev server to loopback.
- Remove unrestricted allowedHosts; use the supported default or explicit trusted hosts.
- If remote/LAN development is required, make it explicit and authenticate access before injecting an operator credential. Do not rely only on a hostname allowlist as authentication.
- Keep production authentication separate and documented.
- Retain the backend’s existing authentication guard.

**Pass condition:** the ordinary local setup works, and the operator-key proxy is not silently exposed through a wildcard bind. Verify the effective dev-server configuration, not only comments.

This finding is about the new authenticated proxy behavior, not a request for a general security redesign.

## 6. R4 — use authoritative Player identity and role state

**Sources:** [src/views/PlayView.vue](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/views/PlayView.vue), [backend/src/worldsim/interfaces/http/routes/roles.py](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/backend/src/worldsim/interfaces/http/routes/roles.py).

The setup already records controlled_character_id and per-member runtime_character_id, but PlayView resolves the player by matching names against visible map occupants. Duplicate names or an absent map occupant can produce the wrong identity.

The cast watcher initially chooses the first alphabetical actor for travel. The mode watcher changes role but does not reset travelChar to the controlled actor. For example, a story controlled by Wren can initially retain Ash as travelChar while the Player selector is disabled.

The “View as” dropdown only changes headers. The backend’s effective_role explicitly prefers the persisted grant over those headers. The dropdown therefore does not implement an actual role switch or a reliable preview.

**Implement:**

- Load the active grant or authoritative controlled runtime ID; do not infer identity from names.
- Synchronize the selected travel actor when role/controlled ID becomes available.
- Disable Player actions until the controlled identity is resolved.
- Keep backend enforcement.
- For this milestone, show the actual mode read-only. Alternatively, implement a deliberate supported role-change command with backend acknowledgement and refetch; do not claim headers alone change mode.
- If a view-only preview is wanted later, design it explicitly without changing the actual gameplay grant.

**Tests:** Player as Wren when Ash sorts first; Player as Ash; duplicate names; missing/filtered map occupant; role display matches the persisted grant; forbidden requests remain forbidden.

## 7. R5 — paginate the feed and keep current narrative visible

**Sources:** [src/composables/useStory.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/composables/useStory.ts), [src/api/worldsim.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/api/worldsim.ts), [backend/src/worldsim/interfaces/http/routes/stage2.py](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/backend/src/worldsim/interfaces/http/routes/stage2.py).

Every feed fetch passes after=0. The backend returns the first 20 source events by default, plus next_after and has_more. The composable discards that pagination state. Reversing those entries only reverses the earliest page; it does not show the latest story.

**Implement:**

- Track the server scan cursor and fetch subsequent pages or an appropriate supported latest-history window.
- Use next_after even when a role-filtered page contains zero visible entries.
- Merge/deduplicate by stable event identity and maintain explicit display order.
- Load incremental events after a beat rather than replacing history with page one.
- Reset pagination on story or effective-perspective change.
- Keep full narrative access distinct from the short timeline snippet if the UI claims to show the full story.
- Show the development-model status in the room itself; the pushed PlayView has no explicit provider-status label despite the report’s claim. The wizard label alone is insufficient for direct room entry.

**Tests:** more than 20 source events; filtered page with zero entries and has_more=true; repeated page; retry after a beat; reload showing the newest committed event.

## 8. R6–R8 — repair transport, activity reconciliation and lifecycle scope

### Network errors are not cancellations

**Source:** [src/api/http.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/api/http.ts).

The fetch catch block maps every exception other than an Error with message REQUEST_TIMEOUT to REQUEST_ABORTED.

**Independent reproduction:** a mocked fetch rejection `TypeError("Failed to fetch")` without any abort produced `REQUEST_ABORTED, cancelled=true, retryable=false`. Consumers such as usePresets intentionally ignore cancelled errors, so this can conceal an outage.

Distinguish actual outer-signal cancellation, internal timeout and network/transport failure. Keep visible retryable network errors. Handle timeout/failure while reading the response body as well as during the initial fetch. A cancelled client request does not establish that a server mutation was cancelled.

### Activity reconciliation uses the wrong DTO

**Sources:** [src/api/worldsim.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/api/worldsim.ts), [src/composables/useStory.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/composables/useStory.ts), [backend/src/worldsim/interfaces/http/routes/activities.py](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/backend/src/worldsim/interfaces/http/routes/activities.py).

listActivities handwrites an items field; ActivityListResponse returns members. useStory therefore cannot find the character’s active activity.

Use the generated response type and members. Do not interpret every 409 as “that journey is underway”: missing routes and other preconditions also return 409. Reconcile against an active activity matching the actor, kind and destination; preserve genuine failure messages. Reconcile a timed-out start before blindly retrying, since this route does not expose a durable idempotency key.

### Route identity and late responses

**Sources:** [src/views/PlayView.vue](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/views/PlayView.vue), [src/composables/useStory.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/composables/useStory.ts), [src/App.vue](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/App.vue).

useStory receives storyId.value once. App.vue does not key the routed component by story ID. An in-place change from /stories/A/play to /stories/B/play can reuse PlayView with its old captured ID.

Only load() has a cycle/AbortController guard. refreshTimeline(), advance() and travel() do not consistently use that lifecycle scope. A late refresh can overwrite more recent view state.

Choose a reactive story-ID lifecycle or remount the room by story ID. Guard all state updates by the current story/perspective/request generation. Keep mutation state pending through acknowledgement and reconciliation so the user cannot start another beat against stale displayed state.

**Tests:** change A→B while A requests are pending; delayed old refresh; navigate away during mutation; direct same-component navigation; assert no subsequent B-room action sends A’s ID.

## 9. R9–R10 — finish reload and continuation semantics

### Wizard restoration

NewStoryView initializes step to 2 while the router comment says it starts at World. It never hydrates the persisted current_step. Saves use the current step before navigation. Quickstart also changes selections locally without immediately persisting those changes.

- Restore the correct step and define whether current_step means the visible step or last completed step.
- Start a genuinely new story at World; make Quick Start’s destination explicit.
- Persist quickstart selections before claiming they survive reload.
- Fetch/display the exact world and character revisions referenced by an existing draft. usePresets currently loads latest revisions only; an older draft can show current world places while still submitting an older revision.
- Preserve completed-draft behavior: reopening a created draft should lead to the existing story or explain its state.
- Scope draft load responses to the current route/draft.

### Open metadata and Home selection

**Sources:** [src/api/worldsim.ts](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/api/worldsim.ts), [src/views/PlayView.vue](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/views/PlayView.vue), [src/views/HomeView.vue](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/src/views/HomeView.vue), [backend/src/worldsim/interfaces/http/routes/stories.py](https://github.com/joelhenwang/ember-vale/blob/5bb99b2db038944dd1014cb856749abbb967c743/backend/src/worldsim/interfaces/http/routes/stories.py).

The API adapter defines openStory(), but room entry does not call it. The explicit open endpoint updates last_played_at; ordinary detail reads do not. Home requests all stories, including archived ones, then promotes the first sorted result to Current Story.

- Record an explicit successful room open through the existing operation without advancing gameplay.
- Select an eligible unarchived story for Home’s Continue hero.
- Align shelf sort behavior with its “Last played” label, including never-opened stories.
- Keep archived stories available through the shelf’s explicit archived filter.

## 10. Correct the acceptance evidence

The committed journey script is useful, but it creates a new story every run. It does not accept an existing story ID to verify restart continuity, and its advance body differs from the frontend’s failing body. Re-running it after restart proves another creation journey, not by itself that the previous story resumed correctly.

Manual restart checks may have happened; retain them as manual evidence. Make the durable proof reproducible:

1. Create a story and save its ID plus expected clock, actor location and event cursor in a test artifact.
2. Restart the API without resetting the database.
3. Run a resume/assert mode against that same ID.
4. Verify state, then continue the existing story.
5. Create a second story and prove A’s action does not change B.
6. Run a browser-driven Player and Observer journey using the real UI and adapter.
7. Capture failed-save, network outage, repeated travel, pagination and route-switch regressions.

Do not substitute component presence or a screenshot for exercising its operation. Add focused component/composable tests around the faulty paths; existing pure formatter/payload tests do not cover these transitions.

## 11. Execution order and stop condition

1. **Fix Advance payload and generated optional/null semantics.**
2. **Guard save→validate→create and operation retries.**
3. **Restrict the credential-injecting proxy to its intended access boundary.**
4. **Correct Player identity, role display and activity response mapping.**
5. **Implement feed pagination, network-error classification and route lifecycle guards.**
6. **Complete wizard restoration and story-open metadata.**
7. **Run focused regressions plus the actual browser journey; update evidence.**

Keep commits reviewable. Preserve screenshots/styles and do not mix this work with a new backend import or broad visual rewrite.

The milestone is complete when the existing UI can create the intended saved draft, complete a real beat/travel action, show new events beyond page one, and resume the same story after restart—while handling the tested failure paths honestly.

After this correction pass, return to the larger product handoff. Live provider probing, studio persistence, director/deity UI and the zoom pass remain separately stated work; they do not need to be pulled into this patch.

## 12. Reproduction and verification summary

| Check performed by this review | Result |
|---|---|
| GitHub source inspection at pinned third push | Changes and findings identified above |
| Extracted Stage1AdvanceRequest model: omitted / {} / null | Accepted / accepted / rejected |
| Actual transport function with failing fetch, no abort | Incorrectly reported cancellation |
| Extracted wizard create function with failed persist | Still submitted and navigated |
| Full backend/frontend test suites, Docker and browser | Not independently rerun |
| Visual screenshots | Presence documented; visual parity not independently revalidated |

These findings are sufficient to request a targeted correction pass. They do not negate the backend progress already delivered.

