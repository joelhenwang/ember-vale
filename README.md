# Ember Vale — main menu (Vue 3 + TypeScript)

Pixel-faithful recreation of the game's home screen: the "current story"
hero card, the *Begin a new tale* launcher, the library summary, and the
*Recent stories* list — parchment palette, Garamond type, ornamental SVG
decor (compass rose, storyteller's desk, mountain ridge).

## Run

```bash
npm install
npm run dev          # vite, binds 0.0.0.0:5173
npm run typecheck    # vue-tsc --noEmit (strict)
npm run lint         # eslint (flat config; vue essential + TS rules; Prettier owns format)
npm run format       # prettier --write src
npm run test         # vitest run — pure game-logic specs (filters, drafts, image registry)
npm run build        # typecheck + production bundle
```

## Routes (vue-router, history mode)

| Path | View | Notes |
| --- | --- | --- |
| `/` | `HomeView` | main menu — current story, begin a tale, library summary, recent stories |
| `/new-story` | `NewStoryView` | wizard band (6-step stepper), cast picker with live search/filter/sort, selected-cast panel, footer nav; state lives in `src/game/catalog.ts` (`wizard`) |
| `/library` | `LibraryView` | internal tabs via `?tab=` — `characters` (default), `worlds`, `style-packs`, `templates`; search, chip filters, sort, grid/list toggle |
| `/stories` | `StoriesView` | “Your stories” shelf — status chips (All / In progress / Archived), search, sort, grid/list density, one `StoryCard` per saved tale with working Archive/Restore; unwired sub-routes (…/configuration, …/saves) fall to `StubView` |
| `/settings` | `SettingsView` | “Settings” — vertical section nav (SettingsNav); AI connections fully wired (provider/model/endpoint/credential, fake connection tests + capability panel); other sections show honest placeholders; SaveBar dirty/discard/save like the studios |
| `/library/character/:id` · `/new-story/character/:id` | `CharacterStudioView` | “Give {name} a voice” — drives/voice form cards; preview column is the separate `CharacterPreviewPanel` (Appearance / Voice / Behavior tabs, full-body render swap, dialogue sampling) |
| `/library/world/:id` · `/new-story/world/:id` | `WorldStudioView` | “Shape your world” — look fields, per-place editors with tabs; preview panel with Scene / Map / Summary, condition selects, preview regeneration |
| `*` | `StubView` | “chapter still being written” placeholder for unwired pages |

The home page's *New Story* / *Quick Start* buttons route to `/new-story`;
*Open Library* routes to `/library?tab=characters`. Studio routes carry typed
route meta (`RouteMeta` augmentation in `src/router.ts`): `title` for the
document title and `from` (`'library' | 'new-story'`) which drives the studio
breadcrumb and where *Finish* returns.

## Architecture notes

- `src/game/model.ts` — typed domain model (story beats, catalog records,
  image slots). The UI only consumes this shape.
- `src/game/state.ts` — `reactive()` menu state; today it's mock data, in
  production it hydrates from the story engine (LLM narrator + state
  tracker) on boot and after every beat. Library counts on the home card are
  **derived from `catalog` lengths** (`LibraryCard.vue`) so no number can go
  stale on its own.
- `src/game/catalog.ts` — the creative archive plus the New Story wizard and
  Library UI state (`wizard`, `libraryUi`). All seed data `satisfies` the
  model types.
- `src/game/filters.ts` — pure search/category/chip/sort helpers used by both
  the cast picker and the Library tabs. Kept Vue-free and unit-tested.
- `src/game/studio.ts` — draft store for both studios. `ensureCharDraft/
  ensureWorldDraft` seed per-id, `saveX` snapshots JSON, `isXDirty` diffs
  against the snapshot (that's what the ● Unsaved changes indicators read).
  Also home to the mock copy pools — `wrenBeats`, `worldSample`,
  `suggestCharacter`/`suggestWorld`, chip vocabularies — so views stay
  composition-only and the fake assistant behaviour is testable.
- `src/game/images.ts` — **image registry.** Components never import image
  files; they resolve a slot to a reactive URL. Two ways to read it:
  - `useGameImage(slot)` → a `ComputedRef` for a component's own lifetime
    (live art slots, story-room backdrops);
  - `resolveImage(slot)` → plain reactive read for use *inside* computed
    maps / loops (avatars in lists, the studio previews). Never call
    `useGameImage()` inside a computed — it creates a throwaway ref per run.

  Until the art pipeline calls `setGeneratedImage(slot, url)`, the
  hand-authored placeholders in `public/images/` are served — so the menu
  always renders complete, and swapping to dynamically generated art is a
  single integration point:

  ```
  narrator emits scene state
    → prompt composer (style pack + lore + beat)
    → image model → cache by story+day hash
    → setGeneratedImage(slot, url)   // every card updates reactively
  ```

- `src/game/stories.ts` — the saved-story shelf (`storyShelf` records + `storiesUi`
  toolbar state). `filters.filterStories` does the search/chip/sort work;
  `setStoryArchived` is the one mutation the page exposes today.
- `src/game/settings.ts` — per-section settings state with the same
  snapshot-based dirty/save/discard cycle as the studios, plus pure
  `applyConnectionTest` / `setProvider` transitions (the timers around them
  are DEMO fakes in the view).

- Shared atoms that grew out of these pages — reuse before re-writing:
  `ui/PageIntro` (emblem + title + sub + actions slot), `ui/SaveBar`
  (dirty status + ghost action + start/end slots; all editing pages use it,
  including both studios), `ui/ViewToggle` (generic grid/list switch, used by
  Library and Stories), `ui/ChipGroup` (now with optional per-chip icons),
  `ui/StatusPill`, `settings/FieldRow` + `settings/ConnectionCard`
  (display:contents grid rows), `stories/StoryCard`.

- Decorative art (compass rose, desk illustration, ridge) is hand-drawn
  inline SVG (`src/components/decor/`) — no external requests, fonts are
  bundled via `@fontsource`.

## Conventions for studio pages

- **One style source:** shared chrome (crumbs, `.card`, preview tabs,
  `.cta`/`.ghost`, footer bar) lives in `src/styles/studio.css` — global, no
  scoping. Views must not redeclare those classes; components may add a
  clearly-commented *override* only when a mockup genuinely differs (see the
  three overrides in `CharacterPreviewPanel`).
- **Self-contained preview column:** `CharacterPreviewPanel` reads the draft
  from the route itself — no props — so both studio origins render identical
  panels and the view stays a thin form shell.
- **`// DEMO:`** marks fake infrastructure: the 900/800 ms render timers,
  the `?v=Date.now()` cache-bust of placeholder art, and the cosmetic
  InlineStepper (advancing just increments a ref; production routes each
  step and validates). Grep for `DEMO:` to find every stand-in.
- Clickable cards expose `role="button"` + `tabindex="0"` and handle both
  Enter and Space; studio preview panes are proper `role="tab"` /
  `role="tabpanel"` widgets with `aria-controls`/`aria-labelledby`.

## Tests (`npm run test`)

`src/game/*.spec.ts` — vitest, node environment: filter/sort purity
(library, cast, stories shelf), draft seed → edit → save → dirty cycle,
suggest-only-fills-blanks, wren/generic beat variant cycling, the image
registry fallback/override, settings save/discard + connection-test +
provider/model coupling transitions.

## Placeholders shipped in `public/images/`

| File | Used by |
| --- | --- |
| `hero-ember-vale.webp` | hero cover (current story) |
| `story-ashes.webp` / `story-lantern.webp` | recent story cards |
| `avatar-lyria.webp` | top-bar profile |
| `hearth-background.webp` / `market-background.webp` | registered scene slots (`scene.hearth`, `scene.market`) for story-room backdrops |
| `character-*.webp` | cast portraits (Wren & Ash from the provided art, Lyria cropped from the mockup, Miri/Thomas/Nessa as sample image-model renders) |
| `character-wren-fullbody.webp` | the Character studio full-body render slot (`character.wren.fullbody`) |
| `world-ember-vale.webp` / `world-silverleaf.webp` | world-card art |
| `library-banner.webp` | Library page banner strip |
