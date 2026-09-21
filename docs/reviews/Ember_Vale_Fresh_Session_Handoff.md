# Ember Vale — fresh-session implementation handoff

**Prepared:** 21 September 2026  
**Destination:** https://github.com/joelhenwang/ember-vale  
**Reviewed baseline:** [6b4771ad7df1f406126cb0204d8d875a0d47258d — “11th push”](https://github.com/joelhenwang/ember-vale/commit/6b4771ad7df1f406126cb0204d8d875a0d47258d)  
**Immediate assignment:** finish the four open E6 intervention findings below, verify the complete behavior, then resume the established product roadmap.

## 1. Start here: instructions to the incoming agent

You are continuing an existing implementation, not starting a migration or designing a replacement application. Ember Vale is the chosen Vue frontend and destination repository. Its Python worldsim backend has already been integrated from PixelSaga. Preserve the existing styling, routes, components, migrations, user data, and accepted behavior.

The long recovery correction cycle is CLOSED. Creation-departure is CLOSED. Preserve those regressions. Reopen them only for a concrete new regression caused by your changes.

The current work is E6: Director/God seats, interpretation, intervention queue, and execution through normal beat advancement. The happy-path travel integration exists. Four source-review findings remain; they are the next implementation task, not merely optional polish.

Work autonomously on this bounded scope. Read the actual checkout and applicable instructions, reproduce each finding with a meaningful test, fix the underlying behavior, and report what was actually verified. Do not expand into a general engine rewrite, frontend redesign, or another speculative reliability campaign.

### First actions

1. Inspect branch, HEAD, working tree, and local instructions. Preserve uncommitted work. The previous agent repeatedly reported “uncommitted,” while subsequent GitHub commits contained that work; inspect reality rather than relying on that phrase.
2. Compare HEAD with the baseline above. If newer work already addresses a finding, verify it instead of reimplementing it.
3. Read the documents listed in section 3, then trace the files in section 7.
4. Establish the local runtime using the repository configuration; do not overwrite an existing .env or reset a database.
5. Complete E6-A through E6-D with focused regressions and the normal HTTP acceptance journey.
6. Update evidence and the status ledger. Keep implementation, deterministic verification, live-provider verification, and remaining gaps separate.

This handoff authorizes continuation guidance, not a remote push or deployment. Follow explicit authorization in the new session for those operations. Earlier agent messages saying a push was “yours” do not establish that this reviewing assistant pushed anything.

## 2. What we are building

Ember Vale is a persistent, LLM-assisted fantasy storytelling RPG and world simulator. Characters have identities, distinct voices, goals, memories, relationships, activities, equipment, and physical state. The LLM proposes actions and writes narration/dialogue; backend rules validate and commit canonical outcomes. Images illustrate accepted state and never create game facts.

The intended loop is: configure a world and cast → choose how to play → create a durable story → act/observe/direct → resolve a beat → inspect narration, dialogue, map and characters → leave and resume the same world later.

The starter canon is deliberately small:

| Subject | Canonical starter content |
|---|---|
| World | Ember Vale |
| Places | Hearth and Market, with traversable connections |
| Wren | Short copper hair, quick grey eyes, patched traveler coat |
| Ash | Charcoal hair tied back, ash-grey cloak |

Extra characters, places, counts, and sample stories in mockups are illustrative. Do not seed fictional played stories to make an empty installation resemble a screenshot.

### Modes

| Product mode | Backend vocabulary | Intended behavior |
|---|---|---|
| Player | player | Act as one selected runtime character; scoped knowledge and actions |
| Observer | watcher | Inspect and advance the world |
| Director | director | Propose supported hooks/arcs and narrative direction |
| God | deity | Force supported, validated changes with auditable consequences |

Effective grants and backend capabilities are authoritative. Headers and frontend controls cannot grant power. A bound Player seat is not silently displaced by the operating-seat UI. Distinguish intended product policy from inherited engine capabilities; reconcile differences explicitly.

Current supported confrontation is sparring, not arbitrary lethal combat. “Force” never bypasses reference integrity, story isolation, authorization, or valid state transitions.

## 3. Read order and source precedence

Read these repository documents:

1. [Original product/backend plan](https://github.com/joelhenwang/ember-vale/blob/6b4771ad7df1f406126cb0204d8d875a0d47258d/docs/handoff/Ember_Vale_Product_and_Backend_Plan.md) — full product requirements, E0–E11 packets, design and domain constraints.
2. [Original START_HERE](https://github.com/joelhenwang/ember-vale/blob/6b4771ad7df1f406126cb0204d8d875a0d47258d/docs/handoff/START_HERE.md) — ownership and frontend-preservation rules; its initial setup tasks are historical, not instructions to repeat completed work.
3. [Current E6 execution evidence](https://github.com/joelhenwang/ember-vale/blob/6b4771ad7df1f406126cb0204d8d875a0d47258d/docs/evidence/e6-execution.md).
4. [E6 seats/queue evidence](https://github.com/joelhenwang/ember-vale/blob/6b4771ad7df1f406126cb0204d8d875a0d47258d/docs/evidence/e6-director-interventions.md).
5. [Accepted recovery sequences](https://github.com/joelhenwang/ember-vale/blob/6b4771ad7df1f406126cb0204d8d875a0d47258d/docs/evidence/recovery-complete-sequences.md).
6. [Visual reference inventory](https://github.com/joelhenwang/ember-vale/blob/6b4771ad7df1f406126cb0204d8d875a0d47258d/docs/handoff/references/README.md).
7. Earlier evidence only when tracing a relevant invariant: docs/evidence/stage-a-b.md, stage-c-d.md, third-push-corrections.md, fourth-push-corrections.md, fifth-push-corrections.md, and fifth-push-followup.md.

This handoff supplies the latest review findings that are not necessarily recorded in a committed review document.

**Important stale-document warnings:**

- The root README still describes several original fixture/demo implementations. Do not use it as a current feature-completion ledger.
- Its old Vite wildcard-bind comment is stale: current vite.config.ts defaults to 127.0.0.1.
- backend/README.md documents initial vendoring and an older migration count. Do not use it to forbid legitimate backend fixes or infer the current migration head.
- The original plan pins older source revisions; the baseline at the top of this document is the reviewed implementation.
- No AGENTS.md appeared in the fetched baseline tree. Check the actual local checkout and parent directories anyway.
- Paths beginning /absolute/path/ in agent reports were machine-specific reporting placeholders. Resolve real paths from the repository root.

## 4. Visual and UX commitments

Keep the existing light anime-fantasy identity: warm ivory/parchment surfaces, teal actions, restrained gold ornamentation, Garamond-family typography, clean smooth illustrations, readable hierarchy, and efficient use of space. Reuse existing components and style tokens. Do not return to PixelSaga's black debug-like forms or import its frontend/router/CSS.

Main destinations: Home, New Story, Stories, Library, Settings; secondary Help/Onboarding and Profile/Account. A local operator profile does not imply an implemented SaaS account system.

New Story order is **World → Cast → Mode → Story → AI → Review**. Character selection precedes choosing whom to control. Stories exposes immutable original setup through an information action. Library contains worlds, characters, style packs, and templates. All character cards have equal dimensions within a grid/breakpoint.

The intended observatory is map-led: approximately 50–80% of the screen for the world map, character portrait markers, contextual activity indicators, a chronological event panel, beat/play/pause/pacing controls, and a direction input. Existing minimal gameplay controls prove functionality but do not automatically satisfy the final observatory design.

Event focus modal: around 80% of the viewport; approximately 70% illustration / 30% storytelling on desktop. Prioritize narration and character dialogue with speaker portraits. Keep its title modest. Do not waste the text panel on Participants/What changed sections. The obscured background is the observatory map, not a duplicate scene illustration. Responsive layout and keyboard/focus behavior must be implemented.

Creation studios use structured forms and sticky previews. Character generation is profile first, then a full-body image conditioned on that actual selected profile. Show both. Equipment, outfit, injuries and authorized physical changes affect runtime body inputs without silently changing identity.

Reference PNGs in docs/handoff/references:

- character-editor-voice.png
- character-profile-full-body.png
- live-character-details.png
- world-editor-places.png
- world-preset-details.png

Existing Ember Vale components are the primary implementation baseline. Reference screenshots are not production artwork to crop into cards.

## 5. Accepted foundation: preserve it

These items were implemented/reported and reviewed over previous pushes. This is not a claim that every full roadmap packet is complete.

| Area | Current accepted foundation |
|---|---|
| Backend spine | Coherent FastAPI/Postgres worldsim engine, migrations, same-origin frontend transport and generated contract |
| Starter revisions | Corrected starter published as revision 2; revision 1 preserved; immutable existing story setup |
| Story creation | Server drafts, acknowledged save/validation, stable-key atomic creation and ambiguous-submit replay |
| Wizard | Six steps, normal World entry, Quick Start review, pinned revisions, persisted step/draft, controlled actor after cast |
| Story room | Effective grant and runtime actor identity, supported travel and atomic beat advancement, resume and history continuation |
| Isolation | Frozen story-operation context and stale-response protection; no name-based actor matching |
| Recovery | Draft-scoped receipts and recovery, route-leave snapshots, version/content-based reopening, explicit conflict choice |
| Creation departure | Disposed wizard cannot redirect a departed user when creation completes |
| Verification | Scripted create/restart/resume and browser journeys; separate deterministic-provider labeling |

Recovery closure baseline was commit 758b8d70. Its full delayed-success and delayed-failure sequences passed isolated reviewer execution with mocked dependencies. They restore Newest after memory reset, save it, clear recovery, and reopen from the server.

Keep planBootRecovery shared by view and tests. Preserve receipt ID/version/key across retries and reopening. Local content tokens establish equality against the latest recorded content; they are not a universal chronological recency guarantee.

## 6. Current E6 state and evidence limits

E6 seats/queue first appeared in 0d559782. The current 6b4771ad implementation adds:

- Operating-seat selection and persisted grant badge.
- Typed submit/list/read/edit/cancel operations and queue UI.
- Pending filing retry with preserved key and world/role checks.
- Queue draining within advance_phase(..., drain_queue=True), after completed-beat replay checks.
- Pre-decision effects and post-seal directed-attempt planning.
- Directed intents tagged with direct: identifiers.
- Attempt completion recorded after a scene commit with an event reference.
- Deterministic HTTP travel journey and service-level intervention tests.

Reported gates at this baseline: 125 frontend tests; typecheck/lint/touched-file formatting clean; 13 intervention and 30 orchestration-neighbor backend tests; browser walkthrough passing. These are prior agent reports, not tests rerun while preparing this handoff.

The reviewer inspected current source and identified the four findings below. They are source-level findings, not claims of a complete live exploit or exhaustive concurrency reproduction.

The dev gateway does not return intervention plans, so the browser walkthrough covers submission/clarification/edit/cancel rather than executed directions. Deterministic HTTP integration is acceptable for engine correctness; it is not live LLM capability verification.

## 7. Implementation map

| Responsibility | Start with |
|---|---|
| Queue interpretation/execution | backend/src/worldsim/application/interventions.py |
| Beat sequencing and scene completion | backend/src/worldsim/application/orchestration/stage1.py |
| Normal advance HTTP route | backend/src/worldsim/interfaces/http/routes/stage1.py |
| Execution admission/leases | backend/src/worldsim/application/execution.py; application/tasks/service.py |
| Intervention types/persistence | domain/interventions.py; infrastructure/repositories/interventions.py; infrastructure/models/interventions.py |
| Effect commands | application/commands/activities.py, director.py, deity.py; application/conditions.py |
| Canonical scene transaction | application/transactions and scene commit callers; trace actual dependencies |
| Queue frontend | src/composables/useInterventions.ts and its .spec.ts |
| Room UI | src/views/PlayView.vue; src/composables/useStory.ts |
| HTTP transport/operations | src/api/http.ts; src/api/worldsim.ts |
| Generated contract | content/schemas/openapi.json; content/clients/worldsim.ts; backend/scripts/gen_ts_client.py |
| Focused backend proof | backend/tests/test_intervention_advance.py; test_intervention_queue.py |
| Neighbor proof | test_stage1_orchestration.py; test_stage1_api.py; test_scene_commit.py; test_s2_director.py; test_s2_roles.py |
| Accepted draft recovery | src/composables/useStoryDraft.ts and .spec.ts; src/views/NewStoryView.vue |
| System journeys | scripts/journey.mjs; scripts/walkthrough.mjs |

Paths beginning domain/, application/, or infrastructure/ in this table are relative to backend/src/worldsim/.

## 8. Immediate execution plan: four open findings

### E6-A — authoritative action identity (high priority)

**Observed:** _direct_attempt uses setdefault for character_id and snapshot_id. Model-supplied values survive. The construction {"family": targets["family"], **action} also lets action.family override the outer validated family. The shape-validation path uses the same pattern.

**Risk:** permission and target checks refer to the outer step, while the constructed action can describe a different actor, snapshot or family.

**Implement:** define one normalization/validation boundary. Assign authoritative actor, current sealed snapshot, and validated family after accepting model-proposed action fields, or reject contradictory supplied fields explicitly. Apply the same rules consistently at interpretation and execution. Model JSON cannot choose authority.

**Tests:** missing identities receive server values; contradictory actor/snapshot/family is rejected or overridden according to the documented contract; an own-player outer step cannot produce another actor's action. Validate the resulting action, not only the outer plan.

### E6-B — competing attempts for one actor (high priority)

**Observed:** plan_attempts allocates a directed dictionary and checks it for duplicate actors but never records accepted actors into it. Multiple attempts pass. The orchestrator later writes a dictionary keyed by actor, retaining only the last.

**Implement:** reserve the actor immediately when accepting a step. Define deterministic precedence using stable queue/step ordering. Subsequent attempts must be explicitly deferred or failed with a reason; none may silently disappear. Preserve player-intent precedence and expose the outcome in queue state.

**Tests:** two interventions for Wren; two steps for Wren in one intervention; a player-filed intent competing with a direction. Assert one selected attempt, explicit remaining status, and consistent results after replay.

### E6-C — effect identity, ownership and interruption (high priority)

**Observed:** _apply_effect_step commits a gate separately from applying effects and marking completion. A losing caller that sees no completed step assumes a crashed predecessor and also executes. That condition also describes a predecessor still running. Conditions are deduplicated by public label; hooks by title. These are display values, not execution identities, and can suppress distinct legitimate directions.

**Do not simply add another status flag.** Trace the full transaction/admission model first.

Current execution.py uses durable task slots, a 300-second lease and phase:{index} scope. Determine how active owners, lease expiry, retries, direct service entrypoints, and consecutive phases interact. Do not infer universal single-writer safety from a function name.

Choose the smallest coherent mechanism:

- Effect plus execution receipt in one transaction where feasible; or
- Effect-specific immutable operation keys/unique constraints plus a durable outcome and explicit recovery/ownership protocol.

Use intervention ID + step identity (and revision if step identity can be reused) for execution deduplication. Distinct operations may share a title/label; decide their game semantics explicitly, never treat their text as proof that the same operation already ran.

A replay must recover the exact prior outcome. An active owner's unfinished work is not automatically available for takeover. Cancellation/application ordering must remain well-defined.

**Tests:** overlapping execution of one step; interruption after effect commit but before completion marking; retry after restart; two distinct directions with the same title/label; completed-beat replay; cancelled work cannot newly apply. Assert canonical state and effect/event counts, not just status labels.

**Mid-scene crash boundary:** current evidence explicitly leaves scene re-commit idempotency unproven. Separate completed-beat replay safety from partial-beat recovery. Determine whether scene outcome receipts can be reused or atomically tied to intervention completion. Do not claim universal lossless/exactly-once execution until the crash window is covered. If a bounded E6 correction cannot close inherited scene behavior, record the exact remaining failure window and keep the stronger reliability acceptance open; do not hide it as “pre-existing.”

### E6-D — correlate ambiguous filings (medium priority)

**Observed:** useInterventions.select() clears pending whenever any queue item is found. Selecting old direction A can therefore clear unresolved filing B.

**Implement:** reconcile pending only with a server item/receipt matching its client request key and owning world, with appropriate identity checks. If the projection lacks that identity, add a deliberate typed projection/query and regenerate the contract. Selecting unrelated items should only change selection.

Keep retry bound to the original filing context. A changed world/seat must not reinterpret it. Discard means abandoning local retry/reconciliation, not cancelling an operation which the server may already have accepted. Say this plainly in the UI.

**Tests:** pending B + select A retains B; matching B clears pending; retry reuses the key; changed context refuses retry; explicit discard permits a genuinely new filing and makes no false cancellation claim.

### Suggested delivery order

Implement A and B together as attempt-planning correctness. Implement C as the execution-durability slice. Implement D as frontend receipt reconciliation. Keep commits/diffs coherent; do not postpone the focused tests until all changes are complete.

## 9. Acceptance gate for closing E6 execution

Use the normal HTTP path with deterministic model output:

1. Create a real starter story and acquire an authorized seat.
2. Submit “Send Wren to Market”; observe a queued item and its typed step.
3. Advance through the normal endpoint; observe the started activity and its reference.
4. Advance as necessary; assert Wren arrives at Market.
5. Replay the completed beat; assert unchanged canonical versions/outcomes and no duplicate operation.
6. Restart/reopen; assert durable world and queue status.
7. Verify cancel-before-application, unauthorized/player operations, competing attempts, and the E6-A contradictory-identity cases.
8. Exercise E6-C interruption and concurrency cases at controlled boundaries.
9. Verify the E6-D unrelated-selection case in the frontend.

Starting travel is not arrival. A completed direction step can mean “journey started” if its result_activity_id and copy make that clear. An attempt can complete after a resolved failure; completion means execution was durably recorded, not guaranteed success.

After meaningful changes, run affected backend and frontend gates and the existing journey. Preserve the recovery suite. Do not demand live LLM output for deterministic transaction testing, but do not label fixture results as live generation.

## 10. Local setup and verification

Confirm installed toolchain versions against lockfiles/configuration. Backend tests must run from the repository root: relative content/dnd paths previously caused misleading failures from the wrong working directory.

Current configured defaults:

| Service | Default |
|---|---|
| Vite | 127.0.0.1:5173 |
| API | localhost:8101 |
| PostgreSQL | localhost:5433 |
| Database / volume | embervale / pgdata-embervale |
| API prefix | /api/v1 |

The Vite proxy injects the operator key from root environment configuration on the server side. Do not bundle credentials, put them in URLs, print them in evidence, or expose that authenticated proxy with a wildcard bind.

### Frontend

Run from repository root:

```bash
npm ci
npm run typecheck
npm run lint
npm run test
npm run build
```

Use targeted Prettier checks for touched files and report unrelated baseline failures separately. Prior evidence mentions existing formatting issues in HeroCard, SetupDialog, StoriesView and a generator line; recheck current status rather than copying those claims forward. Do not run blanket formatting to bury unrelated changes.

### Backend and stack

If .env already exists, preserve it. Configure from .env.example only when needed, using the operator's actual local settings.

```bash
docker compose up -d
uv sync --project backend --group dev
uv run --project backend --group dev pytest backend/tests/test_intervention_advance.py backend/tests/test_intervention_queue.py
```

Ensure the host test database URL points to the isolated local database server and inspect test fixtures before running database tests. Do not drop the user database or execute docker compose down -v to obtain a clean test.

Run the affected orchestration/scene/role neighbors as identified by changed code. Run the configured backend lint/type checks where applicable. Health endpoints are /api/v1/health/live and /api/v1/health/ready. Discover current migration head from the running/configured environment.

### Contracts

After DTO or route changes, use the sanctioned generators:

```bash
uv run --project backend --group dev python -m worldsim.interfaces.http.export --out content/schemas/openapi.json
uv run --project backend --group dev python backend/scripts/gen_ts_client.py --out content/clients/worldsim.ts
uv run --project backend --group dev python backend/scripts/gen_ts_client.py --check
```

Confirm current CLI options if the generator changed. Never hand-edit generated clients to conceal an unsupported contract.

### Journey and browser evidence

scripts/journey.mjs exercises create and restart/resume; inspect its current arguments before running --resume. Preserve the created story identity across restart.

scripts/walkthrough.mjs uses playwright-core and currently assumes installed Windows Edge and a named Compose API container. Inspect its configuration before running elsewhere. Parameterize executable/container discovery only as needed; do not pretend the harness ran on an incompatible environment. Its stop/pause scenarios must restore the API in cleanup.

Screenshots are not proof of 200% zoom or keyboard accessibility. Browser intervention execution remains unverified with the current dev gateway; the deterministic HTTP path supplies execution evidence.

## 11. What follows E6

Do not assume E3–E5 are fully complete merely because E6 is underway. Reconcile actual implementation with the original packet checklist and produce a compact implemented/verified/blocked ledger.

| Packet | Remaining target to assess after E6 closure |
|---|---|
| E3 Library/studios | Real partial drafts, immutable revisions, complete world/character editors, nested return flow |
| E4 Settings/live text | Real provider/profile settings and probes; actual validated narration/dialogue |
| E5 Player/Observer | Full adventure/observatory UI, perspective filtering, activities and serialized autoplay |
| E7 Artwork | Durable assets/jobs, configured image adapter, approved profile→body lineage, event illustration/modal |
| E8 Living characters | Owned/equipped inventory, physique/injuries, relationships/memory and corresponding image inputs |
| E9 Saves/operations | Consistent checkpoints/branches where included, complete backup/restore and real Stories actions |
| E10 Long-term simulation | Safe macro progression, interruptions, era/focus/lineage support |
| E11 Release hardening | Visual/accessibility/deployment verification and honest feature matrix |

Historical known gaps include live-provider verification, studio backend work, rich gameplay presentation, and 200% zoom. Their current extent needs inspection; do not claim all are still absent or all are finished without evidence.

### Future art invariants

Use a new versioned smooth-anime style pack; preserve pixel-saga-v1.json history. Start with clean Ember Vale map, Hearth/Market scenes, Wren/Ash portraits, and reusable creation preview art—not the mockup cast. Keep map anchors/routes in versioned data.

Assets live outside database rows, behind versioned records and pending/ready/failed state. Validate size/MIME; use authenticated retrieval/object URLs with cleanup; no executable uploaded SVG or arbitrary remote fetch. No generation on component mount. Cache immutable versions and reject wrong-subject/stale completions. Event images use event-time state. A render never grants equipment or changes injuries.

## 12. Required delivery report

At the end of this bounded E6 correction, provide:

- Actual branch, HEAD, and working-tree state; commit SHA when committed.
- A–D status with changed paths and concrete behavior.
- Exact commands/results, separating checks run now from inherited evidence.
- Canonical effect/replay assertions and controlled interruption boundaries tested.
- Remaining limitations, especially partial-scene recovery and live-provider/browser execution.
- Screenshots for changed UI at recorded viewport sizes.
- The next product packet proposed, grounded in the actual implementation ledger.

Update docs/evidence/e6-execution.md or add a clearly superseding evidence document. Correct overbroad guarantees instead of leaving contradictory reports. A green count alone is insufficient; the report must explain which failure scenarios were proved.

## 13. Completion checklist for this session

- [ ] Current checkout/work preserved and compared with the reviewed baseline.
- [ ] E6-A authoritative identities fixed and tested.
- [ ] E6-B actor conflicts deterministic and visible.
- [ ] E6-C execution identity/ownership verified across the stated concurrency and interruption boundaries.
- [ ] E6-D unrelated queue selection cannot clear pending filing.
- [ ] Normal HTTP travel/arrival/replay/restart journey remains correct.
- [ ] Closed recovery/creation-departure regressions remain intact.
- [ ] Contracts regenerated where necessary; relevant gates pass or failures are accurately attributed.
- [ ] Evidence distinguishes implemented, deterministic-tested, live-tested, and unproven behavior.
- [ ] No frontend redesign, destructive reset, invented provider success, or unauthorized push/deployment.

**Resume instruction:** begin with E6-A and E6-B in the current checkout. Keep E6-C's transaction investigation bounded to the execution path under review. Finish A–D, then return to the existing product plan rather than another migration.

