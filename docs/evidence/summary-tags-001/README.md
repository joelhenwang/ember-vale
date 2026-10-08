# summary-tags-001: day-end summaries, live check of the cap and the citation format (2026-10-08)

**Question.** `perf-llm-001` found 9 of 71 day-end summaries cut off at the 1,024-token cap, and
the cap was raised to 1,536 (`9845502`). Does a live day-end now finish, and why were
summaries so long?

**Verdict.** The raise was needed: both live summaries ran past 1,024 tokens. The real cause,
though, was the citation format: about 70% of each summary's output was the model echoing
~30 full source ids. One of the two summaries fell back to "A quiet account…" because the model
dropped the `obs:`/`mem:` prefixes and the citations failed validation.

`summary.v2` and `digest.v2` (`dba0198`) show sources as short tags (`[o1]`, `[m2]`) that code
maps back to full ids. A copied full id or bare uuid is still accepted. Output fell 82%,
prompts 58%, there were no fallbacks, and stored citations stay full ids.

## Setup

- Scorecard `strangers` (Wren and Ash), 11 beats to cross the first day-end (10 phases a day),
  on Venice `venice-uncensored-1-2`, where 8 of the 12 earlier cut-offs happened.
- Before: scorecard-034, `summary.v1` with the 1,536 cap. After: scorecard-035, `summary.v2`.

## Results

| Day-end summary | v1 (034) | v2 (035) |
|---|---|---|
| Output tokens | 1,054 / 1,075 | **214 / 178** |
| Prompt tokens | 1,452 / 1,493 | **605 / 655** |
| Latency | 5.0 / 5.2 s | 2.3 / 4.0 s |
| Finish reason | stop / stop (both past the old 1,024 cap) | stop / stop |
| Fallbacks | **1 of 2** (prefixes dropped) | 0 of 2 |
| Sources cited (stored as full ids) | — | 29 / 18 |

The scorecard runs themselves passed in both cases: 18% then 0% repeated questions. Spend was
Venice $0.071 + $0.058, matching the account balance ($4.981 → $4.851, which also covers
$0.002 of other use).

The scorecard counted summaries under the wrong role name (`summary`; the trace role is
`daily_summary`); fixed in `dba0198`.
