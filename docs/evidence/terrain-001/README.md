# Terrain grid: can a vision model read a map's terrain?

`backend/scripts/terrain_eval.py` asks a model to lay a 24 × 16 grid over each of the five maps in `map-detect-001/maps` and name what mostly covers each cell, using nine letters:

| Letter | Terrain | Letter | Terrain | Letter | Terrain |
| --- | --- | --- | --- | --- | --- |
| w | water | p | plains | f | forest |
| h | hills | m | mountains | s | marsh |
| d | desert | i | snow | t | town |

The prompt is `TERRAIN_PROMPT` in `infrastructure/geography/openrouter.py`, sent with low reasoning. Raw answers are in `runs/`. `overlays/<model>/` draws each answer over its map so it can be judged by eye. There is no hand-made ground truth, so the judgement below is visual.

| Model | Time per map | Cost per map | What it got right and wrong |
| --- | --- | --- | --- |
| openai/gpt-6-luna | 9–14 s | ~$0.0008 | Broad strokes (sea, mountain ranges, big forests), but towns land off-target, and on map 4 every island (Hollow Isle, Blackreef, Ixquel) is plain water. |
| **google/gemini-3.8-flash** | 6–28 s | $0.002–0.015 | Best overall: towns sit on their drawings (Corvane, Saltmarket, Pell, the Ixquel temple, the map-3 castle and camp) and islands are land. On map 1 it spreads the mountains over the Warden's Gate and Brindle plains. |
| anthropic/claude-sonnet-5.5 | 5–6 s | ~$0.008 | Sensible kinds, but the whole grid is shifted down and to the left. |

**Decision:**
- **Default model:** `WORLDSIM_MAPS__TERRAIN_MODEL` defaults to Gemini 3.8 Flash.
- **Readings are drafts:** no model is reliable enough to use unchecked, so a reading is a first draft and the map page has a brush to correct it.

**How terrain is used:**
- **Weighting roads:** a road's drawn length is weighed by what it crosses. Plains, towns and water count once. Forest counts 1.4×, desert 1.5×, hills 1.6×, marsh and snow 2×, and mountains 2.6×. Sea and river routes are not weighed.
- **Travel times:** the shortest and longest road anchors then spread travel times over the weighed lengths, as before (`effort_length`, `timed_roads` in `domain/geography.py`; mirrored in `src/game/terrain.ts`).

**Live check on The Saltreach** (`saltreach-terrain-painted.png`):
- **Reading:** 5 s, $0.0017.
- **Correction:** a band of mountains painted with the 3 × 3 brush.
- **Saving:** the grid was saved with the map.
