# fights-deepseek-001: fights on the default model

## Question

Every live fight run so far used Venice (the dev `.env`'s playtest model). The documented default is
`deepseek/deepseek-v4-flash-0731` through OpenRouter. Does deepseek tag fights, do played and watched
adventures play out, and does anything break?

## Setup

The dev API was switched to the OpenRouter profile for these runs with a compose override
(`WORLDSIM_PROVIDER__ACTIVE_PROFILE=openrouter`), then switched back to Venice. It ran main plus the
talk-loop, one-encounter-per-kind and rest-cap changes (`9a7a7b0`).

- `long_run.py`: long-adventure-002's 26-turn plan. Wren is a human fighter who invites Ash, then seeks
  goblins twice.
- `watched_run.py`: watched-party-001's watched adventure, 14 turns.

## Results

| run | turns | fights | outcome |
|---|---|---|---|
| played, first try (`played-500.json`) | 14 | 1 (2 goblins, turn 7) | **500 at turn 14** (a rest): "projection left bounds: stamina=103" |
| played (`played.json`), after the fix | 26, no errors | **2, both when sought**: 2 goblins at turn 7, 3 at turn 17 | 5 goblins fell, a scimitar was left; both heroes at level 2 with 700 XP |
| watched (`watched.json`) | 14 | **2, opened by the storyteller itself** (goblins at turns 4 and 8, before the trouble rule's turn 6) | both reached level 3; actions: 11 attempts, 9 talk, 8 moves, 7 looks, 3 waits, 2 pickups |

- Deepseek tags fights where Venice did not. The watched party never needed the engine's trouble rule.
- Deepseek also acts more: watched-party-001's Venice runs were mostly talk and waiting.
- Turn time was a median of 18.6 s for the played run and 17.0 s for the watched one, as measured by the
  script (it plays the next turn as soon as one returns, so it also waits on the previous turn's words
  and dice).
- Ability checks rolled on deepseek too. For example, "I look around the Hearth and listen" rolled
  Perception 3 against 12 and failed; "I search the area" rolled 20 and succeeded.

## Bug found and fixed

- **What failed:** a rest plus a +stamina effect from the resolver in the same scene summed to 103.
  Projection raised an invariant error and the turn failed with a 500.
- **The fix:** recovery now stops at the cap (`apply_character_effect`, matching `restore`). A cost below
  0 still raises, and a stale plan is still a version conflict.
- **Tests:** `test_a_gain_past_the_cap_stops_at_it`, and `test_a_plan_from_an_older_row_is_a_version_conflict_not_out_of_bounds`
  now uses a stale cost.

## Verdict

Fights work on the default model, and better than on Venice: they open when sought, and on their own in
watched stories.

## Spend

OpenRouter usage went from $9.7765 to $10.2624: **$0.486** for all three runs, including the run the 500
stopped. The game's own records put the runs at $0.168, $0.146 and $0.158; the rest is picture captions
and callings.
