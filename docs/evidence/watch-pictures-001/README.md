# watch-pictures-001: pictures in the Watch screen (2026-10-08)

**Question.** The Watch screen's event view showed only the world map ("No illustration for this scene yet"), even though the presentation already sends watchers every scene picture. Key moments are painted only for player stories, so a watched story usually had no pictures at all.

**What changed (frontend only; the backend already let watchers paint and see pictures):**
- **The event view** (`EventModal.vue`) shows the scene's picture when it has a ready one, captioned with the moment's headline. "See the moment" opens `MomentDialog`, the same view as Home and Adventure, with Previous/Next and prompt editing.
- **While a picture paints**, the view says "This scene is being painted…" over the map.
- **Without a picture**, it keeps the map and its honest caption and offers "Paint this scene" (`PaintSceneDialog`, as in Adventure).
- **The event feed** (`EventFeed.vue`) marks entries whose scene has a picture with a small picture icon.

**Checked live** (`watch-paint.mjs`, headless Edge against the dev API with Krea running locally; no paid calls):
1. The event view showed the map, the caption and "Paint this scene" (`1-event-no-picture.png`).
2. The paint dialog opened with the suggested prompt (`2-paint-dialog.png`), and Paint queued the picture (`3-after-paint.png`).
3. Reopened, the event said it was being painted (`4-event-painting.png`).
4. The picture was ready about 23 s later and shows in the event view (`5-event-with-picture.png`).
5. "See the moment" opened the moment view (`6-moment-view.png`).
6. The feed marks the painted scene (`7-feed-mark.png`, `feed-shot.mjs`).

There were no console errors.

**Not changed:** watched stories still get no automatic key moments. Those are chosen from a player's point of view (the first meeting, an arrival, the player's own turning point). Painting a watched story is left to the watcher, one scene at a time.
