# perf-frontend-001: frontend performance (load, idle CPU, memory, long stories)

**Question.** After the animation push (e91d555…f53af21), what does the built app cost to
load and to leave open, and what can be cut without changing how it looks or behaves?

**Setup.** Production build served by `vite preview` on 5181 (it now proxies `/api` like the
dev server), dev API on 8101 with the dev database. Edge via playwright-core, viewport
1366×820, a fresh browser context per run (cold cache), median of 3 runs.
`scripts/page-bench.mjs` measures, per page:
- **load:** FCP, LCP, CLS, bytes and requests;
- **script:** long tasks and TBT in the first 5 s;
- **heap:** JS heap after a forced GC, DOM nodes, listeners;
- **idle cost:** 10 s with nothing touched. Main-thread busy % is CDP `TaskDuration`. CPU % covers the whole browser, all processes, so compositor and GPU work counts; 100 % = one core.
- **frame pacing:** measured in a separate 3 s window.

`--rested` waits past the app's 60 s rest first. `--memory N` walks the app in place N
times. `data/composite.mjs` lists, from a Chromium trace, which animations failed to
run on the compositor and why. `data/anim-cost.mjs` pauses animations by name to
attribute cost. The machine refreshes at ~100 Hz.

Motion = Full unless stated (the user's choice; reduced motion was already ~0 % idle).

## What was wrong

1. **Paint loops on the main thread.** Seven infinite loops animated `box-shadow` or `color`
   (`ev-breathe` ×8 sites, `wm-pulse`, `pm-glow`, `nsv-pulse`, `pmap-ring`/`wmap-ring`,
   `recent-twinkle`). A single non-composited loop keeps the main thread restyling and
   repainting at the refresh rate. Home spent 24 % of the main thread and over a second
   of style recalculation per 10 s doing nothing.
2. **Loops that started while invisible never reached the compositor.** A loop that starts
   while its page or list is still fading in (opacity 0) is judged "no visible change"
   (Chromium failure reason 131072) and stays on the main thread. Pausing and playing it
   again moved it. This was 13–19 % of the main thread on Adventure and Watch.
3. **Two transform animations on one element** (failure reason 64):
   - the map pin's drop-in and its quest-marker bob;
   - the Library banner's entrance and its pan.
4. **Any running loop keeps the compositor drawing every frame.** That is 25–35 % of a core
   on this machine even when every loop is composited. The logo glow ran forever on every
   page.
5. **Long stories read oldest-first.** Adventure and Watch read the chronicle 50 events a
   page, 20 pages a poll. A 9,000-event story needed ~9 polls (180 requests) before the
   newest turn appeared. The logs also rendered every line, and every older page arriving
   scrolled the reader to the bottom.
6. **Smaller items:**
   - **Fonts:** 82 `@font-face` rules: unused EB Garamond, plus Cyrillic, Greek and Vietnamese subsets.
   - **Pictures:** card pictures were not lazy, and the main picture had no fetch priority.
   - **Polling:** the Adventure poll kept running in hidden tabs.
   - **Bundle:** one 129 kB entry mixed Vue with the app.

## What changed

- **Breathing rings:** every one is now a ring on a pseudo-element that animates only
  transform and opacity (`ev-ring`; `.ev-breathe` keeps its name). The sparkle's colour
  change is a compositable filter.
- **Re-check after entrances (`installRecomposite`):** when an entrance animation or
  transition ends, the running infinite loops inside it are paused and played in place
  (no visible jump).
- **Transform conflicts:** the pin's bob moves to a wrapper span, and the Library
  entrance fills `backwards` only.
- **Rest (`installRest`, `src/game/motion.ts`):** after 60 s without input, ambient loops
  pause. Any input wakes them. Progress indicators never rest: an allowlist of ambient
  names is in `isAmbient`, and a new decorative loop joins by name.
- **Logo and page-heading glows:** they breathe three times when a page opens, and
  continuously while the logo is hovered.
- **Chronicle (`composables/chronicleReader.ts`, shared by Adventure and Watch):**
  - A tiny probe reads the watermark, then the newest 100 events load.
  - Older pages fill in behind, newest first, 50 ms apart.
  - Short stories reuse the probe's page.
- **Log windows:**
  - Adventure draws the newest 300 lines and Watch the newest 120 beats. Scrolling to the
    edge (or the button) draws more.
  - The log follows only the newest line, so backfill never moves the reader.
  - Backfilled lines appear at once instead of unfolding one by one.
- **Small fixes:**
  - **Fonts:** Latin and Latin Extended subsets only; EB Garamond removed. It was declared
    but never drawn: Libron and Cormorant are bundled.
  - **Pictures:** `FramedImage` loads lazily unless `priority`. The Home hero and the
    Adventure moment get `fetchpriority="high"`, and pictures get `decoding="async"`.
  - **Code:** Home prefetches the Adventure code when idle.
  - **Polling:** the Adventure poll stops while the tab is hidden; returning catches up.
  - **Maps:** the map remembers each picture's aspect ratio (asset ids are immutable), so
    pins do not jump on later visits.
  - **Bundle:** a `vendor` chunk holds Vue and the router. The dev server ignores docs,
    backend and evidence; a bench writing JSON had crashed it.
  - **EmberField:** steers its own animations when it scrolls out of view.

## Results

### Idle cost: 10 s untouched, full motion (median of 3)

| page | main thread before → after | style recalc ms/10 s | browser CPU before → after | after the 60 s rest |
|---|---|---|---|---|
| Home | 23.6 % → 0.4 % | 1026 → 5 | 105 % → 45 % | 0.1 % |
| Stories | 0.2 % → 0.3 % | 0 → 1 | 33 % → 26 % | – |
| Library | 17.5 % → 0.3 % | 604 → 3 | 73 % → 30 % | 0.1 %¹ |
| New story | 19.4 % → 0.3 % | 596 → 3 | 80 % → 43 % | – |
| Character studio | 9.2 % → 0.2 % | 230 → 1 | 52 % → 24 %² | – |
| Adventure | 19.7 % → 0.5 % | 652 → 6 | 86 % → 39 % | 0.1 % |
| Watch | 12.6 % → 0.3 % | 321 → 3 | 66 % → 37 % | 0.4 % |
| Settings | 0.2 % → 0.2 % | 0 → 1 | 31 % → 25 %² | 0.3 % |

¹ The intermediate run, `data/after-rested.json`.
² The glows' three breaths are still running inside the 10 s window; afterwards these pages
have no loop at all.

Reduced motion was already ~0–1 % everywhere and still is (`data/final-reduced.json`).
The remaining 25–45 % with full motion is the compositor drawing the composited loops at
~100 fps. It is now cheap per frame, and it stops after a minute of nobody touching the
page.

### Load (median of 3, cold cache)

| page | LCP before → after (ms) | CLS before → after | KB |
|---|---|---|---|
| Home | 2440 → 1840 | 0.001 → 0.002 | 4154 → 4247³ |
| Stories | 2380 → 1464 | 0.029 → 0.029 | 5691 → 5746 |
| Library | 600 → 472 | 0.021 → 0.021 | 3780 → 3840 |
| Adventure | 2040 → 1572 | 0.002 → 0.002 | 3158 → 3246 |
| Watch | 2480 → 2444 | 0.082 → 0.002⁴ | 5277 → 5354 |

³ Bytes rise a little: Home now prefetches the Adventure code (~90 kB) when idle.
⁴ Watch's shift came from the map picture arriving late; it varies run to run. Fresh
contexts have no remembered ratio, so the cache helps only repeat visits. Sending the
dimensions from the API fixes the first visit (below).

LCP moves are partly noise at n=3. The fetch priority and lazy cards help. **The weight is
the API pictures** (see "Left for the backend").

### Bundle

| | before | after |
|---|---|---|
| entry JS | 129.1 kB (49.9 gz) | 22.7 kB (8.8 gz) + vendor 107.5 kB (41.8 gz, cached across releases) |
| main CSS | 62.4 kB (11.4 gz), 82 `@font-face` | 37.4 kB (8.6 gz), 16 `@font-face` |

### Memory: 30 laps of in-place navigation over 8 pages

| | heap after GC | DOM nodes | listeners |
|---|---|---|---|
| before | 6.5 MB, flat | 2560–2744 | 332–355 |
| intermediate (rest added) | 7.4 MB, **growing** | 2748 → **4057** | 361 → **429** |
| after (fixed) | 7.1 MB | 2775, flat | 364, flat |

The intermediate leak: the rest kept paused animations, and with them detached
elements, when pages were left while resting (the walk sends no input). It now prunes
disconnected targets.

### Long stories

Spec `useAdventure.spec.ts` uses a 1,000-event fake:
- **First requests:** `[0, 1]` (the probe), then `[900, 100]`. The newest entry is shown
  after 2 requests.
- **Backfill:** fills to all 1,000.

For 9,000 events, before: up to 180 requests over ~9 polls before the newest turn.

## Left for the backend (not frontend files)

1. **Sized pictures (largest load cost).**
   - `/api/v1/assets/{id}` serves the stored original. A 1360×768 1.6 MB PNG is shown at
     191×108 on Home; Stories moves 5.7 MB, Watch 5.3 MB.
   - 391 portraits and 366 backgrounds are still PNG.
   - Suggested: `?w=` with a few fixed widths (e.g. 256/512/1024), WebP, cached on disk;
     then `srcset` in `FramedImage`.
2. **Cache headers.** Asset responses carry no `Cache-Control`. Asset ids are versioned, so
   `public, max-age=31536000, immutable` is safe. The same applies to hashed `/assets/*`
   in whatever serves the built app.
3. **Map dimensions.** Add the map asset's `width`/`height` to `MapManifestView`. They are
   already in `asset_record`, and the box could be sized on first paint.
4. **Chronicle.** Not strictly needed, since the probe uses `watermark`. Optionally:
   - `GET /world/chronicle?latest=N` returning the newest N *visible* entries (one request
     instead of two);
   - a `before=<seq>` to page older visible entries. A player's 100-event page can hold
     few visible lines.
5. **Polling.** Adventure re-reads presentation, chronicle, narration, character, items
   and suggestions every 12 s (≈35 requests a minute and a half while idle). The
   presentation `revision` is documented as bumped by every canonical write, but only the
   phase projection bumps `world.version`, so it cannot be trusted to skip reads. An
   ETag/304 on these reads would make idle polls nearly free.

## Not done, on purpose

- **Font preload.** FCP is ~70 ms and fonts swap; preloading would compete with the LCP
  picture for the sake of a 0.002 CLS (nav text).
- **`content-visibility` on log lines.** Paint containment would clip speech bubbles and
  entrance motion. The line windows bound the DOM instead.
- **`wm-flow` / `wmap-halo` / `wmap-march`.** They animate SVG strokes, which are
  main-thread, but only on sea lanes and in the map editor while drawing. They rest after
  60 s like the rest.
