# Key moments: pictures of what mattered, and a Home built around them

**Question:** can Home lead with the story's latest key moment (your mockup: the world fading into "A bell beneath the tide")? Scene pictures already existed (d483c4b), but they had three problems:
- **Mechanical choices:** only an arrival, a first meeting or a settled rumour was painted. A discovery never was.
- **Mechanical captions:** "Mara Vell arrives at Oarfall Harbor."
- **Posed figures:** people stood and posed. The picture was queued as soon as the turn committed, before the narration it should paint had been written.

## What changed

- **Queued after the narration, behind the turn.** The turn returns as fast as before.
- **A small writing model reads the turn.** It uses the library writer, `openai/gpt-6-luna`, with `MOMENT_PROMPT` in `application/pictures.py`. It returns:
  - **worth:** 0 (nothing happens) to 3 (a turning point: a discovery, a confrontation, a reveal);
  - **a headline;**
  - **a one-line caption;**
  - **a painter's sentence:** who does what, holding what, in what light.
- **Worth 3 is painted as a `turning` moment.** It leads, and it skips the three-turn wait, as a settled rumour already did.
- **Worth 2 is painted after the fixed moments** (settled rumour, then arrival, then first meeting), within the wait.
- **The judge's words go into every picture of that turn,** so it gets the headline and caption, and the painter shows an action.
- **Studio appearances read as one phrase for the painter.** "17-year-old human female, lean and wiry, dark brown hair in a wind-tangled braid, sea-gray eyes, wearing …" replaces the packed "age: 17 Race: Human Sex: …" lines, which were cut mid-word.
- **Home** (`HeroCard.vue`):
  - The world picture fades into the latest painted moment.
  - Portrait, story, "Last time" and Continue sit beside "Latest key moment", which opens the moment view.
  - Recent stories end with "Start a new story".
  - The "Begin a tale" and "Your library" side cards are gone.
- **Moment view** (`MomentDialog.vue`):
  - The picture sits beside the scene's narration, with spoken lines next to the speaker's face.
  - Previous and Next (or the arrow keys) step through every painted moment.
  - On a phone, the picture stacks above the text.

## Live check (The Bells of the Saltreach, Venice storyteller, Krea on the home GPU)

| Turn | Player | Judge | Result |
| --- | --- | --- | --- |
| 9 | "Wade into the low tide beneath Lowbell Tower and dig at the green metal showing through the sand" | worth 3, $0.000105 | Painted: **"Green Beneath the Sand"**, "Mara Vell digs into the low-tide sand and uncovers green metal." Painter's sentence: "Mara Vell kneels in wet sand, scraping it away with her fingers to reveal a green metal surface. Pale light glints on the exposed metal and shallow water." |
| 10 | "Pull the half-buried bell free and wipe the barnacles from its face to read the markings" | worth 2, $0.000102 | Not painted: one turn after a picture, inside the three-turn wait (by design). |

The picture (`2-home-1920.png`, `5-moment-view.png`) shows her kneeling and digging, where the earlier two were standing poses. Pictures painted before this change get a headline from their kind ("A new arrival", "A first meeting").

Screenshots:
- **Home:** `1-` (before the live turn, an older arrival picture), `2-` (1920), `3-` (1366), `4-` (phone).
- **Moment view:** `5-` (1920) and `6-` (phone).

None of the three widths scrolls sideways.

## Spend

| Service | Spend |
| --- | --- |
| OpenRouter, moment judge | $0.0002 for two turns (10.6099 → 10.6101 of $20) |
| Venice, storyteller | $0.0078 of bundled credits (0.1654 → 0.1577; the $5 balance untouched) |
| Krea | free (home GPU), about 15 s per picture |

## Not done

- **Watchers' screens:** the Observatory's event modal still shows only the world map. It could open the same moment view.
- **First visit:** there is no onboarding. You asked for one later, not now.
- **Tuning:** the threshold of worth 2 or 3 and the three-turn wait are untuned. Revisit them after a longer play session.
