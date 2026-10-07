# place-spots-001: reading the spots inside one place

**Question.** Can the places model (GPT-6 Luna, low reasoning) read a closer picture of one
place (a village) and list the spots where a person could be, well enough to pin characters
on it?

**Picture.** `../map-detect-001/maps/map-5.png`, the user's painted storybook village
(1672x941), with its hand-marked truth in `../map-detect-001/truth.json` (10 labelled
places, 4 extras).

**Prompt.** `SPOTS_PROMPT` in `backend/src/worldsim/infrastructure/geography/openrouter.py`
as shipped. Script: a scratch runner calling `OpenRouterMapReader.spots` and writing
`runs/luna-N.json`.

| run | seconds | cost | spots | labelled found | buildings' pin offset |
| --- | --- | --- | --- | --- | --- |
| luna-1 | 10.2 | $0.0006 | 18 | 9/10 | 0.7–2.2 % |
| luna-2 | 9.5 | $0.0003 | 16 | 9/10 | 0.7–4.3 % |

- Both runs miss the small stone cairn on the hilltop; nothing is invented.
- Both add real unlabelled spots: graveyard, garden, stone bridge, river; run 1 splits the
  village houses into four, run 2 lists one "Village houses" and the farm's barn.
- Areas (road, wood, track) sit 1–8 % off, as in map-detect-001: their centre is a matter of
  taste.

**Verdict.** Good enough to ship: the spots a story needs (inn, market, chapel, smithy,
mill, farm) come back named and placed every time, for well under a tenth of a cent. The
player can untick, rename, drag or add spots before saving.
