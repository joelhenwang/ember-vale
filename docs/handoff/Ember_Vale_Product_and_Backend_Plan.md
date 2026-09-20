# Ember Vale: product brief and backend implementation plan

**Audience:** a fresh coding agent working in `joelhenwang/ember-vale`.

**Objective:** turn the existing Ember Vale Vue application into a working, persistent, LLM-driven fantasy storytelling RPG and world simulator. Work on top of its existing styling, views and components. Build the backend and replace demonstration behavior with real behavior. Do not migrate the frontend into PixelSaga.

This document supersedes the previous frontend-into-PixelSaga integration approach. It is self-contained; the agent need not reconstruct the design conversation to understand the product.

## 1. Project ownership and rules of execution

Ember Vale is the destination repository and frontend authority. Preserve its current branding, fonts, theme, navigation, component structure, card layouts and editing panels unless a concrete bug or missing interaction requires a local change. Do not replace its UI with PixelSaga views or simplify it into generic forms and tables.

PixelSaga is a backend reference and potential source of reusable code, contracts, tests and clean artwork. Its frontend, App, router, CSS, layout decisions and project-wide instructions are not part of the transfer. Follow instructions in the actual Ember Vale checkout. Do not copy PixelSaga's AGENTS.md into this project or introduce its static-mock approval process simply because it exists in the reference repository.

The user has selected Ember Vale as the base. Ordinary API wiring, error/loading states and bug fixes can proceed without repeated aesthetic approval. Build missing gameplay screens using the included design references and the existing design system. Preserve the appearance of completed pages through screenshot comparisons. No broad UI rewrite as a prerequisite to backend work.

Use an isolated working branch. Preserve existing work and user data. Keep PixelSaga read-only during assessment. Do not deploy, push, overwrite another repository, or reset an existing database without authorization in the coding session. Local implementation, tests and reversible development setup are expected.

### Source baseline checked for this plan

| Repository | Main commit | Interpretation |
|---|---|---|
| Ember Vale | `ab9161c59edc112b12db7b3081b9717a85a98c90` | Existing Vue UI with fixture catalogs, in-memory drafts and simulated provider/image behavior |
| PixelSaga | `785713dcf6fd4c071b04944469c5cbbb56a628bc` | FastAPI/Postgres world engine, story catalog/drafts/presets/provider configuration and earlier gameplay work |

These are source-review findings, not results of running either application. The latest main branches returned those revisions when checked. Work in progress may exist on other branches or locally. Inspect the actual checkout before changing anything. Old README test counts and migration heads are not automatically current.

## 2. The product we are building

Ember Vale is a persistent fantasy world inhabited by characters with distinct identities, personalities, voices, memories, goals and relationships. An LLM helps choose actions and produces narration and character-specific dialogue. A rules engine validates what is possible and commits authoritative outcomes. An image model illustrates places, characters and events from accepted story state.

The user can inhabit a character or observe and influence the wider world. Characters continue to act according to their circumstances. The experience should feel like an illustrated, evolving story with game consequences, not a chat log with unrelated pictures.

The core loop is:

1. Configure a world and cast, or use reusable presets.
2. Choose a play mode and generation settings.
3. Enter the story, observe the current situation and act or advance time.
4. Resolve character actions, world changes and interactions consistently.
5. Read narration and dialogue, inspect the map/characters, and optionally direct future events.
6. Leave and return later with the same state, history and configuration.

The initial starter setting is **Ember Vale**, with **Hearth**, **Market**, **Wren** and **Ash**. Wren has short copper hair, quick grey eyes and a patched traveler coat. Ash has charcoal hair tied back and an ash-grey cloak. Extra people, worlds and stories in the UI are demonstration fixtures, not required runtime canon. Do not populate every user installation with fictional play history to match the screenshots.

### Play modes and authority

Use two high-level setup choices: **Player** or **Watch**, with Watch exposing **Observer / Director / God**. The same character cast is selected before choosing the mode. Backend capability checks, not a client dropdown alone, determine permitted actions.

| Mode | What the user can do | What they see |
|---|---|---|
| Player | Submit attempts for one selected character; choose suggestions or free text; advance the next beat | That character's perceived scene and permitted knowledge |
| Observer | Step/pause/play the simulation and inspect characters/events | World overview; no arbitrary canonical interventions |
| Director | Observer controls plus propose events, goals and instructions for the world to interpret | World overview and intervention queue |
| God | Director controls plus explicitly force supported changes | World overview with forced changes recorded in history |

This is the intended Ember Vale policy. If reusing PixelSaga's capability table, reconcile it explicitly: its role vocabulary and some activity permissions do not exactly match this simplified product policy. Separate the local operator's right to manage the application from a story mode's permission to alter its world. Never trust a body field claiming `role=god`.

“Force” can bypass selected narrative uncertainty, not database integrity. It cannot create cross-story links, negative item quantities, invalid references or arbitrary executable effects. Mode changes, if exposed later, are recorded separately from the immutable initial configuration.

## 3. Scope and completion levels

The full target includes application pages, reusable world/character creation, Player and Observatory gameplay, durable simulation, interventions, distinct character dialogue, image generation, current character state, story recovery and operational tooling.

Deliver in useful increments:

| Milestone | Working outcome |
|---|---|
| A: Persistent application | Real Library, Settings, story drafts, story creation/catalog/resume; existing UI retained |
| B: Playable story | Player and Observer, real text provider, canonical turns/events/dialogue, pause/resume and persistence |
| C: Directed illustrated world | Director/God queue, conditions, event modal, profile-to-body image workflow, dynamic equipment/physical state |
| D: Long-lived worlds | Checkpoints/branches, long-term memory, safe macro advancement, lineage/succession/era summaries where supported |

Milestone A alone is not a complete game. Fake-provider tests alone are not proof of Milestone B/C live generation. Track implemented, tested and externally blocked capabilities separately. Lack of credentials should not block unrelated implementation, but must remain an explicit live-provider acceptance dependency.

Do not add multiplayer, subscriptions, a cloud account system, marketplace, a new frontend framework, Kubernetes or a general-purpose agent platform. Start with one local/self-hosted operator and multiple independent stories. Keep the design compatible with future expansion without building it now.

## 4. Keep the frontend, replace its demonstration behavior

Preserve the root Vue app and its Node/Vite configuration. Keep `src/components`, existing views and styling as the base. Add a backend directory alongside them. The following boundary changes are necessary:

| Existing Ember Vale module | Required change |
|---|---|
| `src/game/state.ts` | Replace fabricated current/recent story state with API-derived state |
| `src/game/catalog.ts` | Replace fixture world/character/style/template arrays and global wizard state with persisted data/drafts |
| `src/game/stories.ts` | Real catalog, lifecycle mutations and timestamps |
| `src/game/settings.ts` | Real provider/profile/preference persistence and truthful capability tests |
| `src/game/studio.ts` | Durable partial drafts and typed content; proposals and samples via backend, not canned text |
| `src/game/images.ts` | Scoped immutable asset references and authorized retrieval; no global character-name slots |
| `CharacterPreviewPanel.vue` | Separate actual profile/body images; take typed subject/draft/job state instead of owning route-based fixture access |
| `NewStoryView.vue` | All six real steps; Save draft persists; Continue no longer routes into an unwritten placeholder |
| `SettingsView.vue` | Remove timers that manufacture successful tests; connect existing forms to actual results |
| `StubView.vue` links | Implement required destinations or remove/disable unsupported actions with an explanation |

Keep familiar component markup/classes while introducing typed props, emitted events and small data composables. A presentation component should not mutate canonical global fixtures. Generate TypeScript API types from backend contracts. Avoid duplicating domain schemas in handwritten frontend models; display-only view models are fine.

Existing sample data may remain under an explicit development/demo configuration. Production starts with real installation-owned presets and zero fabricated stories. A Demo mode must be labeled and must never show “live provider verified.”

The donor includes mockup crops among its image placeholders. Audit and replace art containing buttons, labels or other baked UI with clean existing assets or neutral fallbacks. This is a targeted asset fix, not permission to redesign the page. Keep all character cards equal-sized within the same grid/breakpoint. Do not copy extra donor lore into canonical seed data accidentally.

## 5. Backend strategy: reuse without bringing back the frontend problem

Use Python with FastAPI, Pydantic, SQLAlchemy, Alembic and PostgreSQL. This matches the existing world engine and avoids reimplementing complex simulation mechanisms in browser code. Use a filesystem storage adapter initially, with a port that can later target object storage. Long jobs run in a durable worker; the first version can use Postgres job claiming without introducing Redis/Celery.

**Preferred starting strategy:** assess and vendor PixelSaga's backend as one coherent subsystem into Ember Vale, preserving the dependencies and migrations it actually needs. Adapt its API projections to Ember Vale. Do not scatter isolated engine files into a new package while losing their transactional/repository dependencies.

A timeboxed feasibility packet must prove: backend starts against a separate empty development database; migrations run; a preset-backed story can be created; one deterministic turn commits; Ember Vale can list and resume it. Record source provenance and any concrete blockers. Do not import PixelSaga frontend assets/configuration merely because its Dockerfile expects them; adapt the deployment paths.

If a backend subsystem has a concrete integration blocker, document it and implement/replace that bounded subsystem with the same acceptance behavior. Do not begin a parallel second engine by default. Choose one canonical persistence/turn architecture before continuing. Reuse is not proof of correctness: the inspected code/handoffs disclose missing travel setup, preset projection gaps and absent configured live image generation.

Suggested repository additions:

```text
backend/                 API, domain, application services, adapters, worker
backend/migrations/      additive schema migrations
content/                 starter definitions, versioned prompts/style packs
contracts/               generated API artifacts if not using imported location
src/api/                 frontend API client and generated types
src/composables/         request, draft, story, job and asset state
docs/                    setup, architecture decisions, delivery evidence
compose.yaml             database, API, worker, existing frontend/proxy
```

Reuse the imported backend's internal package name if changing it adds no product value. Keep Ember Vale's root frontend package in place. Document exact commands/ports after implementation, not guessed instructions. Use a distinct database/volume from the old PixelSaga installation. Migration of old stories is optional later work with backup and validation; never connect the new project to an old production database as a shortcut.

Layer boundaries remain simple: domain rules/contracts; application commands/queries/orchestration; infrastructure database/storage/provider adapters; HTTP/worker entrypoints. If imported code uses repository Protocols and a UoW, preserve their wiring. Do not keep both a new and imported competing version store. Retain row/version consistency and event constraints wherever imported engine operations rely on them.

## 6. Canonical data model

The table defines logical responsibilities, not a demand to create a table for every row. Reuse equivalent imported records and document the mapping. Use UUIDs for runtime identities, scoped stable keys for reusable location definitions, timestamps for wall time and an independent in-world clock.

| Entity | Required meaning |
|---|---|
| Preset / immutable revision | Reusable world, character, style or story template; editable metadata plus versioned payload |
| Editor draft | Partial world/character content, base revision, selected assets, optimistic version and optional wizard return context |
| Story draft | Selected exact preset revisions, cast instance keys, mode/controlled character, rules, AI/art settings, current step |
| Story catalog | Title, lifecycle status, last-played time and display summary; points to one isolated world state |
| Initial setup | Immutable resolved configuration copied at story creation, including provenance and exact revisions |
| World and locations | Clock, conditions, accepted lore, stable runtime locations and traversable connections |
| Character identity | Stable appearance/personality/voice/background; not overwritten by rendered images |
| Character state | Location, life status, resources, active activity, goals and version |
| Item definition/instance | Definition metadata; actual quantity/owner; equipment and visible-carried associations to owned instances |
| Physical appearance state | Physique, visible injuries/conditions and outfit state with evidence and version |
| Relationships | Directional links and permitted dimensions; A trusting B does not imply B trusting A |
| Knowledge/memory | What each character has learned/observed, private thoughts, evidence/source and scope |
| Turn/scene/action | Durable lifecycle for a simulation beat, proposed intents, reactions and resolved outcomes |
| World event | Ordered, attributable committed change, caused by a command/action/intervention |
| Narrative segment | Narration/dialogue/action text grounded in committed events, speaker IDs and visibility |
| Intervention / steps | Parsed proposal or force command, targets/timing, clarification, queued/applying/applied/failed/cancelled state |
| Asset/image job | Binary storage reference, immutable metadata/lineage, durable generation lifecycle and selected-asset association |
| Provider/profile revision | Configured adapter, credential reference, model/sampling/capabilities and pinned non-secret revision |
| Checkpoint | Consistent, versioned recoverable story snapshot and event cursor, when implemented |

Every runtime read/write is scoped to the intended story and authorized subject. Client-provided IDs must be checked against that scope. Entity versions detect conflicting edits; idempotency keys prevent duplicate commands. Reject reuse of one key with a different payload. Stable ordering, correlation IDs and schema versions make history inspectable.

Preset revision, schema version, entity version, visual-input version and asset version are different concepts. Do not collapse them into one integer. Existing revisions and setup snapshots are immutable. New Library edits affect future selections, not existing stories. At story creation, resolve all selected content and copy the accepted initial state atomically.

## 7. Library and creation content

### World creation

Use the existing studio style with four functional steps: Concept; Places & appearance; Rules & knowledge; Review.

Collect a name, concept, tone/genre, scale, everyday life/tension, magic/technology descriptions, and visual geography/architecture/materials/vegetation/landmarks/exclusions. Locations have stable keys, names, purposes, narrative/visual descriptions and explicit connected keys. Require one valid starting place. Renaming never silently changes a key. Deleting a connected/start location requires fixing references.

Distinguish descriptive world laws from implemented game mechanics. Facts have public, limited-known or hidden scopes. Limited-known bindings in a preset resolve to actual cast instances at story creation; unresolved private facts must not default to public. A generated map cannot add canonical towns or routes just because they appear in the pixels.

### Character creation

Steps: Identity & appearance; Personality & voice; Background & connections; Review. Collect name/pronouns/age/species/role, accepted visible traits and initial outfit; motivations/fears/boundaries/pressure response/contradictions; speaking style and example dialogue; background, skills, memories, secrets and directional relationship bindings.

Use concrete questions, optional advanced sections and bounded fields. A character's private fear is not automatically visible appearance or universal knowledge. Relationship bindings reference cast instance keys on instantiation, not only preset IDs, allowing the same preset to be reused without identity confusion. Initial equipment references known definitions or clearly cosmetic clothing; descriptions alone do not award mechanical items.

Suggestions return typed proposals; the user accepts/rejects them. They never overwrite manual content on completion. Voice/behavior/environment previews are explicitly hypothetical and do not advance the story, create events or change relationships. Record which input version a preview used. Save draft permits incomplete fields; publish validates complete content. Background/text limits must match UI, transport, persistence and runtime consumers without silent truncation.

### New Story

Preserve the six-step visual pattern and implement World → Cast → Mode → Story → AI → Review. Select/create characters before choosing a Player-controlled character. Quick Start explicitly prefills the starter selection; normal New Story starts at World. Save before opening a nested preset editor and return to the same persisted draft/step. Preserve exact preset revisions and cast instance keys across reload.

Create story is one idempotent transaction: resolve/validate presets; allocate world/locations/cast; create routes/starting items/knowledge/relations; bind mode; store initial setup/catalog and creation receipt. A failed creation leaves no partial playable story. Image jobs are recoverable after-commit work, not part of a long database transaction. A fresh story can run with curated/neutral art.

## 8. Simulation and LLM responsibilities

A beat is a durable unit of progress, not one streamed paragraph. The database is authoritative. LLM output is proposed structured content until validated. Model prose must not directly mutate location, inventory, health or world conditions.

### Turn sequence

1. Authorize the request, validate world status and acquire single-writer admission for this story. Return an existing result for a repeated idempotency key.
2. Seal a versioned snapshot of the relevant state and resolve the story's provider/profile revisions. Select eligible queued interventions.
3. Apply due validated conditions/schedules under deterministic rules and assemble permitted contexts.
4. Obtain intents: supplied Player attempt, autonomous character decisions, and supported director proposals. Group interactions by compatible location/participants. Reactions see only available observations.
5. Validate actions: actor alive/capable, targets exist, route/item ownership/range/resources valid. Resolve supported actions through deterministic rules, bounded randomness or a validated structured resolver result.
6. Commit accepted effects and ordered events transactionally, using expected versions. Publish outbox/task records for downstream narration, perception, memory and images. No provider network call while holding this transaction open.
7. Produce narration and attributed dialogue grounded in committed outcomes. Publish presentation updates and mark the beat completed once required durable work reaches its defined boundary.

When using PixelSaga's engine, map these responsibilities onto its existing phases rather than layering a second turn runner around it. Preserve its durable phase/task lifecycle and idempotent recovery. Revalidate before commit if state changed since the snapshot.

Persist randomness outcomes/seed and accepted model outputs when needed to reproduce a committed result. Replay must not ask the model to invent a different history. If narration fails after effect commit, retry narration only and show the committed event summary; do not reroll actions. If resolution fails before commit, keep the last consistent state and expose a retryable/failed beat. Never advance twice because a browser disconnected.

### Initial mechanics

Implement a bounded D&D-inspired ruleset: movement, observation/search, dialogue/social attempts, rest, basic interaction, item use/transfer/equip, training/work, and a minimal coherent combat resolution with resources and success/partial/failure outcomes. Use deterministic validation and recorded checks. Do not claim complete D&D edition compatibility or allow unsupported spells/items because the LLM mentioned them.

Maintain a supported-action registry/schema. Unknown free-text actions can be clarified or mapped to a supported attempt; never execute arbitrary Python/SQL/tool names returned by a model. Proposed items/characters/world facts need explicit validated creation paths. The LLM can describe flavor without adding mechanical rewards or objects.

### Personality, memory and knowledge

Character prompts receive identity/voice, current state, relevant public surroundings, goals, known relationships and owner-permitted observations/memories. An omniscient user view is not the same as an omniscient NPC prompt. A private secret remains private until an event communicates it.

Separate world facts, character beliefs and rumors. Keep source IDs and visibility with retrieved context. Begin with bounded chronological/relevance selection and summaries; add embeddings only if needed or already required by reused code. Do not turn summaries into a mechanism for forgetting authoritative inventory/location facts or exposing another character's private memory. Version prompts and record context selection/provenance for debugging with bounded retention and secret redaction.

Dialogue uses stable speaker IDs, preserves individual voice and follows resolved interactions. Narrative blocks should distinguish narration, dialogue and action. Scene/event text should not consist only of debug fields such as `action_resolved`.

## 9. Player, Observatory and detail views

The existing application pages stay intact while these gameplay destinations are added in the same style. Preserve separate application navigation and story navigation.

### Player / Adventure

Show the current environment, readable narration/dialogue, suggested choices and a free-text attempt field. Display the controlled character and relevant resources/inventory. Suggestions are grounded in available routes, participants and supported actions. Only submit for the bound character; the server filters hidden information before returning it. Changing Player mode is not achieved by changing a query parameter.

### World Observatory

Map occupies about 65–75% of desktop content, adjustable within the original 50–80% preference. A right event/history feed uses the remainder. The top toolbar has Step, Play/Pause and speed controls plus in-world time. A bottom director composer is available according to capability. On mobile use Map/Events panels instead of compressing both into unreadable columns.

Character tokens have consistent portrait dimensions. Actions such as speaking, fighting, resting, eating and idle use brief anchored bubbles/icons. Their positions and states come from world projections, not model-generated coordinates. Resolve overlapping tokens with stacking/clustering. Events link to participants/locations and can be filtered without losing chronological sequence. New feed items should not drag a user away while reading older entries.

Autoplay is server-authoritative, one admitted beat at a time. Speeds initially mean a shorter delay between completed beats, never parallel unresolved turns. Persist pause/play state and stop at configured errors, decisions, budgets or end conditions. Default v1 to pause when the last observing session leaves/disconnects after a grace period; implement this server-side if promised. Unattended background simulation requires a later explicit setting, not accidental behavior. Manual stepping and multiple browser tabs cannot bypass the same writer gate. Pausing prevents new admission and allows the current accepted beat to finish consistently.

### Event focus modal

Clicking a feed event/character interaction opens a modal roughly 80% of the viewport. Left ~70% of the modal shows the event illustration; right ~30% holds a modest title and scrollable storytelling/dialogue. Character dialogue has a small icon beside it. Remove separate Participants and What changed blocks from the main reading area, per user preference. The observatory map remains behind the modal, not a duplicate scene image. On narrow screens stack image and text. Preserve keyboard focus/close behavior.

Event art uses event-time location, participants, action, environment and appearance references. Do not illustrate an old event with today's changed gear unless clearly labeled. Opening the modal does not trigger unlimited paid generation; use an explicit request/default policy with deduplication and budget controls. Missing art shows a suitable existing background with an honest label or a placeholder, while text remains readable.

### Character and location details

Live character details show full-body image plus profile, current activity/goal, equipped/carried items, physical state, relationships and recent changes. Include Follow on map and View original preset. A stale image remains visible with Refresh appearance. Library character details describe the reusable initial template; runtime changes do not edit that template.

Location details show artwork, description, current occupants, recent events and valid connections. World preset details show accepted geography, places, tone/rules and starting cast, with Use in new story/Edit/Duplicate. These can use a drawer or full page consistent with existing components; no generic admin replacement.

## 10. Director and God interventions

Examples the system must support through typed actions:

- “Start a fight between Wren and Ash.”
- “The world is enduring an unknown devastating plague.”
- “Ash should go to the Market.”

Interpretation returns structured targets, intended effects, timing/steps, required capability and ambiguities. Match actual IDs; duplicate names and nonexistent places require clarification. Show a concise interpretation and queue receipt. Routine supported commands can enqueue directly under the chosen policy; world-wide force operations should expose their consequences before commitment.

Director proposes an incident/goal/plan subject to normal feasibility and character behavior. God explicitly forces supported overrides. For example, a Director request for combat can create a confrontation opportunity; it does not secretly bypass the permissions for forced harm. A plague becomes a persistent typed world condition with duration/scope/tick rules when accepted, not a one-paragraph narration that vanishes next turn. Travel validates an actual route and can create a multi-beat activity rather than teleporting by default.

Queue records capture original text, normalized proposal, interpretation version, actor/capability, affected story/entities, expected state and step keys. States cover clarification, queued, applying, applied, failed and cancelled. Revalidate on execution. Cancelling queued work prevents future effects; cancelling after partial application cannot erase committed events. Report partial completion honestly and avoid applying a step twice after a crash.

Instructions/prompts are untrusted content. They do not authorize filesystem/network access, secret disclosure or arbitrary code execution. The planner emits only allowlisted domain commands.

## 11. Image generation and evolving appearances

### Required asset types

World map master/display derivative, location backgrounds, square profiles, portrait full-body art, event illustrations and optional story covers. Smooth nonpixel anime style, versioned style packs, no baked interface text/routes/counts/watermarks. Existing clean starter art is valid fallback content. Map anchors and connections are versioned data separate from raster art.

### Profile first, full body second

1. Resolve accepted identity and style inputs; generate or upload/select a square profile.
2. User approves the profile, making an immutable identity reference.
3. Generate full-body portrait using the actual approved image through the provider's reference/edit interface, plus accepted physique/outfit/visible gear/physical conditions.
4. Store body lineage, input snapshot/hash, provider/model/prompt/style revisions and reference asset versions.
5. User selects the candidate. Selection changes artwork, not inventory, injuries or identity facts.

A text-only image endpoint cannot be presented as reference-conditioned generation. Probe capabilities honestly. Keep profile and body visible in the preview; body shows head to boots. Do not stretch a face portrait into the body panel. Generated anatomy/clothing errors remain visual errors, not canonical events.

### Dynamic state

Separate identity, initial preset appearance and story-owned current appearance. Owned inventory is not necessarily visible or equipped. Equip slots link valid owned instances; moving a worn item clears the association atomically. Cosmetic starting clothing is distinct from mechanical items. Visible injuries have region/side, active/resolved state and provenance. Physique updates require supported canonical evidence or an explicit authorized change; strength/skill points do not automatically mean muscle growth.

A cloak change, visible bandage or accepted physique update marks the body render outdated while retaining the face. Hidden backpack contents and unrelated personality edits do not invalidate it. A replaced profile invalidates dependent bodies. Default to explicit Refresh after state changes; any later auto-refresh requires debounce, coalescing and spend caps.

### Durable job rules

Persist jobs with non-null scope identity, subject, kind, input snapshot/hash, reference dependencies, generation intent/idempotency key, attempts, lease/status and result. A retry reuses an intent; Regenerate creates a new candidate. Workers perform external calls outside transactions. Bounded retries/timeouts and crash recovery cannot create unlimited paid requests. Unknown provider outcomes are reported, not silently retried forever.

On completion, validate MIME, dimensions/pixel count, size and current association before promoting. If the user switched Wren→Ash, or the body inputs changed, retain the result as a historical candidate instead of attaching it to the wrong subject/current version. Keep the last good image while updating. Candidate acceptance is version-checked. “Generated from current inputs” describes hash freshness; it does not guarantee the image is visually correct.

Store binaries outside rows behind immutable storage keys. Authenticated byte retrieval plus Blob/object URLs avoids API keys in URLs. Validate uploads as raster; reject executable SVG/HTML and arbitrary user-supplied remote URLs. Cache by asset/version with scope-aware authorization and URL cleanup. Garbage collection respects references from preset revisions, historical events, stories and pending jobs.

## 12. Providers, Settings and cost controls

Keep the existing Settings UI and implement all its sections: AI connections, generation defaults, appearance/accessibility, storage/saves and advanced. Multiple provider connections/profile revisions are permitted; a story pins chosen non-secret revisions. Application preferences such as text size differ from story-bound model/rule settings. Existing stories do not silently change because a default was edited.

Use a provider-neutral text gateway supporting structured output and a separate image gateway with capability discovery/declared tested support. Start with one genuinely implemented text adapter, preferably the user's OpenAI-compatible local service or an existing working imported adapter. Add image integration for the actual configured provider. Do not advertise every provider name in the demo dropdown as implemented.

Validate supported temperature/top_p/top_k/token-limit options per adapter; do not send unsupported fields or equate unspecified with zero. Separate endpoint reachability, authentication, supported model and successful generation. Results refer to the exact tested configuration revision. If tests target saved connections, label that truthfully; an unsaved form test needs a deliberate backend contract. Remove all fake success timers.

Credentials stay server-side as environment/secret references. Browser input should not become a long-lived raw credential in persisted story config, exports, traces or frontend bundle. Distinguish application access authentication from model-provider credentials. A single local/self-hosted operator is sufficient; Profile is not a fictional authenticated account system.

Apply request timeouts, retry/backoff, per-story maximum concurrent work, output/context budgets and optional spend caps. A small local model must be able to use reduced context and fewer active decisions without breaking canon. No one-call-per-character-every-second architecture. Track tokens/latency/cost when reported and mark unknown estimates honestly. Real-generation tests are explicit because they can cost money.

## 13. API and route contract

Maintain one versioned API, preferably `/api/v1`, under a same-origin production proxy and Vite development proxy. Generate OpenAPI/types. Reuse imported endpoints where their semantics fit; do not build two parallel public APIs without a compatibility purpose.

The following are logical API groups, with proposed paths where new work is needed. Freeze an exact route/DTO map during the first integration packet; frontend strings must follow that generated contract.

| Group | Operations required |
|---|---|
| Library | List/read presets by kind, read exact revision, create/publish revision, duplicate/archive, validate import/export |
| Editor drafts | Create/read/update/discard/publish partial world or character draft, optimistic version and return context |
| Story drafts | Create/read/update and atomic idempotent story creation |
| Stories | Paginated summaries, detail, original setup, rename/archive/unarchive, open/resume, optional later checkpoints |
| Gameplay | Role-filtered presentation, ordered chronicle/event detail, character/location details, own-player attempt |
| Simulation | Status, step, play/pause, pacing; durable beat/job status |
| Interventions | Interpret/clarify/queue, list/read, cancel and status |
| Generation | Suggest/sample requests, image job request/status/candidate selection, authorized asset bytes |
| Settings | Preferences, provider/profile revisions, capabilities, bounded tests, safe cache scopes |
| Operations | Health/readiness, diagnostics and sanitized job failures |

Mutations use expected entity/draft versions and idempotency where duplicate effects matter. Return stable error codes with field errors/retryability: validation, unauthorized/forbidden, not found, version conflict, unavailable capability, provider timeout and failed job. Never show success before server acknowledgement. Use pagination and bounded summary projections rather than one complete world fetch per card.

Start with status polling for active work and incremental chronicle cursors if that simplifies the integration; SSE is an optional transport upgrade. UI refresh must recover missed events by sequence cursor. Streaming prose is provisional until committed; it cannot move map tokens or grant equipment. Cross-route responses are ignored after their subject/session changes.

### Frontend routes

Retain `/`, `/new-story`, `/library?tab=...`, `/stories`, `/settings` and existing studio entry paths. Preserve the user's current route vocabulary rather than importing PixelSaga's application URLs. Extend New Story with persisted `draft` and `step` query parameters. Studio origin must carry a typed, validated return context, not an arbitrary external URL.

Add `/stories/:storyId/play` as a role-aware entry, `/stories/:storyId/adventure`, `/stories/:storyId/world`, and detail destinations/drawers as needed. A server-provided effective mode determines allowed entry. Keep Help/Profile accessible. Browser reload/back/forward should restore route state. Character/world editor steps must be real panels with validation, not a cosmetic numbered stepper.

Rich card data such as recap, cover, cast portraits, place/usage counts and timestamps must come from real projections or be omitted/unknown. Use selected immutable asset references. Do not ask an LLM to generate every card description on a list request. Sort before server pagination.

## 14. Saves, history and long-lived worlds

**Story** is a persistent campaign. **Preset** is a reusable starting template. **Setup export** is configuration. **Checkpoint/save** is recoverable state. Keep these separate in product copy and code.

For the initial release, every committed beat is durable and Continue loads its latest consistent state. Display saving/failed status honestly. Archive stops new work and retains history; rename does not change identity. Original configuration remains available through the Stories information action. A database backup includes associated asset storage and must be restore-tested before being described as a complete backup.

Checkpoints/branches are a later explicit packet, not links to a placeholder. Capture at a safe beat boundary, including relevant canonical state, clock, RNG/outcomes as needed, knowledge/memories, relationships, queued schedules/interventions, selected assets and event cursor/schema version. Reuse imported snapshot support only after it is proven sufficient for restore; a trace snapshot may not be a save.

Prefer Branch from checkpoint initially, preserving the source story. Allocate new scoped identities and remap all references. Pending external jobs must not be duplicated or incorrectly rebound; branch state needs a clear queue/job policy. If rewind is later supported, explain the affected history and validate consistency before committing. Do not regenerate historical LLM responses to pretend a restore succeeded.

Long-term world simulation can compress quiet spans into days/weeks/months/years with deterministic rules and summaries. Stop compression at meaningful events/conditions requiring detailed resolution. If a system cannot model an active plague or travel consistently during a macro period, block that operation rather than skipping it. Later add age/lineage/focus succession, era digests and explicit end conditions such as sustained peace or maximum day. These complete the long-lived-world vision but must not delay the first working story loop.

## 15. Reliability, deployment and safety boundaries

Run API and worker separately against one Postgres database and shared configured asset storage. Use durable leases/outbox or imported equivalents. Exactly one canonical writer may advance a story; independent stories can progress concurrently within global provider limits. Worker restarts and duplicate delivery must not duplicate committed effects.

Supply environment example without secrets, migrations, compose/development commands, health/readiness and a small starter initialization command. Bootstrap presets idempotently; do not seed a played story merely by visiting Home. Configure timezone/in-world time deliberately. Use same-origin `/api` routing, appropriate CORS in development and SPA fallback for frontend deep links.

Local loopback development can use a documented development access mode. Network-accessible deployment requires authentication and explicit configuration. This is not a mandate to build SaaS accounts. Prevent cross-story object access, redact logs, validate uploads and bound model output. Treat all user/generated content as data; do not render arbitrary HTML or run uploaded scripts. Only approved configured endpoints are contacted; user story prompts cannot instruct the server to fetch arbitrary URLs.

Use additive migrations and a separate database for tests. Never drop the existing PixelSaga or Ember Vale user database because a verification script expects a fresh seed. Keep existing stories and media backed up before any optional import. Log sanitized correlation IDs, durations, status and retry counts. Provide enough diagnostics to distinguish provider failure, state conflict and missing configuration without exposing private prompts/secrets indiscriminately.

## 16. Execution packets and required evidence

Complete useful vertical slices. Keep the original UI running throughout. Each packet ends with a short report of actual changes, actual checks, screenshots for touched views and unresolved dependencies. Make coherent commits; do not run a broad refactor between packets without a concrete need.

| Packet | Work | Proof of completion |
|---|---|---|
| E0 Baseline | Inspect Ember Vale instructions/source, record current individual-page screenshots, inventory fake behavior/assets, pin reference backend | UI baseline and API/engine reuse decision recorded; no frontend replacement |
| E1 Backend spine | Add coherent backend, isolated DB/migrations/config, API proxy, generated client, real health and deterministic provider | Existing Home can load a real empty catalog; server restarts cleanly |
| E2 First complete journey | Persist starter presets, story draft and atomic create; connect existing Library/World/Cast/Mode/Review enough to create; minimal real play entry and step | Create → one committed turn → leave → Continue → same state after server/browser restart |
| E3 Library/studios | Durable partial drafts, immutable revisions, complete world/character steps, exact selection revisions, nested return flow | Edit revision 2, reload, select it, create independent story; original preset/story unchanged |
| E4 Settings/live text | Real connections/profile defaults, capability/credential status, supported sampling, one working text adapter | Live validated narration/character dialogue from accepted inputs; no fake reachable badge |
| E5 Player/Observer | Full adventure and observatory screens, perspective filters, activities/basic mechanics, map/chronicle/status, serialized autoplay | Player attempt and autonomous cast progress; two tabs cannot advance twice; pause and errors recover |
| E6 Director/God | Typed interpreter, clarification, queue, permissions, multi-step travel/confrontation, persistent world conditions | Travel/fight/plague examples produce auditable permitted effects; crash retry does not duplicate |
| E7 Artwork | Asset service, real image adapter where configured, approved profile→body lineage, event-time art and focus modal | Profile/body/event jobs complete and survive reload; wrong-subject/stale results cannot become current |
| E8 Living characters | Owned/equipped inventory, visible physical-state updates, relations/goals/memory details and stale-art projection | Cloak transfer/bandage/authorized physique update alter correct state and images without changing preset |
| E9 Saves and operations | Consistent checkpoints/branches if included in release, backup/restore, remaining Stories actions, export boundaries | Restart recovery plus proven backup restore; branches have isolated remapped state; no false save links |
| E10 Long-term simulation | Macro progression, interruption, era summaries/end conditions and lineage/focus support where available | Compression respects invariants and returns to detail at seeded event; documented unsupported cases |
| E11 Release hardening | Complete regression/visual/accessibility checks, deployment docs, clean asset audit and honest feature matrix | Working Ember Vale product through real backend, with live-provider evidence separate from deterministic tests |

E2 intentionally happens before all rich editor/backend features: it proves the chosen backend works through this frontend. It is not permission to leave the later requested functionality as fake buttons. E7 can develop with fixture adapters but live image acceptance remains blocked until a configured reference-capable provider is exercised.

### First end-to-end acceptance scenario

From an empty installation, load real starter presets. Create “A Morning in Ember Vale” with Wren and Ash, Hearth/Market connected, Observer mode. Advance one beat and receive a committed event plus narration. Close/reload and resume the same state. In another story choose Player/Wren, submit a supported attempt and prove Ash remains autonomous. No step uses the demo's saved flags or fabricated story shelf.

### Focused correctness checks

- Duplicate create/advance/job requests replay their result; changed payload with same key conflicts.
- Mid-turn provider failure leaves consistent state; post-commit narration retry does not repeat effects.
- Two stories sharing a preset do not share mutable character state or global image slots.
- Cross-story IDs and unauthorized Player/Observer/God operations are rejected server-side.
- Character private knowledge is excluded from other actors' context and user projections where required.
- Draft/preset conflicts preserve user edits; revision selection survives reload; images are optional for publishing.
- Travel requires connected locations; nonexistent targets do not become invented canon.
- Equip/transfer ownership remains consistent; an image cannot grant a sword or heal a wound.
- Old event images use event-time state; late image completion cannot overwrite another subject/current input version.
- Settings failures remain failures; unsupported parameters are not sent; provider tests identify the tested configuration.
- Story archive stops new admissions; in-flight work follows an explicit consistent boundary.
- Asset cache cleanup does not delete selected/historical assets; configuration export is not mislabeled a full save.

### Visual and operational checks

Run existing Ember Vale typecheck/lint/tests/build and relevant backend contract/lint/type/test checks. Use deterministic fixture contexts for automated screenshots, not random live imagery. Capture individual pages at recorded CSS viewports: 1440×900, 1920×1080 and a narrow mobile size, plus 200% zoom for key forms. Do not scale a fixed large canvas to fake responsiveness. Compare against E0 so backend integration does not change cards, fonts, spacing or artwork placement accidentally.

Verify equal cards, readable text, head-to-boots body art, no UI fragments in images, keyboard tabs/menus, modal focus restore, no obscured controls under Save bars and route refresh/back behavior. No repetitive loading animation is required. Preserve usable empty/error/unavailable states. Inspect logs/network for accidental generation on mount and repeated requests.

For live acceptance, record a real text interaction and profile→body image pair using actual reference input, with sanitized job/model/configuration information. This is separate from fake-provider unit tests. If credentials are absent, report the exact blocked test and complete all independent work; never call the whole pipeline live-verified.

## 17. Reference inventory and known gaps to verify

The included PNGs show the intended style for missing gameplay/details and editor previews. Existing Ember Vale pages remain the implementation baseline. Illustration sample content is not canon; screenshots are not backend specifications or image assets to crop into cards.

PixelSaga's source is useful for story transactions, immutable setup/preset revisions, capability checks, canonical effects, phase/task recovery, event chronicle, interventions, memory and settings resolution. Its published handoffs also acknowledge missing travel routes in seeded worlds, no configured live text/image provider and per-event art limitations. Source inspection additionally found revision-1 hardcoding in its frontend and rich preset fields not fully projected at instantiation. Do not inherit those assumptions into the new frontend/backend contract.

### Pinned sources

- [Ember Vale README and demo architecture](https://github.com/joelhenwang/ember-vale/blob/ab9161c59edc112b12db7b3081b9717a85a98c90/README.md)
- [Ember Vale router](https://github.com/joelhenwang/ember-vale/blob/ab9161c59edc112b12db7b3081b9717a85a98c90/src/router.ts)
- [In-memory studio behavior](https://github.com/joelhenwang/ember-vale/blob/ab9161c59edc112b12db7b3081b9717a85a98c90/src/game/studio.ts)
- [Demonstration settings behavior](https://github.com/joelhenwang/ember-vale/blob/ab9161c59edc112b12db7b3081b9717a85a98c90/src/game/settings.ts)
- [Character preview component](https://github.com/joelhenwang/ember-vale/blob/ab9161c59edc112b12db7b3081b9717a85a98c90/src/components/studio/CharacterPreviewPanel.vue)
- [PixelSaga engine overview](https://github.com/joelhenwang/pixelsaga/blob/785713dcf6fd4c071b04944469c5cbbb56a628bc/README.md)
- [Backend dependencies](https://github.com/joelhenwang/pixelsaga/blob/785713dcf6fd4c071b04944469c5cbbb56a628bc/backend/pyproject.toml)
- [Gameplay/backend handoff and known limitations](https://github.com/joelhenwang/pixelsaga/blob/785713dcf6fd4c071b04944469c5cbbb56a628bc/docs/pixelsaga-revamp/HANDOFF.md)
- [Story catalog/setup/provider handoff](https://github.com/joelhenwang/pixelsaga/blob/785713dcf6fd4c071b04944469c5cbbb56a628bc/docs/pixelsaga-mainmenu/HANDOFF.md)
- [Existing capability policy](https://github.com/joelhenwang/pixelsaga/blob/785713dcf6fd4c071b04944469c5cbbb56a628bc/backend/src/worldsim/application/capabilities.py)
- [Atomic story creation](https://github.com/joelhenwang/pixelsaga/blob/785713dcf6fd4c071b04944469c5cbbb56a628bc/backend/src/worldsim/application/stories/create.py)
- [Perspective-safe context assembly](https://github.com/joelhenwang/pixelsaga/blob/785713dcf6fd4c071b04944469c5cbbb56a628bc/backend/src/worldsim/application/context/assembler.py)

Trace dependencies in the actual backend before copying: ports/UoW, SQL mappings, migration chain, prompt/content paths, model gateways, CLI/worker startup and generated contracts. Reuse backend-only evidence and tests where meaningful. Do not import old frontend configuration or repo instructions with them.

## 18. Delivery definition

The agent must deliver a working Ember Vale application, not another frontend migration plan. Keep its existing UI recognizable and turn its controls into real persisted workflows. Supply working source/migrations/contracts, honest provider states, API/worker setup instructions, tests, per-page before/after screenshots, and an explicit feature/evidence matrix.

A user should be able to create a world and cast, start a story, play or observe it, direct supported events, inspect characters and illustrated interactions, close the browser, and return to the same evolving world. Long-term features can arrive in the documented stages, but their state must be reported accurately rather than represented by demo success.
