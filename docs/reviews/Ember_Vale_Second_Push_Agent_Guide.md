# Ember Vale — second-push implementation handoff

**Repository:** joelhenwang/ember-vale  
**Reviewed baseline:** `d1aaea0a73fe6c551275298f31d4d01c566d5559` (“second push”)  
**Purpose:** correct the remaining backend issues, then complete the first playable journey in the existing Ember Vale frontend.

## 1. Assignment and completion target

Continue on top of Ember Vale. Preserve its Vue views, shared components, routing conventions, artwork and styling. The product is an LLM-driven fantasy storytelling game with persistent worlds and characters, playable either through a selected character or as a world observer, with director intervention planned later.

Your next delivery must let a user:

1. Select a world and cast.
2. Choose Player or Observer mode; in Player mode, select a character from that cast.
3. Create a durable story.
4. Complete one meaningful character action or story beat.
5. Leave, reload the browser, restart the API, and resume the same committed state.

Fix preset revisioning and prove travel completion before wiring this journey. Use the full product plan in `docs/handoff/Ember_Vale_Product_and_Backend_Plan.md` for broader requirements; this document defines the immediate execution order.

Do not repeat completed infrastructure work or launch a broad redesign. Continue through the stages below autonomously, resolving routine implementation details from the repository. Report a concrete blocker if a required capability is unavailable.

## 2. Review status and evidence limits

The second push addresses the first review’s database configuration and readiness issues, restores backend tests, adds ten visual baseline screenshots, removes committed build metadata, and introduces travel-route instantiation.

The agent’s evidence reports successful backend tests and a live HTTP create/tick/restart sequence. The second-push review inspected source and the committed evidence; it did not independently run Docker, pytest or a browser session.

| Area | Current status | Next action |
|---|---|---|
| Database configuration | Username interpolation and typed environment key corrected | Retain and use documented isolated environment |
| Readiness | Positive check handling and numeric schema version corrected | Keep empty-world status advisory during onboarding |
| Backend tests | Restored; selected results documented | Extend specific missing journey coverage |
| Visual baseline | Desktop and narrow screenshots committed | Compare live-data screens against these |
| Travel routes | Validated and created in story transaction | Correct preset versioning and prove completed movement |
| Backend HTTP journey | Create, replay, clock tick and restart reported | Prove gameplay effects and narrative |
| Frontend integration | Still open | Connect existing views to durable state |

The presence of tests does not establish that all imported subsystems work. Report precisely which paths each new test exercises.

## 3. Stage A — repair preset revisioning

### Problem

Migration `0032_starter_travel.py` updates the payload of the existing built-in world’s revision 1 and assigns the literal content hash `builtin-v2`. The application’s missing-preset initializer instead computes a SHA-256 hash from serialized payload content.

A preset ID plus revision must identify stable content. Rewriting revision 1 means that a previously saved draft can resolve to a different world configuration after migration. Existing resolved story snapshots are not directly rewritten by this migration, but draft reproducibility and revision identity are compromised.

### Required design

- Publish the corrected world configuration as a new revision.
- Preserve established revisions and existing story snapshots.
- Use a consistent canonical payload hashing algorithm for newly created revisions. Reuse the existing application convention or centralize it deliberately.
- Update default new-story selection to choose the intended corrected revision.
- Update template references through a new template revision where necessary. An immutable template revision must not silently change its world revision.
- Preserve the exact revision referenced by existing drafts; do not silently upgrade them.
- Keep world, template and character revision numbers distinct. Do not globally replace every revision 1 with revision 2.
- Ensure migration-based initialization and application-based missing-preset initialization produce compatible revision sets, payloads and hashes.
- Never reset the database to conceal an upgrade problem.

### Already-applied migration handling

The evidence says 0032 has already run on a development database. Inspect its actual state before choosing a repair strategy.

Do not assume editing the migration file will repair a database that has already applied it. Provide an explicit forward repair for that state, or another documented migration strategy that covers both existing and fresh installations.

If recovering the original built-in revision, use verified historical seed content and narrowly identified rows. Do not overwrite user changes or rewrite saved story configurations. A draft created while the mutated revision was active may be ambiguous: preserve any captured resolved content and document the ambiguity rather than claiming its original intent can always be reconstructed.

Keep migration history and the treatment of the already-shipped 0032 deliberate. Do not instruct users to run its downgrade casually; that downgrade also rewrites revision content.

### Acceptance checks

- Upgrade a pre-0032 database containing an existing draft and story.
- Upgrade a database where the original 0032 has already run.
- Initialize a fresh database.
- Verify intended current starter revision and both directed travel legs.
- Verify historical story snapshots remain byte-for-byte equivalent in their canonical representation.
- Verify draft revision references are preserved or any explicit recovery behavior is documented and tested.
- Verify initialization is repeatable without duplicate revisions.
- Verify newly published revisions’ hashes equal the canonical hash of their payloads.

**Deliver:** a focused migration/preset commit, targeted tests, and a short explanation of the upgrade paths.

## 4. Stage B — prove a gameplay action completes

### Current coverage gap

`test_created_leg_serves_travel_activity` starts a travel activity and checks its duration and stamina cost. It does not commit that activity, run it to completion, or verify Wren’s arrival through a new database session.

The HTTP journey uses `/world/phases/advance`, which invokes the Stage 0 tick orchestrator. The documented `world_seeded` and `world_ticked` events prove persisted ticking, not the completion of character actions.

### Resolve the orchestration contract first

Trace the existing routes and services before wiring a frontend button:

| Existing path | What the review established | Required investigation |
|---|---|---|
| `/world/phases/advance` | Calls the Stage 0 tick orchestrator | Keep its intended infrastructure role clear |
| `/stage1/advance` | Separate gameplay orchestration route exists | Verify actions, narration, retries and compatibility with newly created stories |
| Activity commands and later orchestration | Travel activities and richer systems exist | Identify which production path advances activities to completion |
| Presentation and chronicle queries | Role-aware read endpoints exist | Verify the selected action becomes visible through these reads |

Do not assume Stage 1 alone completes every activity simply because of its name. Select the smallest existing orchestration path that actually supplies the required behavior. Extend a coherent service if needed; do not assemble unrelated endpoints in the browser to simulate one atomic gameplay operation.

Define what the UI’s “Advance” means: which work runs, what is committed, when the response is complete, and what happens on retry or partial failure. Do not apply an extra Stage 0 tick before gameplay advancement if the chosen orchestrator already advances the clock.

### Required travel test

1. Create a story through the real draft/create path using the corrected starter revision.
2. Resolve runtime character and location IDs from that story.
3. Verify Wren begins at Hearth.
4. Submit and commit a travel action through the intended application/API path.
5. Run the required phase processing.
6. Open a fresh transaction/session.
7. Assert Wren is at Market, the activity has reached its expected terminal state, and the corresponding state/event records agree.
8. Retry the same command with the same idempotency key and verify no second movement, duplicate effect or extra clock advancement.
9. Read the presentation/chronicle and verify the result can be shown to the user.
10. Repeat relevant reads after API restart in the committed journey script.

A deterministic development model is acceptable here. It must exercise real validation, orchestration and persistence. The frontend must clearly identify development generation; it must not invent narrative or completion locally.

Also tighten invalid-route coverage: assert the intended validation error and absence of orphaned world/location/route records, not merely a non-200 response and an unchanged story count.

**Deliver:** committed, repeatable tests and a brief endpoint/service decision explaining the chosen gameplay path.

## 5. Stage C — connect the existing frontend

Implement in this order. Preserve component composition wherever possible; place transport and mapping logic behind the views.

### C1. API contracts and state boundaries

- Generate or align the consumed TypeScript DTOs with the backend contract. Keep a reproducible generation command in the repository.
- Centralize request handling, authentication, errors and cancellation.
- Follow the existing authentication model without hardcoding credentials into source or URLs.
- Map API records into view models where presentation needs differ from domain shapes.
- Include explicit world/story IDs on every applicable request. Never depend on the single-world convenience path.
- Scope query state by story ID. Cancel or ignore late responses when navigating between stories.
- Preserve idempotency keys across retries of the same user operation; generate a fresh key for a new operation.
- Handle stale-version responses without silently overwriting newer state.
- Do not gate first-story creation on the world-count readiness check.

### C2. Real presets and persisted New Story drafts

Replace demo catalog reads in this journey with persisted presets, retaining the existing card layout and equal character-card dimensions.

The minimum starter is Ember Vale, Hearth, Market, Wren and Ash. Other illustrative characters/worlds are not required seed data. Curated art and neutral fallbacks are acceptable.

Wire the steps in the existing wizard:

1. World selection.
2. Cast selection.
3. Mode selection and, for Player mode, controlled-character selection.
4. Story and supported AI configuration.
5. Review and create, respecting the existing step organization.

Persist the server draft ID and reloadable draft content. Save before advancing dependent steps or creating the story. Preserve input on errors. If removing a cast member invalidates the controlled-character choice, make that visible and require a valid selection.

Keep existing studio navigation and return context. Full studio backend integration remains a later milestone, but do not show an in-memory-only preset as successfully persisted or selectable for real story creation.

### C3. Atomic creation and navigation

Use the existing story-creation service. Submit the current expected draft version with a stable idempotency key. Disable accidental repeated clicks while the operation is pending.

On acknowledgement, route to the returned story ID. If a request times out after the server commits, retry with the same key and navigate to the existing story.

Do not mark the story created before acknowledgement or recreate a completed draft during reload.

### C4. Minimal functional story view

Reuse Ember Vale’s shell, surfaces, typography, spacing and components.

- Show current location, cast, readable narrative and one supported action/advance control.
- Observer mode gets a map or explicitly labeled schematic plus event history.
- Player mode clearly identifies the controlled character and applies the backend’s role-aware reads and actions.
- Display pending, failure and committed states distinctly.
- Refresh authoritative presentation and history after completion.
- Keep the active story stable across browser reloads.
- Distinguish unavailable images from pending generation; no fake generation timers.

This is the first functional story view, not the full observatory or cinematic event modal. Do not expand into autoplay, director commands or image jobs during this stage.

### C5. Home, Stories and initial configuration

- Populate Home and Stories from real persisted records.
- Show a proper empty state on a fresh installation.
- Continue resolves the correct story’s saved state.
- The information icon displays the immutable initial setup snapshot.
- Editing a Library preset must not change an existing story’s initial-configuration display.
- Use actual stored metadata. If last-played tracking is missing, implement its intended semantics or omit the claim; do not substitute invented times.
- Preserve the existing visual composition and search/filter conventions for supported functionality.

**Deliver:** a browser-completable journey using live backend records, with no required demo-state dependency.

## 6. Stage D — acceptance and evidence

Use these as meaningful checks, not a requirement to create separate tests for every implementation detail.

| Scenario | Expected result |
|---|---|
| Fresh installation | Empty story shelf; usable starter presets; onboarding remains available |
| Wizard reload | Selected world revision, cast and mode restored |
| Player selection | Controlled character belongs to cast and resolves to correct runtime ID |
| Observer selection | No controlled character required |
| Repeated create | Same command produces one story |
| Failed creation | No partial playable world or orphaned creation records |
| Travel | Committed action completes; Wren’s location is Market in a fresh session |
| Retry after completion | Same command does not duplicate effects or advance again |
| Readable result | Presentation/chronicle exposes persisted outcome and narrative |
| Browser reload and API restart | Same story, clock, character state and event history |
| Two stories | Advancing A leaves B unchanged; switching views cannot display stale A data in B |
| Initial configuration | Remains stable after publishing newer Library preset revisions |
| Stale client/backend outage | Recoverable error; retained input; no false success |
| Visual comparison | Existing layouts preserved across populated, empty, loading and error states |

Commit the journey script or browser test. The second-push HTTP probe scripts were described as scratch-only; the next agent must be able to reproduce the proof from the repository.

Include:

- Exact starting commit and tested resulting commit.
- Startup and test commands, with credentials excluded from evidence.
- Test outcomes with pass/fail/skip distinctions.
- Migration-upgrade cases exercised.
- Browser screenshots or a short walkthrough of the real journey.
- Clear separation between deterministic tests, live HTTP checks and real-provider probes.
- Remaining placeholders and the next milestone.

Use the existing visual baseline in `docs/evidence/e0-visual/`. Stable fixtures remain appropriate for visual tests; production screens must reflect actual user data.

## 7. Suggested commit sequence

| Commit | Scope | Exit condition |
|---|---|---|
| 1 | Preset revision and migration repair | Fresh and existing databases covered; historical state preserved |
| 2 | Gameplay orchestration and travel proof | Persisted completed action and replay verified |
| 3 | Frontend contracts, preset reads and draft persistence | Wizard selections survive reload |
| 4 | Creation, story view, Home and Stories | Complete browser journey works |
| 5 | Focused failure/isolation checks and evidence | Repeatable acceptance proof and visual comparison |

Do not stop after commit 2 and label the user journey complete. Backend proofs and frontend completion are separate deliverables.

## 8. Deferred scope and durable constraints

After this milestone passes, resume the full handoff’s studio, provider, Player/Observer, intervention, image, character-evolution and save work.

Preserve these commitments while making the current changes:

- Smooth anime fantasy styling with versioned style packs.
- Character profile image first, then a reference-conditioned full-body portrait.
- Dynamic outfit, inventory and physical-state changes tracked separately from stable character identity.
- Immutable asset versions and subject/appearance revision checks on late job completion.
- Binaries stored outside database rows and disposable container layers.
- Map anchors and routes represented in versioned data.
- Real generation capability reported only after a configured provider is exercised.

None of these deferred features should become an excuse to postpone the small durable story journey.

## 9. Source references

All links below point to the reviewed second push; inspect the current branch before implementing and reconcile any newer changes.

- [Reviewed commit](https://github.com/joelhenwang/ember-vale/commit/d1aaea0a73fe6c551275298f31d4d01c566d5559)
- [Correction evidence](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/docs/evidence/a-corrections.md)
- [Backend journey evidence](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/docs/evidence/b-backend-journey.md)
- [Travel migration](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/backend/migrations/versions/0032_starter_travel.py)
- [Built-in presets](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/backend/src/worldsim/application/library/builtins.py)
- [Story creation](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/backend/src/worldsim/application/stories/create.py)
- [Travel tests](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/backend/tests/test_story_travel.py)
- [World routes](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/backend/src/worldsim/interfaces/http/routes/world.py)
- [Stage 1 routes](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/backend/src/worldsim/interfaces/http/routes/stage1.py)
- [Stage 0 orchestrator](https://github.com/joelhenwang/ember-vale/blob/d1aaea0a73fe6c551275298f31d4d01c566d5559/backend/src/worldsim/application/orchestration/service.py)

