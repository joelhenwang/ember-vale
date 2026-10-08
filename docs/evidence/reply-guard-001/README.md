# reply-guard-001: the repeat guard for replies (2026-10-08)

**Question.** Decisions have a repeat guard (`729a04a`): the context lists what the character already asked and heard answered, and a line that repeats an answered question gets one retry. Replies (reactions) had neither. Does adding both to replies matter?

**Verdict: kept, with no measurable effect.** Repeated replies were already rare (about 2%). Most are not re-asked answered questions, which is all the guard catches. It fired once in three runs, and the drop from 2.1% to 1.2% is within noise. Cost and speed did not change measurably. It is kept because it closes a known gap at no measurable cost, not because it improved the scorecard.

## What changed

- `Stage1Orchestrator._react_one` reads the reactor's answered exchanges once per phase (shared, like other per-character reads).
- The context gets the "Already asked and answered" note.
- A reply that repeats an answered question gets one retry with the pointed note. The second reply stands.
- Test: `tests/test_repeat_guard.py::test_a_reply_that_repeats_an_answered_question_gets_one_retry`. It fails without the change.
- **The scorecard** now counts replies too:
  - `replies`: the number of reply lines;
  - `reply_repetition_rate`: replies that repeat one of the speaker's last 3 lines, turns and replies together, with the same overlap measure as `repetition_rate`;
  - `reply_retries`: how often the guard fired.

  `repetition_rate` still counts turns only; it never included replies.

## Setup

- Scorecard `crowd`: seven people at the Market, 6 turns, at most 2 bystanders answering.
- OpenRouter `deepseek/deepseek-v4-flash-0731`, reasoning off.
- Three runs without the guard, from a clean copy of `d3f3da2` via `PYTHONPATH` (scorecard-042…044), then three with it (045…047).

## Results

| | Without (042 / 043 / 044) | With (045 / 046 / 047) |
|---|---|---|
| Replies | 84 / 79 / 76 | 87 / 72 / 80 |
| Repeated replies | 3.6 / 1.3 / 1.3% (mean 2.1%) | 2.3 / 1.4 / 0.0% (mean 1.2%) |
| Guard fired | — | 0 / 1 / 0 |
| Repeated turns | 0 / 0 / 0% | 0 / 0 / 3.6% |
| People who spoke | 8 / 8 / 7 | 8 / 8 / 7 |
| Model calls | 188 / 186 / 170 | 195 / 186 / 181 |
| Billed $ | 0.140 / 0.121 / 0.108 (mean 0.123) | 0.124 / 0.113 / 0.112 (mean 0.116) |
| Seconds per turn | 16.0 / 17.7 / 19.1 | 24.3 / 19.8 / 16.6 |

The 3.6% repeated turns in run 047 come from decisions, which this change does not touch. Spend: OpenRouter usage went from $8.612 to $9.329, so **$0.717 billed** for the six runs. The estimate before starting was about $0.70.
