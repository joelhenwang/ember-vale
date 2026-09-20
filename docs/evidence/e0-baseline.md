# E0 baseline — Ember Vale (main @ ab9161c)

Date: 2026-09-20. Checkout: `main...origin/main`, clean except untracked `docs/`.
Frontend gates on this checkout (after `npm install`): `vue-tsc --noEmit` pass,
`eslint .` pass, `vitest run` 37/37 pass (6 files).

## Routes (from src/router.ts + README)

- `/` HomeView — current story, begin-a-tale, library summary, recent stories.
- `/new-story` NewStoryView — currently cast-picker only (step 2 of 6-step
  visual stepper); Save draft is a local 1.4s `saved` flag flip, Continue routes
  to dead `/play-mode`.
- `/library` LibraryView + `?tab=` characters/worlds/style-packs/templates.
- `/stories` StoriesView — shelf from in-memory `storyShelf`; Archive/Restore works.
- `/settings` SettingsView — AI connections wired to fake tests; generation,
  appearance, storage, advanced are honest placeholders.
- Studio entries `/library/character/:id`, `/new-story/character/:id`,
  `/library/world/:id`, `/new-story/world/:id` — real form shells on in-memory drafts.
- `*` StubView placeholder.

Dead/unwired: `/play-mode` (NewStory Continue target, no route → StubView),
`/stories/.../configuration`, `/stories/.../saves` (documented StubView fallbacks).
No gameplay routes exist yet: no `/stories/:storyId/play|adventure|world`.

## DEMO fakes (grep `DEMO:`)

- `SettingsView.vue:95-97` — 700ms timer then `applyConnectionTest` (endpoint
  non-empty ⇒ reachable; image caps flip to supported). No network.
- `settings.ts:89-91` — snapshot lags one edit so page opens dirty by design.
- `settings.ts:138-142 generateTestImage` — cache-busts placeholder via
  `setGeneratedImage('world.map', url + '?t=...')`.
- `CharacterPreviewPanel.vue:70-79` — 900ms timer then cache-busts
  `character.wren.fullbody` placeholder, sets `appearanceSaved`.
- `CharacterPreviewPanel.vue:122-127` — 800ms timer then cycles canned voice beat.
- `WorldStudioView.vue:147` — fake render latency + cache-busted placeholder URL.
- `WorldStudioView.vue:90`, `CharacterStudioView.vue:56` — cosmetic steppers.
- `NewStoryView.vue:40-45` — Save draft only flips a flag.
- `studio.ts` canned pools: `wrenBeats`, `genericBeat`, `suggestCharacter`,
  `suggestWorld`, `worldSample`, `defaultTraits` — all narrator stand-ins.
- `state.ts`, `catalog.ts`, `stories.ts` — fully in-memory fixtures; nothing persists.

## Contaminated / placeholder art (public/images)

`images.ts` notes placeholders mix concept art, mockup crops, and sample renders.
Concrete issues: `world.map` slot reuses `hero-ember-vale.webp` (a hero cover, not a
map); test-image flow cache-busts whatever is registered (`?t=`); full-body panel
stretches `character.wren.fullbody` placeholder via CSS cover. Per references/README,
never crop UI screenshots into production portraits/covers. Targeted fix only —
no page redesign (deferred to E7 asset audit).

## Reference backend pin (read-only assessment)

PixelSaga @ `653614d` (branch `feat/ember-vale-integration`; plan pinned
`785713d`). Coherent Python/FastAPI/SQLAlchemy/Alembic/Postgres engine:
`backend/src/worldsim/{domain,application,infrastructure,interfaces}`,
32 Alembic migrations (through `0031_settings_pipeline`), versioned prompts in
`backend/prompts`, `content/{seeds,definitions,dnd,schemas,visual-styles}`,
`compose.yaml` (pgvector pg16 + api + web). Requires Python `>=3.12,<3.13`
(local toolchain is 3.14.7 → Docker is the expected runner).

Reuse decision: vendor the backend as one coherent subsystem
(`backend/`, `content/`, `compose.yaml` paths adapted, isolated DB/volume) and
adapt API projections to Ember Vale. Do NOT import its frontend, CSS, router, App,
AGENTS.md, or static-mock approval process. Known gaps to verify during E1/E2:
seeded travel routes, preset→instance projection coverage, live text/image provider
config, revision-1 hardcoding in its old frontend (not imported).

## What E0 does NOT claim

No screenshots captured in this pass (no browser harness wired yet — E2 will add
deterministic-context captures at 1440×900 / 1920×1080 / mobile + 200% zoom).
No backend runs yet. No UI changed.
