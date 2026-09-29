# Narrator re-score with corrected evaluator (offline, $0)

Two parser defects falsely rejected retained responses: the audience line's
sentence period stuck to the final UUID, and the older `- key:` fact format
produced an empty allowed-key set. Fixed in `parse_narration_context`
(`backend/src/worldsim/application/graphs/narrate.py`), covered by four
regression tests on exact fixture excerpts in `test_narration_graph.py`.

Per-item validation metadata (`fixture.meta.json`: audience, keys, budget)
was generated with the fixed parser and verified read-only against the
database — every audience matches its scene's participants and every key is
covered by that event's observation facts or committed reactions (10/10).
Scoring uses that metadata, never model outputs. Original result files,
fixture, and ANALYSIS.md are untouched; detail per item is in
`corrected-narrator.json`.

## Corrected narrator acceptance (attempt-0 vs repair)

| arm | recorded passed | attempt-0 pass | repair pass | union |
|---|---|---|---|---|
| A deepseek t0.2 | 2/10 | 3/10 | 0/0 | 3/10 |
| B GLM t0.2 | 4/10 | 6/10 | 1/1 | 6/10 |
| C deepseek t0.0 | 2/10 | 2/10 | 1/1 | 3/10 |
| D1 JSON mode | 0/10 | 0/10 | 0/1 | 0/10 |
| E nemo t0.2 | 2/10 | 7/10 | 6/9 | 7/10 |

False denials destroyed real passes: arm E rejected 5 of 7 first-try
passes (bad audience IDs, empty key sets), then spent unnecessary repairs —
most of which also pass. Arm B lost 2 the same way. Provider-error items
(`attempt0: null`, reasoning-only with no text) are unaffected by this
correction; D1's zero stands.

## Observed call latency (separate from acceptance)

Attempt-0 call latency p50: A 96.2s, B 60.7s, C 79.8s, D1 46.5s,
E 6.7s. Repair call latency p50 (where repairs returned text):
B 74.2s, C 94.4s, D1 25.0s, E 5.2s. Repairs prompted by erroneous
denials were unnecessary interventions, so no untouched-counterfactual
time-to-valid-output is reconstructed; treat the union column as
observed-with-intervention, not first-try performance.

## Reading (narrow, as instructed)

Nineteen arm-E calls returned nonempty text without recorded provider
errors or reasoning-only failures, at substantially lower observed
latency. Under corrected checks E passes 7/10 first-try against
A 3/10, B 6/10, C 3/10, D1 0/10 — but gameplay suitability remains
unproven: corrected acceptance is still schema plus unattributed
`beats_valid` (speaker-to-source disabled), and the user's ballot notes
stand (misvoiced instructions, repeated actions from duplicated input
facts). Citation correctness alone does not make good narration.
