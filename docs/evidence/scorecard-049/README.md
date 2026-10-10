# Story scorecard scorecard-049

Commit `54dfb96`, model `venice-uncensored-1-2`, 12 beats per scenario, run 2026-10-10T12:21:18+00:00. Estimated spend $0.263.

| Scenario | Goal | Beats | s/beat | Repairs | Repeats | Moves done/tried | Talk streak | Idle streak | Settled | ~$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strangers | PASS: repeated questions 8% (pass ≤ 20%) | 9 | 13 | 0/72 | 8% | 3/3 | 5 | 0 | 0/2 | 0.071 |
| strangers error | stopped before beat 10: spend cap reached | | | | | | | | | |
| stuck_task | PASS: 8 successful physical attempt(s) | 9 | 14 | 0/112 | 33% | 2/3 | 1 | 0 | 1/2 | 0.124 |
| stuck_task error | stopped before beat 10: spend cap reached | | | | | | | | | |
| meet_up | PASS: Wren at Market, Ash at Market | 12 | 9 | 2/73 | 12% | 1/1 | 4 | 3 | 0/1 | 0.068 |

Full numbers (action mix, repairs by role, hooks, final places, items) in `results.json`.

## Question

Baseline for talk loops on Venice (the dev `.env`'s playtest model), before `9a7a7b0`. In
watched-party-001 the repeat guard caught "asking the townsfolk about the empty stalls" every turn,
but the retry said it again and the second answer stood.

Note: the $0.25 cap stopped strangers and stuck_task after 9 turns. scorecard-050 runs 9 turns, so the
two compare like for like.

## Spend

Estimated $0.263 on Venice.
