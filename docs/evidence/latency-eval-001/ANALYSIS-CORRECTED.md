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
most of which also pass. Arm B lost 2 the same way; arm C stands at
2/10 first-try, 3/10 including its retained repair. Provider-error items
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
`beats_valid` (speaker-to-source disabled), and the assistant editorial
ratings (not a human-user playtest) stand as presentation preferences
(misvoiced instructions, repeated actions from duplicated input facts).
Citation correctness alone does not make good narration.

## Speaker-to-source re-score (offline, production check enabled)

Authoritative mappings built read-only per item: `reaction:<id>` from
committed reactions; `attempt:<family>` from the scene's attempts joined
to intents, accepted only where one actor owns the family. Missing
mappings: none — every family is single-actor, every reaction key
resolved, and attempt actor equals intent author on all 352 rows checked.
(`attributed-rescore.json`, `speaker-map.json`.)

Attributed attempt-0: A 3/10, B 6/10, C 2/10, D1 0/10, E 6/10. Nemo's
9d6fe343 falls (speaker does not match the mapped author); the other six
survive. Note the production gap this exposes: assembly facts carry no
speaker, so production `beats_valid` checks reaction keys only — attempt
attribution is verified here but unenforced in the pipeline.

## Semantic review of nemo's seven attempt-0 passes

Six of seven voice unquoted attempt-topics as direct speech, against the
identified-utterance contract (paraphrase-only): 34a6cdf2, 937f1568 and
9d6fe343 quote the stalls instruction verbatim; 1d6cdf95, 96ba807f and
e2787b12 quote unquoted questions. All seven double beats from duplicated
input facts ("repeats her question", "tries again", "waits again").
703d2583 is the most faithful (attempts narrated as attempts; the genuine
reaction dialogue correct). Structural acceptance, even attributed, does
not establish gameplay suitability.

## Arm F: current pipeline + nemo (integration, paid)

Deduped narrator prompts (line-dedup proven equal to pipeline assembly
output: one attempt per family per scene on all 10 items), current system
template, nemo at temp 0.2, same repair policy, production validation
(schema plus `beats_valid` with reaction-key speakers, attempts unchecked
as in production). Model and sampling fixed; the variable is the pipeline.

- Passed 8/10 under production validation; 2 exhausted (invented
  compound keys on old-format items). Attempt-0 7/10, one converted by
  repair. Under the stricter offline attempt-speaker lens: 5/10.
- Terminal p50 8.5s / p90 16.1s; validated p50 8.0s (n=8).
  Zero provider errors, zero reasoning-only.
- 17,648 tokens, missing=0, est. $0.0004 of the $0.50 envelope.
  20-call limit, 14 calls used; stall abort never fired.
- Repeated-action beats are gone from passing outputs (one wait plus one
  communicate where the fixture carried two of each). The remaining
  semantic gap is unchanged: unquoted instruction topics still voiced as
  direct speech (e.g. 34a6cdf2). That is a prompt/contract problem, not
  a latency or attribution one.
