# scene-spots-live-001: does the storyteller set scenes at a place's spots?

**Setup.** Dev stack, storyteller on Venice (`venice-uncensored-1-2`). Story "Inside Corvane"
(6ae66386) from "Ember Vale copy": Corvane has its own map (the storybook village,
19 kept spots); for this test Saltmarket was given the same map in the story's
`place_maps` config. Ash and Wren start in Corvane. Beats run through autoplay (Step x3
per round), the chronicle read back with `spot_key`.

| round | storyteller fact | scenes with the spot list | scenes naming a spot |
| --- | --- | --- | --- |
| 1 | "…If the scene happens at one of them, name it" | 2 | 0 |
| 2 | "…Set the scene at the one spot that fits what happens, and name it in the first beat" | 3 | 2 ("At the Hearth…", "At Old Bram's farm…") |
| 3 | round 2 + "They were last at X: keep the scene there unless what happens moves them" | 3 | 2 ("At Old Bram's farm, where Wren had earlier…", "at the Market square in Saltmarket…") |

- Optional wording is ignored; asking for the spot in the first beat works most of the
  time. The scene that named none is left where the people last were (server hint and
  story-watch map both look back past unnamed scenes in the same place).
- The matcher (`spot_named`) read every named spot, curly apostrophe in "Old Bram’s farm"
  included, and no false hits.
- Without the "last at" hint the pair hopped from the Hearth to the farm between beats; with
  it the next scene referred back to where they had been.
- Story-watch: inside Saltmarket both stood at the Market square, as the scene said.

**Cost.** 12 beats, 113 model calls (all roles), 439k prompt and 19k completion tokens on
Venice; no OpenRouter spend (balance unchanged at $9.53).

**Not measured.** Other storyteller models (DeepSeek on OpenRouter), longer runs, whether
named spots ever contradict the action (e.g. a fight "at the Chapel").
