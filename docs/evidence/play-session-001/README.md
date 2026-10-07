# Play session: a studio-made character in a studio-made world

I made Mara Vell in the new character studio:
- **Overview:** written by hand.
- **Empty fields:** the 23 empty fields were filled for $0.0003.
- **Portrait:** painted by Krea.

I then started "The Bells of the Saltreach" in The Saltreach through the New Story wizard, playing as Mara with Ash in the cast. I played eight turns on the live storyteller (Venice, `venice-uncensored-1-2`): five actions or lines and three waits. `turns.json` has every turn's text and timing, and `scripts/` has the browser scripts.

## What the session showed, and what was done

| Found | Fix |
| --- | --- |
| The opening printed the studio's packed lines ("Age: 17 Race: Human Sex: Female Hair: …"). | `appearancePlain` turns them into prose (`2-` before, `4-` after). |
| "Carrying: Empty pockets", although she carries her grandmother's brass bell, a tide-knife and more. The narrator even hung "a small brass bell" in the square. | "Carries:" from the studio becomes items she holds when the story starts (`domain/carried.py`). |
| The map panel was a schematic with three places bunched along one edge, labels overlapping. | Places without a drawn map sit evenly on a ring. The map page can use the world's own picture as its map, and the map reader is told the world's place names, so an unlabelled painted map comes back as Mirewake, Oarfall Harbor and Lowbell Tower (`7-`). |
| A band of empty space under the story while the side column ran on (your screenshot). | The side column is as tall as the story and scrolls on its own; the map sits above the rumours. |
| The story room was narrow, with lines cut mid-word ("wearing th"), raw event names ("WORLD TICKED") and a tiny Say box. | Full width with the story beside the controls, whole-word snippets with "…", plain event names ("Time passes", "What happened") and a normal input (`5-`). |
| Story watch: cramped "INSIDE" badges, and the map stopped short of the events column. | Readable badges; the map fills its column (`6-`). |
| A two-statement click handler on the Sex/Height buttons broke the studio build after formatting. Type checks did not catch it. | Moved into a function, fixed in d3ceb25. A full `vite build` is now part of the checks. |

## How the turns felt

Each turn took 5–15 s. Narration often lands a few seconds after the turn ends, and the page replaces "The scene is still being written…" when it arrives. Every action moves time on by one phase, so the eight turns covered one day from sunrise to night. I left that pacing alone.

## Spend

| Service | Spend |
| --- | --- |
| Venice bundled credits | about $0.022 (0.1877 → 0.1654; the $5 balance untouched) |
| OpenRouter, whole round | $0.091 ($10.518 → $10.609 of $20). This includes the terrain model comparison (about $0.07), the writing helper, the map reader and the face finder. |
