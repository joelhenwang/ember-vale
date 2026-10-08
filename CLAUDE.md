# Ember Vale: notes for Claude

Read this before you claim that something is missing, broken or new. Most "missing" features
already exist (see the inventory below, and the grep recipes at the end). Run `git log`. The
commit messages are long and accurate, and they are the best history of this project.

## 1. What this is, and who you work for

Ember Vale is a persistent, illustrated fantasy storytelling RPG and world simulator. You make
or choose a world and a cast in the Library, start a story as a **Player** (you control one
character) or a **Watcher** (Observer, Director or God seat), and the world advances in
**beats** (players see the word "turns"). In each beat every character decides, reacts and
acts. Validated backend commands own canon, LLMs only propose JSON, and a narrator writes
prose grounded in committed events. An image service paints portraits, places, maps and key
moments.

The user (Joel, joelhenwang on GitHub) owns the project. Since 2026-10-04 Claude has had full
autonomy over it. The user gives short directives ("All sound good", a UI review list) and
reviews the results: screenshots, evidence folders and spend reports. Make the routine
decisions yourself. Ask only about money beyond small live runs, about destructive data
operations, and about real product direction.

## 2. Repo map

| Path | What lives there |
|---|---|
| `backend/src/worldsim/domain/` | Pure models and rules (`rules/`: actions, routes, meetups, mentions, repeats, scenes, validation, `dnd/`). Also `geography.py` (map maths, road stamina, terrain weighting, `spot_named`), `pictures.py`, `journey.py` (renown), `carried.py` |
| `backend/src/worldsim/application/` | Commands, queries and orchestration. `orchestration/stage1.py` is the beat engine (~4k lines). `orchestration/background.py` holds BackgroundNarration and `framing.py` holds FramedGateway. `graphs/` holds the LLM role graphs (character, reaction, resolve, narrate, director, summary, lenient). `queries/presentation.py` is the player and watcher view. `pictures.py`, `editor_drafts.py`, `library/` (builtins, preset_create, writing) and `stories/create.py` are also here |
| `backend/src/worldsim/infrastructure/` | `settings.py` (every `WORLDSIM_*` env var), `model_gateway/` (openrouter, venice, hedge, selection), `images/` (krea, runner, shrink), `geography/openrouter.py` (map reader with PLACES/ROADS/SPOTS/TERRAIN/FACE prompts), `local_models/` (RecallIndexer, MentionReader), `writing/`, `db/`, `repositories/` |
| `backend/src/worldsim/interfaces/http/` | `app.py` (all routers under `/api/v1`), `routes/*.py`, `schemas.py` (API DTOs), `beats.py` (`run_beat`, shared by advance and autoplay), `state.py` (AppState wiring), `export.py` (OpenAPI export) |
| `backend/prompts/` | Versioned role prompts. Active versions: `character_decision.v7`, `reaction.v4`, `resolver.v4`, `narrator.v4`, `director.v12`, `summary.v2`, `digest.v2` (constants in `application/graphs/*.py`) |
| `backend/migrations/versions/` | Alembic `0001`–`0057` committed. The API container's entrypoint migrates on start |
| `backend/scripts/` | `scorecard.py` (live story-quality scorecard), `play_session.py`, `narrator_prompt_eval.py`, `map_detect_eval.py`, `map_routes_eval.py`, `terrain_eval.py`, `place_spots_eval.py`, `recall_eval.py`, `routing_eval.py`, `prefix_eval.py`, `frame_painted_faces.py`, `gen_ts_client.py` |
| `backend/tests/` | pytest. Parallel-safe: each DB test clones a migrated template |
| `src/views/` | One file per page (see the routes in §3.12) |
| `src/components/` | `observatory/` (WorldMap, PlaceMap, EventFeed, EventModal), `story/` (PaintSceneDialog, BeatEntry), `studio/`, `library/`, `settings/` (ImageSettingsPanel), `ui/` (PictureFramer, FramedImage, CardMenu, SaveBar…), `decor/` |
| `src/game/` | Vue-free logic plus specs: `adventure.ts`, `observatory.ts`, `worldMap.ts`, `terrain.ts` (mirrors the server's terrain weighting), `placeMap.ts`, `parchment.ts`, `characterForm.ts`/`worldForm.ts` (studio field specs), `playerSpeech.ts`, `storyRoute.ts`, `quickHero.ts`, `records.ts` |
| `src/composables/` | `useAdventure`, `useObservatory`, `useStory` (story room), `useStoryDraft`, `useEditorDraft`, `usePresets` (module-level cached shelf), `useInterventions`, `useProviderSettings`, `useImageSettings` |
| `src/api/` | `worldsim.ts` (typed calls over the generated client), `http.ts`, `client.ts` |
| `content/` | `schemas/openapi.json` and `schemas/domain-schema.json` (generated), `clients/worldsim.ts` (generated), `visual-styles/` (anime-saga-v1, pixel-saga-v1), `dnd/`, `seeds/`, `assets/generated/` (gitignored; a compose volume in Docker) |
| `local-models/` | Optional native-Windows FastAPI service on port 8110: embeddinggemma-300m (OpenVINO int8) `/embed` and GLiNER2.5 `/extract` |
| `launcher/` | Rust ratatui TUI launcher. `Start Ember Vale.cmd` / `start-ember-vale.sh` download the released binaries |
| `scripts/` | Older Node harnesses (`journey.mjs`, `walkthrough.mjs`, `beat-latency.mjs`, `reliability-baseline.mjs`, recovery harness) |
| `docs/evidence/NNN/` | Measurements and decisions, one numbered folder each (§4) |
| `docs/handoff/` | Original product plan (`Ember_Vale_Product_and_Backend_Plan.md`, Sept 2026) and `START_HERE.md`. This is history, not the current state |
| `evidence/` (root) | Simulation gate bundles that the tests regenerate only with `WORLDSIM_WRITE_EVIDENCE=1` |

The backend was vendored from `joelhenwang/pixelsaga` (see `backend/README.md`). The internal
package name `worldsim` stays.

## 3. Feature inventory (what exists)

The commit hash after each item is the commit that introduced it. Later commits refine many
of these features.

### 3.1 Beat engine (Stage 1)
- **Beat = `POST /stage1/advance`** (`orchestration/stage1.py`, `interfaces/http/beats.run_beat`). Steps: seal a snapshot, drain the queue, run the director (every 3rd beat), collect decisions, assemble scenes, run reactions, resolve, commit, then narrate. The old stage-0 advance (`/world/phases/advance`, CLI advance) was **retired** in ed74b59. `/world/seed` and the read routes stay for tests.
- Phase timings in the `X-Worldsim-Phase-Timings` header (374afed, 2391f8e).
- Overlapping work: the director runs alongside decisions, scenes prepare in parallel, and reactions per (attempt, reactor) run in parallel. Commits stay in order, and a scene with a version conflict is redone (1caa5e7). Scene narration runs side by side after commits (4de0533). Party (D&D) worlds still narrate scenes one by one.
- **Background narration**: with `WORLDSIM_APP__BACKGROUND_NARRATION=true` (on in the dev `.env`, off by default) a beat returns once its scenes commit, and the next beat first settles any pending narration (b3130e6). Day-end summaries also run in parallel and in the background (f6ba34d).
- Quiet beats (everyone waits or rests) are flagged idle. Autoplay fast-forwards past them and the feed folds them (dc320e0).
- Model hedging: a twin request after a per-role delay (character/reaction 4 s, director 5 s, resolver/narrator 7 s, summary 10 s), first answer wins (97f1567, 31aceea; `infrastructure/model_gateway/hedge.py`).
- Lenient parsing: extra-key-only schema errors skip the repair call, tagged/nested director shapes unwrap, one ```json fence is stripped at the gateway (e95577a, fea1d0a, ef4dfff, 0538128; `graphs/lenient.py`).
- Per-role token floors through `role_max_tokens` (192dd44). The narrator cap is 1536 (f13d341).
- Per-role models: `WORLDSIM_PROVIDER__ROLE_MODELS__<ROLE>` (db1a229). Per-role reasoning: `ROLE_REASONING__<ROLE>` (2391f8e).

### 3.2 Characters' minds
- Decisions see who is present, with ids (527d720), "You are at X, from here you can travel to…" (84ad4d0), remembered replies and time labels, plus one current **intention** (migration 0042, 0b061b0).
- Actions: move (the server fills `route_id`, ccf4fe7), communicate, observe, wait, rest, take/transfer (66f08a5), **interact** = a free-text physical attempt that the resolver judges success/partial/failure (7c81df3), spar (only between characters with party sheets, 48af139).
- Meet-up rule: crossing moves become one move plus a wait (fa1c687, `rules/meetups.py`).
- Anti-idle: a streak note when a character's last 3 turns were all talk or all waiting (7f916bc).
- **Repeat guard** (`domain/rules/repeats.py`): shows up to 3 answered exchanges, and a repeated question gets ONE retry (word overlap ≥0.6 or local cosine ≥0.85) (729a04a). Reactions are not guarded yet.
- **Recall by relevance** with local embeddings (`_recall_by_relevance` in stage1.py, `recall_vector` table, migration 0048, 09a66c2). It falls back to recency and salience when the service is off.
- Context budgets for decisions: observations 6000, memories/lore 3000, goals 2500 chars (00418d8).
- Pronouns on cards, presets and NPCs (migration 0044, 1676706). Prompts and the narrator use them.
- Journeys: a move along a road longer than 1 phase starts a TRAVEL activity. The traveller pays stamina on departure and is absent from decide/react/perceive until arrival, and arrival writes a chronicle entry "X arrives at Y." (8184722, `split_journeys`).

### 3.3 Resolver, items, loot
- The resolver reads names and content, not ids (7c81df3). It sees what is at hand at each actor's place plus open rumours (3c5eea3). It knows where the actor stands, so an attempt on something absent is at most partial (b00ac60).
- Items lie at places and can be taken or given (migration 0043, 66f08a5). `item_found` loot appears at most once per scene on success (c62bff0, migration 0047), and duplicates of held items are dropped (f79df02).
- Invented moves are dropped before validation (76953cd, a9ce935).
- Studio "Carries:" becomes held items at story start (`domain/carried.py`, 9145dd7).

### 3.4 Director
- Hooks/rumours with spawn_npc (d9ae713), place_item (66f08a5) and new_location (0112d48), each limited to 3 per story.
- Unmapped places named in talk reach the director (d9b2423, `rules/mentions.py`), plus a ready-made suggestion and one repair to add the place (d9b7434, f795356, 057a689). GLiNER spans replace the noun list when local-models runs (92b2ea0, `place_mention`, migration 0049). Places mentioned ≥3 times that someone heads for open at the start of the beat (3186966).
- Rumours settle: the director lists `resolved` with an ending (12d90ba, migration 0046), and the resolver may emit `hook_settled` on a success that plainly finishes one (ff48bfc, migration 0050).
- "Story so far" (≤6 lines over the 240 events before its 8-event window) plus settled rumours (2b86914). A noop is wrong when no hook is open (director.v12, f6ba34d). One rumour per matter (director.v11, 9d8499f).
- Talk streaks and waiting chains are visible to the director (b415d35, dc320e0).

### 3.5 Narrator
- narrator.v4 (f38c28d): output shape first with placeholders, craft guidance, one listed spot per scene. The `previously` recap and `pronouns` facts arrived in v3 (883622a). Recap-only beats are dropped (b9e84e5), and sentences that retell the recap are dropped (3186966).
- Player speech: quoted communicate attempts become the player's own dialogue (`speech:<intent>` facts, 9ac44ea).
- Scene spots: the narrator gets the place's spots and "They were last at X", and chronicle entries carry `spot_key` (b364d5c).
- Deterministic fact order for reproducible prompts and caching (e4f68fc). An opt-in structured narration mode exists (world config `narration.mode = "structured"`, evidence `structured-narration-001`).
- Replay harness: `backend/scripts/narrator_prompt_eval.py --live` / `--rescore` (8544503, 11ea716).

### 3.6 Player screen: Adventure (`/stories/:id/adventure`, AdventureView.vue, aae7adc)
- A Do/Say/Wait composer. Say goes to a named recipient, always shown (a1ec3da). Your turn appears at once and answers unfold (73da284).
- Chips: go somewhere, look around, pick up, give carried items (324c622), lead chips built from the newest rumour (8469c8d, 7bc110f), rest, spar.
- Side sheet: portrait, stamina/mana, what you carry, drives, "Word around the vale", map. **Renown**: places, people, deeds and settled rumours give levels with titles from Newcomer to Legend (279aec9, `domain/journey.py`).
- The banner shows the place's own art (8c3d41d) with time-of-day light (7fcd4bc). "Still being written…" appears for pending narration, with a 1.5 s poll (b3130e6). The view catches up when its tab regains focus (34e341e).
- **Scene pictures appear under their scene, with "Paint this scene"** (PaintSceneDialog.vue). See §3.8.
- **Home** (HomeView.vue, HeroCard.vue): a banner where the world picture fades into the latest painted moment; portrait, story, "Last time" and Continue; the latest key moment (headline + caption) opens **MomentDialog.vue** (picture beside the scene's narration, spoken lines beside the speaker's face, Previous/Next through all painted moments; `src/game/moments.ts`). Continue sits under the latest key moment in the right column (236d9a9). Recent stories end with a "Start a new story" card that also holds **Quick start** and **Play as a new hero** (QuickHeroDialog). No first-visit onboarding yet (the user wants one later, not a priority).
- **Layout (after the designer's mockup, 2d97276; one card divided by hairlines since the follow-up):** left, the latest painted moment large (badge "Latest illustrated moment", place and time over it, people here as faces to talk to, expand opens MomentDialog; without a moment, the place art or the map), and under it the local map and the **current story lead** (newest rumour; the rest and settled ones fold away). Right, "The story" with the composer (Tab fills the first lead or suggestion; chips kept). Along the foot, a status bar (portrait, level and title, stamina, mana) whose **Character details** opens a drawer with the full sheet (renown counts, drives, carrying). Story pictures are thumbnails that open the moment view. Under 1100 px the story comes first and the status bar sticks to the bottom.
- The Help dialog is a how-to-play guide (9550341). Phone layout: 6b1c172, 0befcc5.

### 3.7 Watching: Observatory and story room
- **Story watch / Observatory** `/stories/:id/watch` (ObservatoryView.vue, 020a09f): map with tokens, event feed, event modal, Step/Play/Pause driving **server-side autoplay** (`application/autoplay.py`, `/stories/{id}/autoplay/*`, migration 0041, 9a22ec2). Autoplay stops after 60 s without presence. Player stories cannot autoplay.
- The map is the world's own drawn map with its roads, and travellers walk along them by the clock (b6310b7, 8184722). Places with their own map get an "Inside" chip that opens PlaceMap.vue, where people stand at their newest named spot or at a spot that suits their activity (faf9b46, b364d5c, `src/game/placeMap.ts`).
- **Story room** `/stories/:id/play` (PlayView.vue): the older form-driven room, used for the Director/God seats. It holds the **interventions** UI (typed interpret → queue → apply; `/interventions`, `useInterventions`) and the "You are on the road to X" banner for travelling players.
- Which screen a story opens on: `src/game/storyRoute.ts` (player → adventure, watcher → watch, director/deity → play).

### 3.8 Images (Krea 2 Studio)
- Image jobs: idempotent, bounded retries, versioned assets. The runner works pending jobs one at a time (`infrastructure/images/runner.py`, `krea.py`, 0c8a4d3). It stores WebP at display size and keeps curated portraits. Jobs are queued at story creation (portraits), on director spawns and places, and on key moments. **Never on read.**
- Settings > Image generation: every Krea field, live status and a "Try it" preview (`/settings/images/service`, `/settings/images/preview`; DB prefs `application_preferences.images`, migration 0051, b41ee72). The default checkpoint is `krea2Anime_v15_bf16`. Switching checkpoints costs ~35 s and affects every user of the machine, and the UI warns about this.
- **Scene pictures / key moments** (d483c4b, `scene_picture` table, migrations 0052 and 0054, `application/pictures.py`). Once a beat's narration is written (behind the turn, `Stage1Orchestrator._queue_moment`), a small writing model (`WritingSettings.model`, the library writer) reads the player's scene with `MOMENT_PROMPT` and returns worth 0–3, a headline, a caption and an action-focused painter sentence (~$0.0001 per turn). Worth 3 = a **turning** moment that leads and skips the cooldown; worth 2 is painted after the fixed moments (settled rumour > arrival > first meeting). At most one picture per beat and one per 3 beats (settled and turning points bypass this). Without a writer the fixed moments still paint, captioned mechanically. Evidence: `docs/evidence/key-moments-001`. **Repaint from the moment view:** "See and edit the prompt" shows the whole prompt as sent (`GET /world/pictures/{id}/prompt`, built by `scene_prompt` exactly as the runner builds it); "Regenerate" (`POST /world/pictures/{id}/repaint`) queues a `scene:repaint:` job and marks the prompt `raw_prompt` (sent as written; faces still go as references). The old painting shows until the new one is done (`repaint_job_id`, migration 0055; the runner swaps `job_id` on completion and never reuses old art for repaint keys); the dialog polls `/assets/jobs/{id}` with a 0.1 s clock. This happens only when an image service is configured (`paint_moments`) and the "Paint key moments" setting (`scene_moments`) is on. Faces stay consistent: portraits are registered on Krea as `ev-<24hex>-v<version>` and sent as `characters`, and place art goes in `references` (≤2 people + place). **"Paint this scene"** = `GET /world/scenes/{id}/picture-suggestion` plus `POST /world/scenes/{id}/pictures`, using an editable plain-words prompt with speech and backstory stripped. Pictures are served in presentation `scene_art`.
- Portraits: prompts carry pronouns (7f552aa). Painted portraits get a face frame from the map reader (89638ab; backfill `frame_painted_faces.py`). Characters can import their own picture, framed 2:3 portrait plus face circle (e70cbba, PictureFramer.vue). `POST /library/portraits/paint` paints from the studio (be5d3ac). The portrait studio shows and edits the raw Krea prompt: `POST /library/portraits/prompt` returns the whole prompt plus settings (checkpoint, style, ratio, mode, seed) built exactly as painting builds it, and `paint` with `raw: true` sends an edited prompt as written (07c34af). While painting, the picture blurs under turning rings and a clock in tenths of a second.
- World covers: a 16:7 banner (`POST /library/covers`, 1d872f4). Stories copy it.
- Style packs: `content/visual-styles/*.json`. These are **view-only in the Library ("Coming soon", cf28f06)**, like templates.

### 3.9 Worlds, maps, terrain, places
- **World map page** `/library/world/:id/map` (WorldMapView.vue, 46c578d): upload or paint a map. GPT-6 Luna reads the places (`POST /library/maps/{id}/places`, told the world's own names, 9145dd7) and Sonnet 5.5 traces the roads (`/roads`). The player fixes pins and roads and sets the shortest and longest trip. Saving with `PUT /library/presets/{id}/map` writes a new revision, and new stories time their routes from it.
- Hand drawing: place, road and bend tools plus a "Blank parchment" canvas (5f78018, `src/game/parchment.ts`).
- **Terrain grid** (f4587c9): `POST /library/maps/{id}/terrain` gives a draft from Gemini 3.8 Flash, painted by hand with a brush. Roads are timed by terrain-weighted length (mountains 2.6x, marsh/snow 2x, hills 1.6x, forest 1.4x, sea/river unweighted). The weighting is in `domain/geography.py` and mirrored in `src/game/terrain.ts`.
- Road stamina per phase: sea/river 1, road/bridge 2, path 3, pass 5, capped at 40 (`road_stamina`, 8184722).
- **Place maps (sub-maps)** `/library/world/:id/inside/:key` (PlaceMapView.vue, faf9b46): a picture per place with spots read by Luna (`POST /library/maps/{id}/spots`), saved with `PUT /library/presets/{id}/places/{key}/map`. "Inside every place at once" batch-paints, reads and saves each one (28c9ffb).
- Places without a drawn map sit on an even ring (`schematic_anchors`, 9145dd7).
- Editor publish keeps maps drawn after the draft opened (`keep_drawn_maps`, be5d3ac).

### 3.10 Library and studios
- Presets with immutable revisions, editor drafts, publish receipts, archive/duplicate (E3, Sept). Built-ins are the world Ember Vale (Hearth, Market), Wren, Ash, the Anime Saga style and the "Ember Vale opening" template (`application/library/builtins.py`).
- **Character studio** (be5d3ac) works in steps: Overview → Appearance → Background & personality → Voice → Review. The right panel changes per step (`CharacterSidePanel.vue`, helpers in `characterForm.ts`): concept, portrait studio (PortraitPicker `variant="panel"`), compass, voice (lines + "Hear a sample"); Review shows the full sheet (`CharacterPreviewPanel.vue`) and one line per step with Edit. Evidence `character-studio-panels-001`. **World studio** (a4065f7): Overview → The world → Places → Review, with World/Place/Summary preview tabs.
- **Studio layout (both studios, aa899ec, 43193c5):** the title ("Character studio"/"World studio" above it, "Editing …" for an existing preset) and a full-width step bar (`InlineStepper stretch`) sit above both columns; the form and the side panel start on one line and stretch to the same height (the form's last card grows). Side panels do not stick or cap their height. The user flags any gap under a side panel, so keep columns equal when adding steps.
- **Writing help**: `POST /library/writing/enhance` and `/fill` (`application/library/writing.py`, `infrastructure/writing/openrouter.py`, `WORLDSIM_WRITING__MODEL` default `openai/gpt-6-luna`). Fill writes only the empty fields, at ~$0.0003 per fill. `POST /library/writing/sample`: a 3–6 line exchange in the character's voice for a chosen situation, only on request (~$0.0001, ~2 s).
- Packed fields: studio fields pack into the existing payload text (`characterForm.ts`/`worldForm.ts`). `appearancePlain` (frontend) and `plain_looks` (backend, `application/pictures.py`, for painters) turn them into prose.
- Look and feel: Libron reading font, Alegreya Sans UI font, Cormorant for display, ember accent, KeepAlive pages, carousel slides (d3a47e0).
- **Motion (game feel, e91d555 and follow-ups):** one motion language in `src/styles/motion.css`: tokens (`--ease-settle` ≈ expo.out for entrances, `--ease-in` for exits, `--ease-io`, `--ease-sine` for loops, `--ease-spring` only for small confirmations), shared `<Transition>` names (`ev-fade`, `ev-swap` tabs/modes, `ev-step-next`/`ev-step-prev` wizards, `ev-modal` scrim + first-child panel, `ev-drawer`, `ev-sheet`, `ev-pop` menus, `ev-rise`, `ev-list` TransitionGroups) and utilities (`ev-press`, `ev-img-fade` + `is-loaded`, `ev-drift` Ken Burns, `ev-breathe`, `ev-flicker`, `ev-sheen`, `ev-push-in`, `ev-stamp`, `ev-skeleton`, `ev-dots`, `ev-pop-stagger`, `ev-rise`). Effects in `composables/useEffects.ts`: `burst(el)` sparks, `shake(el)`, `flash(el)`, `v-tilt`, `v-ripple`. `useMotion.ts`: `moves()`, `useTweened` (numbers glide), `v-reveal`. `decor/EmberField.vue` draws drifting embers. Reuse these before inventing new ones; animate transform/opacity only. Global defaults (f53af21): every button/tab/summary gives on press through the CSS `scale` property (so it composes with transforms); `role=alert`/status lines fade in; any `<img>` that loads after first paint fades in (`installMotion`, opt out with `data-no-fade`); `.ev-empty` gives empty states a floating sparkle, `.ev-pop-once` pops a badge. EmberField pauses off-screen. Clickables must not move constantly (map tokens pause their idle bob on hover; the active place's pin bobs, not its "Inside" label). Story entry from outside plays an iris (App.vue); the New Story launch screen shows only while the create request is in flight.
- **Settings › Appearance › Motion** (MotionSettings.vue, `src/game/motion.ts`): follow the computer / full / reduced, saved per device in localStorage `ev.motion` and written as `<html data-motion>`.

### 3.10b Performance and scaling (perf pass 2026-10-08, `docs/evidence/perf-summary-001`)
- **HTTP:** JSON over 1 KB is gzipped. JSON GETs carry a content-hash ETag with `private, no-cache`, so an unchanged poll is a 304 (`interfaces/http/etag.py`). The middlewares are plain ASGI, never `BaseHTTPMiddleware`.
- **Pictures:**
  - Pictures are immutable per id: year-long cache plus ETag.
  - `?w=` on `/assets/{id}` and `/library/assets/{id}/bytes` serves a WebP that wide, snapped to 96…1280 and encoded once into `generated/.variants/`. The frontend passes about 2x the drawn width (`assetUrl(world, id, w)`, `libraryAssetUrl(id, w)`); framers, the moment view and full-screen maps take the original.
  - Maps and the starter art are stored as WebP (migration 0056, `scripts/maps_to_webp.py`).
- **Reads:** batched (stories list 3 queries; chronicle 8); presentation flat to 300x story length. Adventure reads the chronicle newest-first and backfills (`chronicleReader.ts`). An idle tick reads only the presentation unless the story stamp changed.
- **Beats:**
  - one pooled HTTP client (`infrastructure/http_pool.py`) and graphs compiled once;
  - `WORLDSIM_APP__PARALLEL_MODEL_CALLS` (12), pool 10+20;
  - phase-shared world reads (`orchestration/phase_reads.py`, byte-identity verified in `tests/test_phase_reads.py`);
  - a cancelled request cancels its director;
  - a character's own observations, memories, relationships and digests are read once per phase, and perception rows insert in batches (−11–22% statements a turn; `perf-reads-001`);
  - a context ranks every recent row plus only the newest 200 older salient ones (`OLDER_SALIENT_KEPT`): ranking costs ~0.02 ms a row on every call and the salient set has no time limit. Flat to 1,000 turns.
- **Scaling:**
  - Image jobs are claimed with `FOR UPDATE SKIP LOCKED` plus a lease, and record created, started and finished times (migration 0057).
  - `WORLDSIM_APP__BACKGROUND_LOOPS=false` with `python -m worldsim.interfaces.worker` (compose profile `scale`) moves autoplay, painting and indexing out of the API; `WORLDSIM_APP__WORKERS=N` then serves from N processes.
- **Frontend idle:** ambient loops rest after 60 s without input; new chronicle entries wake them (`wakeScene()`).
- **Push vs poll:** polling stays. Load-tested: one process carries ~60 viewers watching autoplay (p95 159 ms at 50), and 4 processes ~100 dependably (150 is at the edge on this shared host). 90% of polls are 304s that still cost full work, `WORLDSIM_APP__PRESENTATION_FINGERPRINT=true` answers them from one fingerprint query (`WorldRepository.presentation_fingerprint`): p95 at 75 viewers 458 → 73 ms. It is off by default, and **any new write that the presentation shows must be added to `_FINGERPRINT` and to `tests/test_presentation_fingerprint.py`** (`perf-reads-001` §8–9). A quiet chronicle read is 3 queries, not 8, and uvicorn's duplicate access log is off.
- **Several API processes share `WORLDSIM_DATABASE__CONNECTION_BUDGET` (150)**, and compose runs Postgres with `max_connections=200`. Four processes at 10+20 each used to overrun the default 100 and fail requests under load.
- **Benches:** `backend/scripts/api_bench.py` (`--inprocess` counts queries), `beat_bench.py` (`--verify-reads`), `scripts/page-bench.mjs` (`--rested`, `--memory`), `llm_usage_report.py`.

### 3.11 Stories, settings, providers
- New Story wizard (6 steps, server story drafts, pinned revisions, atomic idempotent create). Layout follows the designer's mockups (7172899): each step has its own heading (`src/game/newStory.ts` `NEW_STORY_HEADS`), steps across the page, the step beside a panel showing its result (world preview, your cast with Starts at, your role over the world picture, story preview, storyteller by name from `storytellerName`), Review as one row per step with Edit; footer buttons say where they go. Step labels: World, Characters, Play mode, Story, Storyteller, Review (slugs unchanged). Left out on purpose: world tags and painted cover art in the mockups (no such data yet). **Quick hero** from Home: "Play as a new hero" (9fce20b, QuickHeroDialog.vue). The Home hero shows "Continue as X" (829f5bb).
- **Story settings** `/stories/:id/settings` (StorySettingsView.vue, 4dd5cb1, migration 0053): a per-story LLM prefix/suffix that wraps every role's user prompt through FramedGateway (system prompts stay stable for caching), an image prefix/suffix, and per-character image prefix/suffix. API: `GET/PUT /stories/{world_id}/prompts`.
- Settings > AI connections are real (`/settings/providers`, 070ddfb). Keys stay server-side and are referenced by env var NAME.
- Providers (`infrastructure/model_gateway/`): `fake` (default), `openrouter`, `venice` (f0106a5, always `include_venice_system_prompt=false`). OpenRouter `provider.sort` comes from `WORLDSIM_PROVIDER__OPENROUTER_SORT` (ac1d21b). Spend is OpenRouter's billed `usage.cost` (08f8c44), and cached tokens are stored (b9e84e5).
- **Local models** (`local-models/`, port 8110; 09a66c2, 8ac272d, 92b2ea0): optional. The API must keep working with it off. Start it with `local-models/.venv/Scripts/python.exe -m local_models.server --port 8110`.
- **Launcher** (cb8a7e3, acf3c79): `launcher-vX.Y.Z` tags publish binaries through `.github/workflows/launcher.yml` (first tag `launcher-v0.1.0`). After changing `launcher/`, bump `launcher/Cargo.toml` and push a new tag. Never hand-build release assets.
- CI: `.github/workflows/ci.yml` (frontend typecheck/lint/format/test, backend ruff/basedpyright/pytest), plus `nightly.yml` for the 11 `sim_gate` simulations.

### 3.12 Frontend routes (`src/router.ts`)
`/`, `/new-story`, `/library?tab=`, `/library/character/:id`, `/new-story/character/:id`,
`/library/world/:id`, `/library/world/:id/map`, `/library/world/:id/inside/:key?`,
`/new-story/world/:id`, `/stories`, `/stories/:id/play`, `/stories/:id/adventure`,
`/stories/:id/settings`, `/stories/:id/watch`, `/settings`, and `*` (StubView).

### 3.13 Backend routes that exist but have NO UI
`/macro/*` (long-term simulation: eras, lineage, endings), `/stage2/characters/{id}/diary`,
`/stage2/relationships*`, `/stage2/claims`/`beliefs`, `/stage2/skills`, `/stage1/party*`
(D&D party), `/stage2/director/hooks`, `/stage1/model-runs`, `/stage2/deity/overrides` and `/stage2/director/proposals`
(the UI goes through `/interventions`), `/library/import/*` and
`/export`, `/settings/cache*`, `/assets/jobs`. Before you build a feature, check whether a
backend for it already exists.

### 3.14 Deliberately not built, or deferred
- **Observatory event modal art**: it shows the world map with an honest caption. The scene pictures that presentation sends to watchers are not shown there (MomentDialog could be reused), and key moments are painted only for player stories.
- **Party combat (D&D-style, hit points, monsters)** exists in the backend (`/stage1/party*`, `tests/test_dnd_combat.py`) with no UI. Mockups with gold, HP bars and skill checks ("Arcana DC 12") would need that wired, not invented.
- Full-body renders and profile→body lineage, visible equipment and injuries, checkpoints/branches, and backup/restore (plan packets E7–E9) are **not built**. `src/game/images.ts` keeps placeholder slots only.
- Creating or editing style packs and templates: "Coming soon" (cf28f06).
- SSE streaming: polling only, by decision (capacity and design in `perf-reads-001`).
- System One (kNN or GLiNER predicting decision families) was evaluated 2026-10-06 and **not adopted** (52–56% agreement against a 41% baseline; it would also fight the anti-idle note).
- Reordering prompt sections for caching was **not adopted**: it gained only 2–4 points (b9e84e5, `scripts/prefix_eval.py`).
- The narrator on mistral-nemo was evaluated (`latency-eval-001`, nemo-001…007) and is not the default. Per-role routing allows it.
- `docs/evidence/implementation-ledger.md` (September) is **stale**. Its E4–E8 "blocked" rows have since been built.

## 4. Decisions and the evidence behind them

| Decision | Evidence |
|---|---|
| Live text model `deepseek/deepseek-v4-flash-0731` via OpenRouter, **reasoning OFF** (`WORLDSIM_PROVIDER__REASONING=off`); default and low reasoning exhaust token caps | `docs/evidence/beat-latency-001` |
| `OPENROUTER_SORT=throughput`: beats ~2x faster, all goals pass | `scorecard-016`, ac1d21b |
| Venice (`venice-uncensored-1-2`) is NOT the default: faster, but 43–73% repeated questions and ~2x cost. Note that the dev `.env` currently runs `ACTIVE_PROFILE=venice` for playtests | `scorecard-012` |
| Measure story changes with the scorecard, before and after, repeating a scenario ~3x. A single playtest is anecdote | `scorecard-001…033`, `playtest-001…011` |
| narrator.v4 over v3: equally valid, many more spots named, fewer stock phrases | `narrator-v4-001` (read the rescore correction at the top) |
| Spend was overstated ~17x before 08f8c44. A 40-beat session really costs ~$0.17 | 08f8c44 |
| Prompt cache: decisions/reactions/resolver 59–68% cached, narrator ~8% (under the cache minimum). Do not reorder sections | b9e84e5 |
| Map places → `openai/gpt-6-luna`, roads → `anthropic/claude-sonnet-5.5`, terrain → `google/gemini-3.8-flash` (`WORLDSIM_MAPS__*`) | `map-detect-001`, `map-routes-001`, `terrain-001`, adbe67e |
| Spots prompt v2: local names, no position words, ≤3 plain houses, at most 32 spots | `place-spots-001`, `place-spots-002` |
| Narrator spot rule must be firm ("set the scene at one spot, name it in the first beat") | `scene-spots-live-001` |
| Local embeddings run on CPU by default. iGPU fp16 returns zero vectors and fp32 breaks under load, so the iGPU is opt-in. Recall thresholds: low 0.45, high 0.80 | 8ac272d, `scripts/recall_eval.py` |
| Images: Krea checkpoint `krea2Anime_v15_bf16`, ~14 s per image. Never switch the checkpoint silently | b41ee72, `providers-images` notes |
| Face frames for painted portraits from Luna, 29/29 | `painted-faces-001` |
| Background narration: server turns 3–9 s instead of 6.5–17 s | b3130e6 |
| Crowds: an attempt is answered by the person it is aimed at plus 2 others (`WORLDSIM_APP__REACTING_BYSTANDERS`, default 2): −49% billed, −21% per beat, no scorecard loss over 3 runs each | `crowd-reactions-001`, scorecard-036…041 |
| Day-end summaries and digests cite short source tags (`summary.v2`, `digest.v2`): −82% output, no fallbacks. The scorecard reports and guards on the billed cost (list price ran ~2.5x under the bill) | `summary-tags-001`, scorecard-034/035 |
| Per-character reads shared per phase, batched perception inserts, older salient rows capped at 200, SSE deferred with a design | `perf-reads-001` |
| Perf pass: pages 3–8x lighter, idle CPU ~0.4%, reads flat to 300x, beat overhead 2–3x lower. uvloop, prompt reordering and removing the DB pre-ping were rejected. Crowd reactions since capped (crowd-reactions-001) | `perf-summary-001` and the five `perf-*-001` folders |
| UI review of 7 Oct (fonts, caching, studios, writing help) | `ui-review-001`, `docs/reviews/1/7_oct_2026-user-review.md` |
| Play-session fixes (prose opening, carried items, ring layout) | `play-session-001` |

## 5. How to run and check

**Ports.** The dev API is the docker container on **8101** (db on **5433**). Run vite on
**5180**: `npx vite --port 5180 --strictPort`, then open `http://localhost:5180`. Use
`localhost`, because the browser tool blocks 127.0.0.1. The vite proxy forwards `/api` to 8101
and injects the bearer key from `.env`. Calls made straight to 8101 need
`Authorization: Bearer $WORLDSIM_SECURITY__API_KEY` (health routes excepted). **Ports 5173
and 8000 on this machine belong to OTHER apps (5173 is the user's Granter app). Never start,
stop or probe services there.** `vite.config.ts` still defaults to 5173, so always pass
`--port 5180`. local-models uses 8110, and the recovery harness reserves 8102.

```bash
docker compose up -d --build api      # after backend changes; the entrypoint runs alembic upgrade head
curl http://localhost:8101/api/v1/health/live
```

**Backend checks** (run from `backend/`):
```bash
export WORLDSIM_DATABASE__URL="$(grep '^WORLDSIM_DATABASE__URL=' ../.env | cut -d= -f2- | tr -d '\r')"
.venv/Scripts/ruff.exe check . && .venv/Scripts/ruff.exe format .
.venv/Scripts/basedpyright.exe                      # zero errors, no baseline
.venv/Scripts/python.exe -m pytest -p no:logging -n 4 -q -rf -W ignore   # ~2m40s
```
- **Never `-n auto`** locally: 14 workers against one Postgres cause setup errors. Without the DB URL every DB test times out (it falls back to 5432).
- New DB tests must request the `migrated_db` fixture (CI's base DB is never migrated).
- `pytest -m sim_gate -n 4` runs the slow simulations (~8 min; nightly in CI). The recovery-harness self-test is opt-in with `EMBER_VALE_HARNESS_SELFTEST=1`.
- Tests write evidence to a temp dir. `WORLDSIM_WRITE_EVIDENCE=1` / `WORLDSIM_WRITE_FIXTURES=1` regenerate committed bundles.
- Old-schema trap: `tests/test_preset_revisions.py` runs today's app against a 0031/0032 schema. A new column on a table that story creation writes must stay out of the INSERT when unset (no Python default, `eager_defaults=False`).
- Read the `-rf` failure summary before committing. Do not rely on `tail -1`.

**Frontend checks** (repo root):
```bash
npx prettier --write src
npx eslint .
npx vue-tsc --noEmit
npx vitest run
npx vite build --outDir "$TEMP/ev-build" --emptyOutDir   # REQUIRED
```
The vite build is required because prettier can reformat a multi-statement inline Vue handler
(`@click="a = 1; b()"`) into broken code, and vue-tsc does not catch it (d3ceb25). Put
multi-statement handlers in functions.

**Generated contracts.** After API schema or route changes, run from `backend/`:
```bash
.venv/Scripts/python.exe -m worldsim.interfaces.http.export --out ../content/schemas/openapi.json
.venv/Scripts/python.exe scripts/gen_ts_client.py          # writes content/clients/worldsim.ts; --check to verify
```
Add new schema names that the frontend needs to the `WANTED` tuple in
`backend/scripts/gen_ts_client.py`. After domain model changes:
`.venv/Scripts/python.exe -m worldsim.domain.schema --out ../content/schemas/domain-schema.json`.
`test_domain_schema` fails if you forget.

**Live measurement.** `backend/scripts/scorecard.py --live [--only X] [--max-usd 0.20]
[--provider venice]` runs 5 scenarios (strangers, lost_item, stuck_task, meet_up, named_place)
and writes `docs/evidence/scorecard-NNN`. A full run costs ~$0.13–0.28. `play_session.py`
plays Adventure against the dev API.

## 6. Working rules

- **Never `source .env` wholesale.** It selects a live provider, and a test run once hung
  ~60 min on network calls. Export single variables with `grep '^NAME=' .env | cut -d= -f2- | tr -d '\r'`.
- **Keys never reach the client.** The vite proxy injects the operator key server-side, and
  provider keys are referenced by env-var name.
- **Before any live run, check balances and report spend:**
  OpenRouter `GET https://openrouter.ai/api/v1/key` (usage). The limit is now unlimited, but
  that is not a blank cheque. Venice `GET https://api.venice.ai/api/v1/api_keys/rate_limits`.
  Tell the user the running total and the run's cap (`--max-usd`).
- **Evidence is never overwritten.** Each new run gets a new numbered folder
  (`scorecard-034`, `terrain-002`…) with a README covering the question, setup, table and
  verdict. When an evidence README turns out wrong, add a correction at the top and keep the
  old numbers (see `narrator-v4-001`).
- **Stop only processes you started.** For vite, kill the node PID you started (TaskStop can
  leave the child running). If Vite's module graph goes stale ("does not provide an export
  named…"), restart it with `--force`.
- **Another session may be editing at the same time.** Check `git status` before committing,
  and commit only your own files.
- **Commits:** a plain-English subject that says what changed for the player or the system
  ("Journeys: long roads take their time and cost stamina"). The body says why, with the
  measured numbers and evidence folder. End it with the trailers from the session's
  attribution reminder (currently `Co-Authored-By: Claude …`; follow whatever the reminder
  of your own session says). Commit evidence separately when it is large. Never skip hooks.
- **Pictures drawn small take a width:** `assetUrl(world, id, ~2x drawn px)`. A bare URL downloads the whole painting (a 1.6 MB PNG was drawn at 191 px). Only framers, the moment view and full-screen maps need the original.
- **asyncio cancels once:** when cleanup awaits a sibling task on cancellation, cancel that sibling first (`59528c7`; plain ASGI exposed a hang that anyio's repeated cancels had hidden).
- **Pictures that can change need a key.** `StoryImage` reads its slot once (`useGameImage`), so a reused one shows a stale picture when the slot changes; give it `:key` (the New Story banner bug, 7172899).
- **No `:global(.x) .y` in scoped styles:** Vue compiles it to plain `.x`, so the rule hits the parent itself (it collapsed the Library's List mode to 240 px). Style a child from the parent with `.x :deep(.y)` instead.
- **Reduced motion:** `src/styles/motion.css` applies it when `<html data-motion="reduced">`, or when the system asks and the viewer did not choose Full (Windows with animation effects off reports it; the user's machine does). It stops movement but keeps opacity/colour fades; progress indicators keep the class `ev-progress-spin` so they still turn (7646ede). A component's own reduced rule must use both selectors, `:root[data-motion='reduced'] .x` and, inside `@media (prefers-reduced-motion: reduce)`, `:root:not([data-motion='full']) .x`, never a bare media query (it would override Full). Script-driven motion asks `moves()`.
- **Run checks without pipes hiding failures:** `basedpyright | tail` reports tail's exit code; a type error shipped that way once (fixed 9e8bd8e). Check `$?` or read the "N errors" line.
- **Player-facing copy is plain language.** Say "Turn", not "Beat". Leave out revision
  numbers, ids, "usage not tracked yet" and developer jargon. Never show a control that does
  nothing; say "Coming soon" honestly instead (cf28f06). Keep new UI in the existing tokens
  and fonts (`--font-body` Libron, `--font-ui` Alegreya Sans, `--ember`).
- **Honesty rules from the plan:** no fake success from timers, no generation on mount or on
  read, and missing capabilities are reported as missing.
- **LLM output is a proposal.** Validate it, trim the junk before validation instead of paying
  for repairs, and never let prose mutate state.
- **Windows / Git Bash pitfalls:** MSYS rewrites arguments that start with `/` (e.g. `/api/v1/...`
  as a CLI arg) into Windows paths. Use `MSYS_NO_PATHCONV=1` or a full URL. Heredocs that put
  `\n` inside Python strings get mangled, so write a small script file instead. Output from
  `find`/`ls` piped into pytest args can carry stray characters, so use a `pytest.main` helper.
- Browser playtests that hide the tab send no autoplay presence. Script
  `POST /stories/{id}/autoplay/presence` instead.
- Dev data worth keeping: world "The Saltreach" (8995a291), "Ember Vale copy" (aa12c4f2) with
  maps, roads and place insides.

## 7. Before saying something doesn't exist

Run these first. The answer is usually yes.

```bash
git log --oneline -i --grep='<word>'                 # e.g. picture, paint, spot, terrain, rumour
git log -S'<identifier>' --oneline                  # when a symbol appeared
grep -rn '<word>' backend/src/worldsim/interfaces/http/routes   # is there an endpoint?
grep -rn '<word>' src/views src/components src/game src/composables
grep -rn '<word>' src/api/worldsim.ts               # does the frontend call it?
ls backend/migrations/versions | tail                # newest tables
ls docs/evidence                                     # was it measured or decided?
grep -n '<word>' backend/src/worldsim/infrastructure/settings.py   # is it a setting?
```
Also check the memory notes in `~/.claude/projects/C--Users-JoelWang-Documents-dev-ember-vale/memory/`.
Remember that a feature can exist in the backend with no UI (§3.13), or in one screen and
not another (scene pictures are in Adventure, not in the Observatory modal). Say exactly
which one it is.
