# Playtests 003–005 — making characters travel together

Same setup as 001/002 (Wren and Ash at the Hearth, DeepSeek V4 Flash,
reasoning off, 10 live beats each, scripted presence). ≈ $0.02 per run.

| Run | Code | Move attempts → applied | Ending | Finding |
| --- | --- | --- | --- | --- |
| 003 | fa1c687 (meet-up rule) | 14 → 1 | apart | **Autonomous moves almost never applied:** decisions name a destination but no route id, and a routeless move resolves as impossible. 002's "swaps" were failed moves narrated as movement. Fixed in ccf4fe7 (server fills the route). |
| 004 | ccf4fe7 | 8 → 7 | apart | Moves land and they travel together (beat 3), then drift: an arrived character kept "moving" on a stale intention ("keep walking to the Market") along the only route — back. Observations said only "Wren moves". Fixed in 84ad4d0 ("You are at Market. From here you can travel to…"; "Wren goes to Market"; act on the intention once there). |
| 005 | 84ad4d0 | 2 → 2 | **together** | Travel together in beat 3, stay together, coherent plan (split the stalls, meet at the fountain bell). Intentions: Wren "Browse the market stalls with Ash…", Ash "Stay at the fountain bell to keep our meet-up". |

## What 005 shows next

- **Nothing to act on.** Beats 7–10 are "Ready to browse the stalls?" on
  repeat: stalls, stallkeepers, ledgers and lockets exist only in prose.
  There is no action to browse, buy, examine or talk to anyone else, and
  director hooks name people who do not exist (`spawn_npc` is never used).
- **Director JSON shape drift** (3 repairs): `"type": "json_object"`, the
  action under `type`, payload under `proposal`/`hook`. Normalized after
  this run.
- Narration of solitary movement is thin; pronouns still vary.
