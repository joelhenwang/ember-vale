# Story scorecard scorecard-050

Commit `54dfb96`, model `venice-uncensored-1-2`, 9 beats per scenario, run 2026-10-10T12:23:27+00:00. Estimated spend $0.192.

| Scenario | Goal | Beats | s/beat | Repairs | Repeats | Moves done/tried | Talk streak | Idle streak | Settled | ~$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strangers | PASS: repeated questions 0% (pass ≤ 20%) | 9 | 10 | 1/58 | 0% | 3/7 | 3 | 0 | 0/1 | 0.054 |
| stuck_task | PASS: 9 successful physical attempt(s) | 9 | 11 | 4/99 | 0% | 6/6 | 0 | 0 | 0/1 | 0.094 |
| meet_up | PASS: Wren at Market, Ash at Market | 9 | 8 | 1/48 | 0% | 1/2 | 2 | 3 | 0/1 | 0.044 |

Full numbers (action mix, repairs by role, hooks, final places, items) in `results.json`.

## Question

Do talk loops break once a repeat that survives its retry goes unsaid, and once the retry says plainly
not to talk this turn when the same matter came up twice before? Same scenarios, model and length (9
turns) as scorecard-049.

## Compared with scorecard-049

| Scenario | repeated lines before → after | talk streak | goal |
|---|---|---|---|
| strangers | 8% → **0%** | 5 → 3 | pass both |
| stuck_task | 33% → **0%** | 1 → 0 | pass both (8 → 9 successful attempts) |
| meet_up | 12% → **0%** | 4 → 2 | pass both |

## Verdict

The loops break on Venice, with no goal lost. These are single runs, so it is a strong signal rather
than a settled number. Deepseek already scored 0% repeats (scorecard-048).

## Spend

Estimated $0.192 on Venice. Venice went from $2.4587 to $2.0026 for both scorecards ($0.456).
