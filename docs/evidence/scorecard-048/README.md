# Story scorecard scorecard-048

Commit `2069700`, model `deepseek/deepseek-v4-flash-0731`, 12 beats per scenario, run 2026-10-10T02:23:06+00:00. Estimated spend $0.347.

| Scenario | Goal | Beats | s/beat | Repairs | Repeats | Moves done/tried | Talk streak | Idle streak | Settled | ~$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strangers | PASS: repeated questions 0% (pass ≤ 20%) | 12 | 11 | 0/79 | 0% | 2/2 | 3 | 2 | 0/2 | 0.046 |
| lost_item | PASS: purse held by Ash | 12 | 16 | 2/118 | 0% | 3/3 | 1 | 0 | 0/3 | 0.074 |
| stuck_task | PASS: 3 successful physical attempt(s) | 12 | 18 | 7/193 | 0% | 3/3 | 3 | 0 | 1/3 | 0.125 |
| meet_up | PASS: Wren at Market, Ash at Market | 12 | 13 | 2/113 | 0% | 4/4 | 2 | 1 | 1/3 | 0.071 |
| named_place | PASS: added Old Mill; there at the end: Wren, Ash | 12 | 10 | 2/60 | 0% | 2/4 | 1 | 3 | 0/3 | 0.031 |

Full numbers (action mix, repairs by role, hooks, final places, items) in `results.json`.

## Question

Did the fight work merged in `2069700` (shared code in the turn engine: background dice, `_check_fresh`
version conflicts, companion and fair-fight notes that only reach party scenes) change ordinary
stories without fights? Baseline: scorecard-032 (`729a04a`, the last full five-scenario, 12-turn run).

## Compared with scorecard-032

| Scenario | 032 calls / repairs | 048 calls / repairs | 032 s/turn | 048 s/turn | goal |
|---|---|---|---|---|---|
| strangers | 156 / 4 | 79 / 0 | 18 | 11 | pass both |
| lost_item | 154 / 4 | 118 / 2 | 19 | 16 | pass both |
| stuck_task | 330 / 16 | 193 / 7 | 25 | 18 | pass both (8 → 3 successful attempts) |
| meet_up | 75 / 1 | 113 / 2 | 13 | 13 | pass both |
| named_place | 76 / 4 | 60 / 2 | 13 | 10 | pass both |

- Fewer calls come from the crowd cap (crowd-reactions-001: an attempt is answered by its target plus 2
  others), which landed after 032.
- Repairs fell from 29/791 (3.7%) to 13/563 (2.3%). No failed calls, 0% repeated questions everywhere.
- stuck_task's goal needs one successful physical attempt; 3 is within the spread seen before (it was 8
  in 032, and as low as 2 in earlier runs). named_place tried 4 moves and 2 went through, yet both
  ended at the Old Mill it added.

## Verdict

No regression in ordinary stories. Fight-only code stays out of them.

## Spend

Estimated $0.347; OpenRouter billed $0.356 (usage $9.4061 → $9.7620). The cap was $0.35 on the estimate.
