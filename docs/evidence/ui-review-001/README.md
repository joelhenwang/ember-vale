# UI review of 7 Oct 2026: what changed and how it was checked

This answers `docs/reviews/7_oct_2026-user-review.md`. The screenshots were taken with headless Edge against the dev stack (vite on 5180, API on 8101). The scripts that took them are in `scripts/`.

## Look and feel (d3a47e0)

- **Fonts.**
  - Reading text uses **Libron** (OFL), bundled in `src/assets/fonts/libron` so it works offline.
  - Short text (navigation, tabs, buttons, labels, chips) uses **Alegreya Sans**.
  - Large titles keep Cormorant Garamond.
- **Accent, shadows and motion.**
  - A warm *ember* accent marks active and hover states.
  - Card shadows are deeper, and cards you can open lift on hover.
  - Page content rises into place when a page opens.
- **Page caching.** Home, Stories, Library and Settings stay alive between visits. Coming back shows them at once and refreshes quietly, and the preset shelf is cached and shared. Measured: the loading line never appeared when returning to Home or Library.
- **Carousel transition.** Moving between the main pages slides in nav order (see `after-slide-mid-transition.png`).
- **Buttons.**
  - Buttons are padded inside.
  - The arrow is now a drawn arrow, and on hover a fresh one slides in as the old one flies out.
  - Teal buttons show a sheen on hover (`after-button-hover.png`).
- **Cards / List toggle.** The selected view never showed because of a CSS specificity bug. It is now a segmented control with a sliding marker and labels.
- **Subtexts.** The motto and the three filler notes on Home are gone.
- **Library.**
  - The banner picture fades into the paper on its left.
  - The Create button and the "From X to story" side rail are removed.
  - The tabs sit on top of the shelf they open, with a full-width sliding marker.
  - The shelf reaches the bottom of the window.
  - The `…` menus work: Open in the studio, Draw the map, Make a copy, and Archive with Undo. Built-in presets can't be archived.
  - Every "Create" tile is one button.
- **New story.**
  - The step fills the window, and the actions sit at its foot.
  - The draft state moved to the left, with a coloured dot.
  - Hints and place lists are readable sizes, and button text is padded.

## Character studio (be5d3ac)

The studio now has five working steps:
1. **Overview:** name, pronouns, and your own overview.
2. **Appearance:** age, race, sex, hair, eyes, height, body and extra, plus **Generate image** or **Import image**.
3. **Background & personality.**
4. **Voice.**
5. **Review:** what they wear and carry and how they are, then **Create character** or **Publish changes**.

There are no breadcrumbs, no picture card at the top, and no Publication box. The preview shows the real character.

**Writing help** uses `POST /library/writing/enhance` and `/fill` on a small OpenRouter text model (default `openai/gpt-6-luna`, configured with `WORLDSIM_WRITING__*`).
- *Improve my overview* shows a fuller version next to yours, and nothing changes until you choose it.
- *Fill the empty fields* only writes into empty fields, and marks them until you edit them.

**Generate image** uses `POST /library/portraits/paint` (Krea, in the house style). The face is found and framed automatically, and *Adjust the framing* is still available.

All the new fields are packed into the existing `appearance`, `personality` and `background` text, so stories receive them with no engine change. Library cards show the overview.

Live run ("Tamsin Reed", not kept):

| Step | Result |
| --- | --- |
| Improve overview | 3.5 s |
| Fill | 23 fields in 6.0 s, $0.0003 |
| Paint | 22.9 s |

In a second browser run I created a test character, reopened it with its fields intact, and archived it from the card menu.

## World studio (a4065f7)

The studio now has four working steps:
1. **Overview:** the name, and your overview, which is the world's description.
2. **The world:** terrain, climate, architecture, peoples, history, distinctive details, and what the world never contains.
3. **Places:** the helper can add *n* places from the overview (each with a type from the studio's list and a road to the first place), and describe places that have no text yet.
4. **Review:** where stories start, then Create or Publish.

The preview has three tabs:
- **World:** paint the world as a map, or import a picture. It becomes the banner the cards show. Once the world exists, this tab also shows its drawn map and a link to pin places.
- **Place:** paint or import a picture for each place. It becomes that place's own map.
- **Summary.**

Live run, "The Saltreach" (kept in the dev library, archive it from its card menu if you don't want it):

| Step | Result |
| --- | --- |
| Fill | 6 fields and 3 new places in 6.1 s, $0.0003 |
| Map picture | 15.9 s |
| Place picture | 15.8 s each |
| Publish after the place pictures | Revision 4 kept both place pictures, the cover and the edit |

## Fixes found along the way

- **Publishing could drop maps.** Publishing a world merged the editor draft over the revision it opened on. A map or place picture saved after that was lost on the next publish. Maps now come from the newest revision. Covered by `test_a_place_picture_saved_while_the_editor_is_open_survives_its_publish`.
- **Stalled drafts.** A studio whose earlier draft sat on an older revision stalled on a conflict. It now resumes that draft, and editor errors show on every step.
- **Duplicate place ids.** Places added in the same millisecond shared an id.

## Spend

OpenRouter usage went from $10.517044677 to $10.518251727 of $20: **$0.0012** for this whole round. Krea is free.
