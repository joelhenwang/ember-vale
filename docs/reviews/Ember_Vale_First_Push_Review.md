# Ember Vale: first-push review and next-agent direction

Reviewed commit: `2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93` (“first stage”), September 20, 2026.

## Verdict

Continue from this branch. The architectural direction is appropriate: Ember Vale remains the application and visual foundation, with a coherent Python backend imported underneath it. This push is an infrastructure checkpoint, not yet a working product milestone.

A comparison of Git tree blob hashes against `ab9161c59edc112b12db7b3081b9717a85a98c90` confirms that the existing Vue source files are unchanged. The only new frontend source files are the API helper and its tests; Vite configuration changed to add the proxy. Preserve that discipline when connecting the UI.

The committed evidence reports a successful Docker boot, migrations through 0031, database connectivity, proxy checks, and 41 frontend tests passing. This review inspected source and reproduced the readiness-helper logic in isolation; it did not independently run Docker, the full test suite, or a browser session. Treat the agent’s runtime results as reported evidence, not independent verification.

Sources: [E0 evidence](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/docs/evidence/e0-baseline.md), [E1 evidence](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/docs/evidence/e1-spine.md).

## Corrections before wiring the application

### 1. Fix database configuration consistency — priority high

In [compose.yaml](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/compose.yaml), the database service accepts POSTGRES_USER, but the API connection URL hardcodes the username embervale. Changing the documented username therefore produces a healthy database with an API that cannot authenticate.

In [.env.example](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/.env.example), the host-side connection is named DATABASE_URL. Both the application settings and Alembic read WORLDSIM_DATABASE__URL instead. A host-run backend using the example will not receive the intended Ember Vale URL and can fall back to the inherited localhost:5432/worldsim default.

Required changes:
- Use the configured username consistently in Compose.
- Supply the actual typed database environment key in the example and document how the host process loads it.
- Keep Compose’s internal db:5432 address distinct from the host’s localhost:5433 address.
- Document the existing public-bind/API-key startup requirement with copyable local startup instructions; do not quietly remove that guard.
- Prove startup with a non-default database username and verify that host and container execution resolve to the intended isolated database. Do not touch an existing PixelSaga database.

### 2. Fix the readiness contract — priority medium

[src/api/client.ts](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/src/api/client.ts) declares schema_version as a string, while [the backend schema](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/backend/src/worldsim/interfaces/http/schemas.py) returns an integer.

The allChecksPass function accepts every status except failed. Executing its actual function body gives:

| Check status | Actual result |
|---|---|
| ok | true |
| degraded | true |
| unknown | true |
| failed | false |

This contradicts its “every reported dependency check passed” contract. It is not yet a visible UI regression because the helper is not wired into the views, but it should be corrected before consumers rely on it.

Required changes:
- Use the authoritative generated contract for consumed API types, or temporarily align the small handwritten contract exactly.
- Define success positively using the backend’s documented successful check status.
- Cover degraded, unknown and empty checks with meaningful tests.
- Keep readiness separate from “a user has created a story.” The inherited readiness check marks an empty world table degraded. An empty installation must still allow onboarding, preset selection and first-story creation.
- Do not seed a fake played world merely to turn readiness green. Decide whether world-count readiness is advisory or remove it from infrastructure readiness.
- Health readiness does not prove live text or image generation works; report provider capability separately.

### 3. Restore backend regression coverage — priority high before engine edits

The tree contains the imported backend but no backend/tests directory. Four new frontend helper tests cannot validate story creation, database transactions or turn execution.

Bring over the relevant tests and fixtures from the exact backend donor revision, adapting only environment assumptions. Establish a runnable subset for migrations, atomic story creation, idempotency, turn commit and reload before modifying these paths. Add integration tests for the new frontend/backend journey as it is wired.

Do not declare the imported engine verified merely because the HTTP process starts.

### 4. Capture the visual baseline now — priority medium

The E0 evidence explicitly says screenshots were not captured. The source preservation is valuable, but the visual baseline must exist before API wiring changes loading, error, empty and populated states.

Capture Home, the New Story cast step, Library characters/worlds, Stories, Settings and both editors at a normal desktop viewport. Keep equal character-card dimensions. Include one narrower viewport. Use stable fixtures for visual comparisons, clearly separated from the production data path.

Do not require the runtime app to show fake stories just to match a screenshot.

## Inherited integration gap to address during the next milestone

[Built-in presets](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/backend/src/worldsim/application/library/builtins.py) define Hearth and Market but an empty travel list. [Story instantiation](https://github.com/joelhenwang/ember-vale/blob/2ddaca0f9fe4dbc6a98d1916c0a2bc04ebcb7b93/backend/src/worldsim/application/stories/create.py) creates locations with empty routes and does not materialize preset travel connections.

This is inherited backend behavior, not an Ember Vale UI regression. However, it will block a meaningful Hearth-to-Market movement demonstration unless addressed.

Define the starter’s intended connection in versioned preset data, validate both endpoints, and instantiate its corresponding travel records inside the same story-creation transaction. Test that invalid travel data rolls creation back and that valid movement persists. Drawing a route on the map is insufficient.

## Next implementation assignment: E1 corrections, then one E2 journey

Use the existing handoff in docs/handoff/Ember_Vale_Product_and_Backend_Plan.md as the full product specification. This review narrows the next delivery; it does not replace that plan.

### Delivery A: make the foundation reproducible

Complete the four corrections above. Record the full SHA of the imported PixelSaga revision: the evidence names 653614d from feat/ember-vale-integration, while the earlier handoff pinned 785713d. Explain relevant backend differences and document deliberate fixes. A changed donor revision is not automatically wrong; it needs traceable provenance.

Remove committed backend/src/worldsim.egg-info build output and ignore it. Include exact startup, migration and selected test commands in the root README.

Deliver evidence of clean startup without requiring undocumented edits.

### Delivery B: implement create → advance → reload → continue

1. **Preserve the existing shell.** Keep Ember Vale’s router, components, typography, colors and layout. Add API/state adapters behind the current views. Do not import PixelSaga frontend code or replace Vue components with a second application.

2. **Expose real preset data.** Make Ember Vale, Hearth, Market, Wren and Ash available idempotently as reusable starter definitions. User-created stories remain empty until creation succeeds. Illustrative characters and worlds are not required seed data.

3. **Wire the existing New Story flow.** Persist the draft and selected preset revisions. Select/create the cast before choosing a controlled character in Player mode. Observer mode must not require a controlled character. Preserve draft state across reloads; return actionable validation errors without losing input.

4. **Create atomically.** Reuse and test the imported creation transaction and request-replay behavior. Snapshot initial configuration and preset revisions, instantiate the world/cast/routes, and establish access in one consistent operation. Disable accidental repeat submissions and retain the same idempotency key for retries of the same command. A retry must not create a duplicate story.

5. **Wire Home and Stories to persisted records.** Display actual stories, real last-played metadata and a true empty state. Continue uses a stable story identifier and loads its committed state. The information icon shows immutable initial configuration, not today’s edited Library presets. Demo cards must not masquerade as saved user stories.

6. **Add the smallest functional story view.** Reuse the existing visual system. Render the current location, cast and narrative; provide one manual advance/action control. In Observer mode use a map or explicitly labeled schematic plus an event feed. Do not build autoplay, interventions and image generation in this same slice.

7. **Commit one real beat.** A deterministic development model is acceptable for this milestone, visibly identified as such. Exercise the real request, rule validation, transaction and event persistence paths. UI success must follow server acknowledgement. Retry must not double-apply an action; failed generation must not partially advance state.

8. **Prove persistence.** Leave the story, reload the browser, restart the API and continue. Story ID, committed beat, locations, character state and event history must agree. State must not depend on frontend memory or a component timer.

9. **Exercise failure and concurrency.** Cover validation errors, backend unavailability, a duplicate request and a stale-version action. Preserve user input and show a recoverable error. A stale client must refresh/reconcile rather than silently overwrite newer state.

### Required evidence for Delivery B

| Check | Pass condition |
|---|---|
| Fresh database | Valid empty Stories page; starter presets selectable; first story can be created |
| Wizard reload | Cast and mode choices survive; Player selection belongs to selected cast |
| Atomic creation | One story on replay; invalid creation leaves no partial world |
| First beat | Server persists the action/event and advances state exactly once |
| Travel | Defined Hearth/Market connection works through backend rules |
| Resume | Browser reload and API restart preserve committed state |
| Configuration information | Initial configuration remains stable after Library preset edits |
| Visual preservation | Existing screens retain their composition with live/loading/empty/error data |
| Honest capability reporting | Development model and unavailable image generation are clearly distinguished from live providers |

Provide exact commands and results, a short browser walkthrough or screenshots, and a list of remaining placeholders. Separate deterministic tests from any real-provider probes.

## Keep later features in their planned stages

After Delivery B passes, continue the existing handoff sequence: studios and preset revisioning; live text settings; richer Player/Observer views; director interventions; image jobs; evolving character appearance; saves and later world simulation.

When image generation is implemented, retain the approved-profile → reference-conditioned full-body sequence, immutable subject/appearance revisions and stale-job protection. Persist image binaries outside database rows and outside disposable container layers. Do not report live generation until a configured adapter has actually been exercised.

The next push should demonstrate a durable story journey in the existing Ember Vale UI. More copied infrastructure or more polished demo screens alone will not complete that milestone.

