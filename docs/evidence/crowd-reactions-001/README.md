# crowd-reactions-001: who answers an attempt in a crowd (2026-10-08)

**Question.** Every person present answered every attempt, so reaction calls grow with the
square of the crowd: about 465 a beat at 25 people (`perf-beat-001`). Does it change the story
if only the person addressed plus two others answer?

**Verdict: adopt.** In a seven-person scene, capping at the addressee plus 2 bystanders cut
billed cost 49% and time per beat 21%. Over three runs each, the scorecard showed no loss:
as many people spoke, no more repeated questions, and conversations followed through.

`WORLDSIM_APP__REACTING_BYSTANDERS` now defaults to 2. Scenes small enough that everyone fits
under the cap are untouched, which covers all the existing 2–3 person scorecard scenarios.
Set the variable to 24 to let everyone react again.

## Setup

- **Code:** `7c78e58`, cap and scenario; `choose_reactors` in `orchestration/stage1.py`.
- **Who answers:** an attempt aimed at someone (talk, spar, hand over, interact with) is
  answered by that person plus K others present. The K are picked by a hash of (attempt, person),
  so the choice is replay-stable and spreads across the crowd.
- **Scenario:** scorecard `crowd`, seven people at the Market with their own wants, 6 beats.
  The goal is at least 4 speakers and at most 20% repeated questions.
- **Model:** OpenRouter `deepseek/deepseek-v4-flash-0731`, reasoning off, throughput routing
  (the production default).
- **Runs:** three uncapped runs (scorecard-036, 038, 040) and three with K = 2 (037, 039, 041),
  run back to back.

## Results

| | Everyone reacts | Addressee + 2 |
|---|---|---|
| Reaction calls | 262 / 253 / 316 (mean 277) | 125 / 111 / 117 (mean 118, **−57%**) |
| All model calls | 336 / 313 / 388 | 192 / 172 / 190 (**−47%**) |
| Billed $ (`model_cost`) | 0.236 / 0.190 / 0.243 (mean 0.223) | 0.125 / 0.103 / 0.113 (mean 0.114, **−49%**) |
| Seconds per beat | 21 / 16 / 21 | 15 / 15 / 16 (**−21%**) |
| People who spoke | 7 / 7 / 9 | 8 / 7 / 8 |
| Repeated questions | 0 / 0 / 0% | 0 / 0 / 4% |
| Repairs (of all calls) | 8/336, 3/313, 7/388 (1.7%) | 5/192, 4/172, 5/190 (2.5%) |
| Scenes with mechanical narration | 0 of 22 | 1 of 20 |

Notes:
- The action mix barely moved (communicate 26 vs 27 in the first pair).
- Repairs fell in number (18 → 14) but rose as a share (1.7% → 2.5%). The reaction calls the cap removes
  rarely need repairs, so the remaining mix leans on resolver and narrator calls, which repair more.
- The one capped scene with mechanical narration came from a narrator call whose repair also
  failed. It did not recur in the other two capped runs, and the uncapped runs also needed
  narrator repairs.
- The "~$" column in the scorecard-036…041 READMEs is a list-price estimate that ran about 2.5x
  under the bill. The billed figures above come from `model_cost` and match OpenRouter's
  usage counter: 7.583 → 8.603, $1.02 for the six runs. The scorecard now reports and guards on
  the billed figure.

**Reading the stories.** In the capped runs, people still answer whoever addressed them. Old
Marg answers Sela's question about who is ailing, Farmer Oda explains her bruised shoulder,
and Brann asks Ash for a hand. Threads also run across beats: the locked chest in run 1, the
fallen cart and apples in run 3. The one continuity slip seen (Wren asking Ash a second time
what brings them) is the 4% repeat, and similar slips appear uncapped.

## Not measured

Crowds bigger than seven, where the saving grows quadratically, and long stories. If a
crowded scene ever feels like people ignore a loud event, raise K before removing the cap.
