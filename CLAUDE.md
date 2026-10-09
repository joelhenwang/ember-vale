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
| `backend/migrations/versions/` | Alembic `0001`–`0058` and `0060` committed (0060 chains onto 0058; re-chain it after any 0059). The API container's entrypoint migrates on start |
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
- **Combat (storyteller-driven, no turn order):** in a world with a party roster, the narrator writes tags that `resolve_narration_tags` (`domain/rules/dnd/combat_resolve.py`) rolls after the prose: `ENCOUNTER[2x goblin]`, `ATTACK[longsword at goblin]`, foes striking back `ATTACK[goblin at Wren]` (the monster's first weapon action; the fallen do not strike), `CAST[fire bolt at goblin]`, `CONDITION[poisoned on Wren]`, `RECRUIT[Lyra]: elf ranger, level 3`. The rules are `prompts/dnd-rules.v2.md` (`STORY_RULES_PROMPT_VERSION`; v1 stays for the parity test; v3 is kept as a file but made a live narrator write no tags, combat-depth-001 `rules-ab.json`): each tag starts its own beat, an untagged fight does not happen, and the prose never decides the dice. A `dnd-foes` fact says in words which fight is on, so it is not re-ENCOUNTERed. One combat event per scene (`derive_combat_event_id`) keeps `summary.rolls` (JSON, each roll in parts), `scene_event_id` and `foes`; spars keep the same shape. Readers never see tags: `strip_combat_tags` runs on narration, chronicle, timeline and picture prompts. **Combat depth (combat-depth-001, no migration):** each foe of a group has its own pool: `ENCOUNTER[2x goblin]` makes Goblin 1/Goblin 2 (keys `goblin-1`/`goblin-2`; a lone foe keeps its plain key). Tags aim by number (`Goblin 2`, `the second goblin`, `goblin #2`); a plain name is the first of its kind still standing. A fresh ENCOUNTER after a finished fight starts fresh; while that kind still stands in the fight that is on, newcomers are numbered after them (`fighting` = `foes_on` keys), and the fight event's `foes` are the fight that is on plus the scene's. Fallen foes give their SRD XP (`monsters.json` `xp`) shared evenly by the party; crossing a 5e threshold levels up via `level_up_preview` (`domain/rules/dnd/progress.py`: `gain_xp`, `level_up`). Levelled CASTs spend a slot (lowest free at or above the spell level, upcast); none left = a plain `no-slot` roll; cantrips free; slots come back when the **story day** changes (`Sheet.slots_used` on `slots_day`, lazy, no hook). Rolls add `xp` (`amount`, `share`) and `level` rows; `GET /stage1/party` adds `spell_slots_left`, `xp`, `xp_level_start`, `xp_next_level`. The party's sheets and rules reach only scenes the linked hero is in (`party_in_scene`; an unlinked hand-begun party counts everywhere). **Combat depth 2 (combat-depth-002, no migration):** the **player's own words roll**: a linked hero's interact attempt this scene (`Deed`, `domain/rules/dnd/deeds.py`) that plainly attacks or casts, when the storyteller did not tag that hero, adds the tag line itself (after the scene's first ENCOUNTER): a weapon or spell on the sheet that the words name (else the first weapon that suits the verb: shoot/fire/loose → ranged), aimed at a foe of the fight that is on or of the scene's ENCOUNTER (by number when named, else the first); with no fight on, a creature both the player and the prose name opens one. Stand-down words ("lower", "sheathe", "don't"), a downed hero and a kind already slain in this story (only the storyteller's ENCOUNTER brings another) are no deed; healing spells aim at a named party member or the caster. The fight event's summary counts them (`deeds`). **Foes strike back by themselves**: when the party fought in a scene and the storyteller tagged no foe's blow, each foe standing (up to 3) strikes once at the hero who acted (`strike_back`). A hero at 0 HP neither swings nor casts; a blow at a fallen foe rolls nothing. The narrator hears a fight that just ended (`fight_over_line`, as `dnd-foes`) and who is down (`dnd-down`), and no resolver verdict on a blow ("it does not work" read as a contradiction of the dice). When narration fails or falls back, the party's own blows still roll. A spar without two sheets is no bout (it used to fail the turn after the scene committed, leaving it half done). A hero at 0 HP **stays down** on a level-up (the maximum grows). A later story day is the **long rest** (`long_rest`, lazy on `Sheet.rest_day`): full HP, conditions cleared, slots back; applied in resolve, spars, the narrator's sheets and `GET /stage1/party`. **Level-up choices** (`Sheet.choices`, `LevelChoice`): a level with an Ability Score Improvement leaves the linked hero +2 to one or +1 to two, and the spells a level brings are picked for them and may be swapped (`make_choice`; `POST /stage1/party/{member_id}/choices`, the hero's player or a Director/God); unlinked companions take +2 in their class's first abilities at once. Level rolls carry `choose`. Live (Venice, `combat-depth-002`): the hero's blow rolled on every attack turn with a foe up (27/27; the storyteller alone tagged 33%), about one foe blow per attack turn, 5 of 6 fights won in 6 turns. **Experience beyond fighting (quest-xp-001, no migration):** a rumour that settles (the director's `resolved` or the resolver's `hook_settled`) gives every party member, in full, the 5e medium-encounter XP for their own level (`settle_xp` = `ENCOUNTER_BUDGET` medium: 50 at level 1, 100 at 2, 150 at 3, 250 at 4, 500 at 5; `award_settled` in `domain/rules/dnd/quests.py`, sheets woken by `long_rest` first, levels by `gain_xp` with choices for linked heroes only). `award_settled_hooks` (`application/orchestration/settle_xp.py`) runs after the director's accept and after a scene commit that carried `hook_settled`, in its own transaction (a version conflict retries once; it never fails the turn), and writes one event per rumour (`derive_settle_xp_event_id`, so a replay gives nothing twice) whose `summary.rolls` hold an `xp` row with `result: "settled"` (`target` = the rumour's title, `share` = XP each; members of different levels get one row per amount naming them) plus `level` rows; the resolver's settle names its scene (`scene_event_id`), the director's stands on its own in the turn. Adventure, Watch and the story room show it with the dice under the heading **Experience** (`onlyExperience`, "The missing flour is settled · 50 XP each"), and Watch's die mark skips experience-only rows. Stories without a party are unchanged. **Fair fights and companions (companions-001):** weapon damage adds the weapon's ability (Str, Dex for ranged, the better for finesse; never below 1), spars too (`weapon_damage`). There is no death and dying: a hero at 0 HP **gets back up with 1 HP** once the fight is over (the scene ends it, or the next party scene with no fight on; roll kind `recover`, "Wren gets back up"). A fight begun without an ENCOUNTER opens one as large as the words count ("two goblins", "a pair of wolves": `opening_lines`, `group_size`; a lone foe is still just met; a slain kind opens nothing). A tag line is the blow of the party member its prose names first (`line_actor`), the weapon decides only when it names no one. **Companions:** a combat-story hero's invitation ("join me", "be my companion", "travel with me"…, `domain/rules/dnd/invites.py`) tells the invited character to answer plainly now; a plain yes makes them a companion at once (`_join_invited`, after the scene commits), **linked to their own character** at the party's level. **Callings (callings-001, no migration):** their race and class are the small writing model's choice (`suggest_calling` in `application/callings.py`, `CALLING_PROMPT`: the card plus the party's members, one race and one class from the SRD tables that fit the character and, all else equal, one the party lacks; ~$0.0001 a join, logged as `calling suggested` with `cost_usd`); no writer, a failed call or an answer outside the tables falls back to the card's keywords (`companion_description`, else human fighter); the join never fails for it. The orchestrator's `moment_writer` is now always the writer when an OpenRouter key is set (moments still judge only while painting). `POST /stage1/party/{member_id}/calling` {`world_id`, `race`, `character_class`, `expected_version`} (`change_calling` in `commands/party.py`; the hero's player or a Director/God) rebuilds a companion's sheet with `auto_sheet` at the same level, keeping name and XP. Allowed only for a companion (never the played hero: the role grant's character, else the one the story was created for) who has **never fought**: no kept roll in any event (`list_rolled`) names them as actor or target (recruit/xp/level rows do not count, so settled-rumour XP does not lock it), and no fight is on (`domain/rules/dnd/callings.py`); `PartyMemberView.calling_changeable` says so. A race named in full wins in RECRUIT descriptions and card keywords ("half-elf" was read as elf). A linked companion's own attacks roll as deeds; a companion beside the played hero (in the hero's scene, or at the same place: `present_keys`) whom nothing had act strikes the first foe standing (`helper_lines`, `helped` on the fight event). Only the played hero chooses at level-up (`chooser_keys`, from the role grant). Spars have their own event id (`derive_spar_event_id`; sharing the combat id lost the fight's dice) and no friendly bout happens while a fight is on (a spar chosen then becomes waiting, so the storyteller does not narrate one). **Companions as companions (companions-002):** a linked companion's decisions and reactions carry a note that they travel with the hero's party and, with a fight on, which foes stand (`companion_note`, `_party_note`); when the hero moves, a companion standing with them gets the same move (`_follow_hero`), and a companion's own move away becomes staying put (they leave only with the hero). The fallback strikes the most wounded foe standing; a hero's Say to a companion naming a foe ("Ash, take the third goblin!") aims that companion's blow that scene (`order_target`, `orders`). While a fight is on, a companion's own spar/wait/look-around/rest becomes their blow (`_companion_attack`, `companion_attack`: "I attack Goblin 2 with my longsword"), at the foe the hero ordered this fight, else the most wounded. Orders steer that companion's blows (tags included) and last the fight they were given in (world config `party_orders`, `stored_orders`/`orders_record`). A party member's blow at a foe already down re-aims at the most wounded foe standing (`retarget`). An ENCOUNTER smaller than its prose opens as many as the prose tells, and the last two turns' prose counts when the player's words open a fight (`recent`). **Long play (long-adventure-001):** the player's words cannot reopen only a kind slain in the last fight while it lingers (`slain_lately`; it used to be forever); a blow at no known creature rolls nothing; when a party member attacks and no fight is on, the narrator gets `dnd-seek` ("the party is looking for a fight: bring foes in with ENCOUNTER or show none are found"). A stale out-of-bounds effect is a version conflict (the scene is redone), not a 500 (`_check_fresh` in `transactions/canonical.py`). **Story pacing:** fallen foes and settled rumours give `WORLDSIM_APP__XP_SCALE` (default 4) times their 5e XP (`xp_scale` on `resolve_narration_tags` and `award_settled`); at 1x a hero had 25-50 XP after 26 live turns against 300 for level 2. Set it to 1 for plain 5e. A settled rumour gives XP only when a linked party member is among its people or in the scene where it settled (`party_took_part`).
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
- **Repeat guard** (`domain/rules/repeats.py`): shows up to 3 answered exchanges, and a repeated question gets ONE retry (word overlap ≥0.6 or local cosine ≥0.85) (729a04a). Replies get the same note and one retry (`reply-guard-001`; it rarely fires: replies repeat ~2%, mostly not answered questions). The scorecard's `repetition_rate` counts turns only; `reply_repetition_rate` and `reply_retries` count replies.
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
- **Combat stories (opt-in, party-combat-001):** a story created with fights has a party. Adventure then shows **Your party** in its own row under the picture, members side by side (`components/story/PartyPanel.vue` `row`; it used to share the small lead box and cut off a companion's Change): hero first, then companions, each with level and calling, a health bar, AC and conditions; an "In a fight" badge and **Foes** with health while a fight is on. Character details holds the full version (weapons, spells, spell slots a day), and the status bar has a Health bar. Each card shows an XP bar toward the next level and, for casters, "Spell slots today 1 of 3 first-level"; the newest fight's level-ups show a "Level up!" badge (and sparks when it happens). This combat level ("Level 2 Cleric") lives in the party panel only; the status bar's level is journey renown. Foes of a group are listed one by one (Goblin 1, Goblin 2) with their own bars. A companion who has not fought yet shows "Ash joined as a human ranger · Change" (`CallingPicker.vue`: People and Calling selects from `HERO_RACES`/`HERO_CLASSES`, `joinedAs` in `party.ts`; the roster updates at once, callings-001). A level-up choice shows "A level-up choice is waiting" under the party, and Character details holds **Level-up choices** (`LevelChoices.vue`: six ability buttons, +2/+1 with the cap; spells to keep or swap), and the dice say "choose a better ability in Character details" (combat-depth-002). The dice also say "Goblin 2 is defeated · 50 XP", "Level up! Wren reaches level 2 · +7 hit points" (popped, sparks when fresh) and "No spell slot left · it fails" (combat-depth-001). Each fight's rolls sit under their scene as **The dice** (`CombatRolls.vue`, words from `src/game/party.ts` `sayRoll`): d20 badge, who attacked whom with what, total vs AC or DC, hit/miss/critical, damage, health before → after, saves, heals, recruits. A hurt card shakes, a heal glows, and a fresh critical throws sparks. The party is read with the character sheet when the story stamp changes; the stamp includes `recent_event_id`, because rolls land after the scene is told. Stories without fights look unchanged.

### 3.7 Watching: Observatory and story room
- **Story watch / Observatory** `/stories/:id/watch` (ObservatoryView.vue, 020a09f): map with tokens, event feed, event modal, Step/Play/Pause driving **server-side autoplay** (`application/autoplay.py`, `/stories/{id}/autoplay/*`, migration 0041, 9a22ec2). Autoplay stops after 60 s without presence. Player stories cannot autoplay. **The dice in Watch** (combat-depth-001): a fight's rolls fold into their scene (`groupFeed`), the feed marks a scene with dice with a small die (`EventFeed` `fought`), and the event view shows them under the narration (`EventModal` `rolls`, reusing `CombatRolls.vue`; `rollsByScene`/`rollsFor` in `src/game/observatory.ts`). A turn with dice is never folded into a quiet stretch.
- **Pictures in Watch** (watch-pictures-001): the event view shows the scene's picture and opens MomentDialog, says so while one is being painted, and otherwise offers "Paint this scene" (PaintSceneDialog); the feed marks scenes that have a picture.
- The map is the world's own drawn map with its roads, and travellers walk along them by the clock (b6310b7, 8184722). Places with their own map get an "Inside" chip that opens PlaceMap.vue, where people stand at their newest named spot or at a spot that suits their activity (faf9b46, b364d5c, `src/game/placeMap.ts`).
- **Story room** `/stories/:id/play` (PlayView.vue): the older form-driven room, used for the Director/God seats. It holds the **interventions** UI (typed interpret → queue → apply; `/interventions`, `useInterventions`) and the "You are on the road to X" banner for travelling players. **Party, dice and going back:** a combat story shows the party panel at the top of "Cast & places" (`PartyPanel`, titled "The party" for a seat that plays no one; `GET /stage1/party` serves every role and is re-read once a load has paged through and whenever the turn or the number of entries changes). Each turn's dice sit under their scene (`BeatEntry` `rolls`, from `rollsInTurn` in `src/game/observatory.ts`: under the scene when it is in the turn, else under the fight's own event); `/stage2/timeline` entries carry `combat` like the chronicle (`combat_log` in `queries/presentation.py`). Turn headings offer "Branch from here" and "Go back to this turn" (`useBranchPoints`, `canBranch`/`canRewind`, `BranchDialog`); after going back the room drops the removed turns' scene pointers (`useStory.forgetAfter`) and reloads in place.
- Which screen a story opens on: `src/game/storyRoute.ts` (player → adventure, watcher → watch, director/deity → play).

### 3.8 Images (Krea 2 Studio)
- Image jobs: idempotent, bounded retries, versioned assets. The runner works pending jobs one at a time (`infrastructure/images/runner.py`, `krea.py`, 0c8a4d3). It stores WebP at display size and keeps curated portraits. Jobs are queued at story creation (portraits), on director spawns and places, and on key moments. **Never on read.**
- **Picture sweep** (picture-sweep-001, `infrastructure/images/sweep.py`, `PictureSweeper` in the background loops of the API or worker): deletes files under `content/assets/generated` that no `asset_record` row (any story, branch or the library) has as its `content_ref`, and `.variants/<asset id>-w*.webp` whose asset row is gone. `asset_record` is the only place a file is referenced (checked over every text/json column of the dev DB). Careful by design: older than `WORLDSIM_IMAGES__SWEEP_GRACE_HOURS` (1) AND already unused at the previous sweep of the process (`SWEEP_EVERY_HOURS`, 6; the first sweep after a start deletes nothing, so backups taken between a rewind and the sweep stay whole), DB read after the folder is listed, no rows at all = deletes nothing, never outside `generated/` (starter art in `revamp/` untouched), no symlinks; failures only log. `SWEEP_UNUSED=false` turns it off (tests do, in conftest). Dry run: `backend/scripts/picture_sweep.py` (`PICTURE_SWEEP_LIST=1`). A painting whose job was removed mid-paint (rewind) records nothing and leaves its file to the sweep (runner `_job_gone`).
- Settings > Image generation: every Krea field, live status and a "Try it" preview (`/settings/images/service`, `/settings/images/preview`; DB prefs `application_preferences.images`, migration 0051, b41ee72). The default checkpoint is `krea2Anime_v15_bf16`. Switching checkpoints costs ~35 s and affects every user of the machine, and the UI warns about this.
- **Scene pictures / key moments** (d483c4b, `scene_picture` table, migrations 0052 and 0054, `application/pictures.py`). Once a beat's narration is written (behind the turn, `Stage1Orchestrator._queue_moment`), a small writing model (`WritingSettings.model`, the library writer) reads the player's scene with `MOMENT_PROMPT` and returns worth 0–3, a headline, a caption and an action-focused painter sentence (~$0.0001 per turn). Worth 3 = a **turning** moment that leads and skips the cooldown; worth 2 is painted after the fixed moments (settled rumour > arrival > first meeting). At most one picture per beat and one per 3 beats (settled and turning points bypass this). Without a writer the fixed moments still paint, captioned mechanically. **Watched stories** (no player, watched-moments-001) get moments too: every scene is a candidate, the fixed moments are a settled rumour and the first scene any two characters share (no arrivals), the writer reads up to 3 of the longest scenes, and only a settled rumour skips the cooldown there. Evidence: `docs/evidence/key-moments-001`. **Repaint from the moment view:** "See and edit the prompt" shows the whole prompt as sent (`GET /world/pictures/{id}/prompt`, built by `scene_prompt` exactly as the runner builds it); "Regenerate" (`POST /world/pictures/{id}/repaint`) queues a `scene:repaint:` job and marks the prompt `raw_prompt` (sent as written; faces still go as references). The old painting shows until the new one is done (`repaint_job_id`, migration 0055; the runner swaps `job_id` on completion and never reuses old art for repaint keys); the dialog polls `/assets/jobs/{id}` with a 0.1 s clock. This happens only when an image service is configured (`paint_moments`) and the "Paint key moments" setting (`scene_moments`) is on. Faces stay consistent: portraits are registered on Krea as `ev-<24hex>-v<version>` and sent as `characters`, and place art goes in `references` (≤2 people + place). **"Paint this scene"** = `GET /world/scenes/{id}/picture-suggestion` plus `POST /world/scenes/{id}/pictures`, using an editable plain-words prompt with speech and backstory stripped. Pictures are served in presentation `scene_art`.
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
- **Combat stories** (party-combat-001): in New Story's Play mode a player story chooses "A tale" (default) or "An adventure with fights", plus the hero's people (9 races) and calling (12 classes) from `content/dnd`. The draft carries `mode.adventure {race, character_class}` (validated in `stories/validation.py`, player only), and `stories/create.py` adds the hero's level-1 sheet (`auto_sheet`) to the party inside the atomic create, linked to the played character. Drafts without it hash as before. Watcher stories never fight.
- **Branch from any turn** (story-branches-001, migration 0058): from a kept turn, a player or watcher starts a NEW story that continues from the end of that turn; the original is untouched. Every turn keeps a **checkpoint** at its end (`story_checkpoint`: one JSON of every changeable row of the story plus the event cursor, built in Postgres by `uow.checkpoints.capture`, called from `Stage1Orchestrator._keep_turn` after the scenes commit, or after day-end work on a midnight turn). A branch (`application/stories/branch.py`, copy in `infrastructure/repositories/checkpoints.py`) takes changeable state from the checkpoint and history (events, scenes, narration, observations, memories, summaries, finished pictures) up to the turn from the live tables, renames every id (runs/snapshots/intents/attempts/reactions/resolutions keep their derived form), shares picture files by `content_ref`, never copies pending image jobs, model calls, task runs or autoplay. `POST /stories/{id}/branch` (`absolute_index`, optional `title`, `Idempotency-Key`), `GET /stories/{id}/branch-points`; `story_branch` provenance shows as `branched_from` on story list/detail ("Branched from X at Day 1, morning"). UI: "Branch from here" on Adventure's turn headings, Watch's feed headings and event view (BranchDialog.vue, `src/game/branches.ts`, `useBranchPoints`). Turns without a checkpoint (played before 0058, or whose keeping failed) are **refused** plainly, never rebuilt. Tests: `tests/test_story_branches.py`.
- **Retention and going back** (rewind-001, migration 0060): a story keeps the checkpoint of each of its newest 200 turns (`KEEP_RECENT_TURNS` in `domain/branches.py`) and, before those, only each day's last turn (midnight); `uow.checkpoints.prune` runs right after each capture in `_keep_turn` (own transaction, failures logged; ~5 ms, flat). Older pruned turns are refused with "For older days only each day's last turn is kept…" and are simply not offered in the UI. **"Go back to this turn"** (`POST /stories/{id}/rewind` {`absolute_index`}, `Idempotency-Key`; `application/stories/rewind.py`, `checkpoints.rewind`): in ONE transaction it first saves the story as it stands as a branch from its newest turn titled "<story> — the path not taken (Day N, time)" (a failure there stops everything), then restores the turn's checkpoint in place and removes everything after it (events, runs, snapshots, scenes, narration, observations, memories, summaries, pictures of removed scenes with their jobs and asset rows, model calls/costs/manifests and task runs of removed turns, recall vectors, later checkpoints), pausing autoplay. Anchors (`world`, `entity`, `location`, `character`, `character_card_version`) are upserted and later rows deleted; every other state table is emptied and reinserted from the checkpoint, so **a table added to `STATE_TABLES` is rewound with no other change**. Rewind itself never deletes picture files (branches share them by `content_ref`); the picture sweep (§3.8) removes the ones no row refers to any more. Migration 0060 lets `phase_snapshot` rows be deleted only when the transaction sets `worldsim.rewind = on`. Refused: the newest turn, a turn not kept, the newest turn not kept, a turn or its writing still running (holds the next turn's execution slot while it works). `branch-points` now returns `latest_turn`; UI: "Go back to this turn" beside "Branch from here" on Adventure turn headings, the Watch feed and event view (`BranchDialog mode="rewind"`, `canRewind`), which then reloads the story in place. Tests: `tests/test_story_rewind.py` (incl. a guard that every table with a `world_id` is classified).
- **Story settings** `/stories/:id/settings` (StorySettingsView.vue, 4dd5cb1, migration 0053): a per-story LLM prefix/suffix that wraps every role's user prompt through FramedGateway (system prompts stay stable for caching), an image prefix/suffix, and per-character image prefix/suffix. API: `GET/PUT /stories/{world_id}/prompts`.
- Settings > AI connections are real (`/settings/providers`, 070ddfb). Keys stay server-side and are referenced by env var NAME.
- Providers (`infrastructure/model_gateway/`): `fake` (default), `openrouter`, `venice` (f0106a5, always `include_venice_system_prompt=false`). OpenRouter `provider.sort` comes from `WORLDSIM_PROVIDER__OPENROUTER_SORT` (ac1d21b). Spend is OpenRouter's billed `usage.cost` (08f8c44), and cached tokens are stored (b9e84e5).
- **Local models** (`local-models/`, port 8110; 09a66c2, 8ac272d, 92b2ea0): optional. The API must keep working with it off. Start it with `local-models/.venv/Scripts/python.exe -m local_models.server --port 8110`.
- **Launcher** (cb8a7e3, acf3c79): `launcher-vX.Y.Z` tags publish binaries through `.github/workflows/launcher.yml` (first tag `launcher-v0.1.0`). After changing `launcher/`, bump `launcher/Cargo.toml` and push a new tag. Never hand-build release assets. **Backups screen** (launcher 0.2.0, `launcher/src/backups.rs`): **B** while playing lists `./backups` (local time, stories, size), **N** backs up now, **Enter** restores the chosen one after a confirmation (backup of the current state first, stop api/worker, `backup restore <stamp>`, start api, wait for health); each step is logged and a failure names its step.
- CI: `.github/workflows/ci.yml` (frontend typecheck/lint/format/test, backend ruff/basedpyright/pytest), plus `nightly.yml` for the 11 `sim_gate` simulations.

### 3.12 Frontend routes (`src/router.ts`)
`/`, `/new-story`, `/library?tab=`, `/library/character/:id`, `/new-story/character/:id`,
`/library/world/:id`, `/library/world/:id/map`, `/library/world/:id/inside/:key?`,
`/new-story/world/:id`, `/stories`, `/stories/:id/play`, `/stories/:id/adventure`,
`/stories/:id/settings`, `/stories/:id/watch`, `/settings`, and `*` (StubView).

### 3.13 Backend routes that exist but have NO UI
`/macro/*` (long-term simulation: eras, lineage, endings), `/stage2/characters/{id}/diary`,
`/stage2/relationships*`, `/stage2/claims`/`beliefs`, `/stage2/skills`, `/stage1/party/begin`
and `/stage1/party/{id}/link` (the wizard creates the hero instead; `GET /stage1/party` feeds Adventure), `/stage2/director/hooks`, `/stage1/model-runs`, `/stage2/deity/overrides` and `/stage2/director/proposals`
(the UI goes through `/interventions`), `/library/import/*` and
`/export`, `/settings/cache*`, `/assets/jobs`. Before you build a feature, check whether a
backend for it already exists.

### 3.14 Deliberately not built, or deferred
- **Party combat** is wired for player stories (opt-in, §3.6/§3.11), with each foe its own health, XP and levels, spent spell slots (combat-depth-001), the player's own attacks rolled, the long rest healing and level-up choices (combat-depth-002). Not built: a turn-based or initiative engine (deliberately: the storyteller drives fights), gold, skill checks outside fights ("Arcana DC 12"), XP outside fights other than a settled rumour (quest-xp-001), death and dying (the fallen get back up after the fight instead), short rests and feats. The dice and the party show in Adventure, Watch and the story room.
- Full-body renders and profile→body lineage, and visible equipment and injuries (plan packets E7–E9) are **not built**. Rewind in place is built (§3.11, rewind-001). Backup/restore is built (`backups-001`: compose `backup` service, `scripts/restore-backup.sh`, launcher Backups screen). Branching from a turn is built (§3.11); turns played before migration 0058 cannot be branched (their state was overwritten in place), and queued Director/God requests are carried only as they stood at the turn. Going back keeps the model calls and costs of removed turns (their run/task links are cleared), so the story's spend never drops. Removed pictures' files are deleted by the picture sweep (§3.8) some 6–12 hours after nothing refers to them any more. `src/game/images.ts` keeps placeholder slots only.
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
| Combat is opt-in per story and stays storyteller-driven (tags rolled after the prose, no initiative engine). A real narrator wrote no tags until the rules said each tag starts its own beat and an untagged fight does not happen (Venice: 0 → 2 tagged attacks over 3 turns, $0.021) | `party-combat-001` |
| The player's own plain attack or spell rolls even when the storyteller forgets the tag (deeds: 27/27 attack turns rolled live, the storyteller alone 33%); silent foes strike back; the slain stay slain; a downed hero stays down on a level-up; a new story day heals; ASI and spell choices are the player's ($0.40 live) | `combat-depth-002` |
| Weapons add their ability to damage; the fallen get back up after a fight; "two goblins" opens two; an invitation is a plain yes/no and a yes joins at once; companions fight beside the hero; a tag line is the named member's blow; spars have their own event id. Live: 2/2 joined (0/2 before), every rollable hero turn rolled, $0.24 | `companions-001` |
| Companions keep the party in mind, travel only with the hero, take orders ("Ash, take the third goblin!" struck Goblin 3 2/2 live), and join with a calling the writing model picks (Ash: human ranger, $0.00006); settled rumours pay only when the party took part. $0.11 live | `companions-002` |
| 26-turn live adventures: rest heals, companions travel and fight, turns ~11 s; fixed a stale-rest 500, goblins that could never return, rolls at 'enemy', and a storyteller that ignored a sought fight (fights per story 1 → 2). XP is 4x 5e for story pacing (the owner chose this; WORLDSIM_APP__XP_SCALE). $0.39 | `long-adventure-001` |
| Combat depth: numbered foes per group (plain name = first standing), XP shared evenly by SRD challenge rating, levels via `level_up_preview`, slots spent with the long rest = a new story day (lazy, no migration). One Venice run under dnd-rules.v3 wrote no tags at all ($0.0093): measure v2 against v3 over several runs before relying on live fights | `combat-depth-001` |
| Branching: past state is NOT rebuildable from what was stored (state rows are updated in place, items/routes are deleted, snapshots keep only versions), so each turn keeps a checkpoint from 0058 on; older turns are refused. Capture p50 14 ms a turn, 10.8 KB (7.6 KB stored) flat over 300 turns; salience kept only at day ends (it was 63 KB a turn at turn 300) | `story-branches-001` |
| Retention: newest 200 turns + each older day's last turn (a 320-turn, 6-person story keeps 212 checkpoints, 1.5 MB stored instead of 1.9 MB, and past turn 200 each day adds one checkpoint instead of ten; prune ~5 ms, checkpoint step p50 16 ms either way). Going back saves the discarded future as a branch first, in the same transaction, and never deletes picture files | `rewind-001` |

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
