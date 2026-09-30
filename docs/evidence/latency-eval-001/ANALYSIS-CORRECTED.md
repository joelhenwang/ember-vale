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

## Arm F: historical-prompt dedup experiment (paid, NOT pipeline output)

Arm F removes identical lines from the retained historical prompts; it
does not rebuild prompts through `render_user_prompt()`. Retain it as a
dedup experiment only:

- Five fixtures keep legacy `- attempt:` formatting; today's renderer
  emits `- key "attempt:":`.
- `fa524125` still carries its earlier rejection/repair instruction.
- Line-dedup is false in general: distinct actions can render identical
  text, which production preserves via source IDs. It coincides with
  pipeline output on these 10 items only because each scene holds one
  attempt per family. Future integration fixtures must go through
  production assembly/rendering with source identities preserved.

Corrected counts from `results-F.json` (original records preserved):
attempt-0 passes 6/10; passes after repair 8/10; repair conversions 2
(`703d2583`, `fa524125`); 14 calls used of the 20-call limit; accepted
final outputs also passing the offline attempt-speaker check 5/10, with
`1d6cdf95`, `703d2583`, `fa524125` failing attribution. Terminal p50
8.5s / p90 16.1s; validated p50 8.0s (n=8). Zero provider errors, zero
reasoning-only. 17,648 tokens, missing=0, est. $0.0004 of the $0.50
envelope; stall abort never fired.

Semantic content (beyond keys): `1d6cdf95` assigns Wren's question to
Ash; `703d2583` presents Wren-turns-to-Ash as dialogue spoken by Ash;
accepted `937f1568` invents Ash speaking, an audience leaning in, and a
sudden commotion from attempt/wait facts. Valid citation keys do not
establish that prose follows those facts — this is more than a
quotation-prompt problem, and the remaining work is speech-eligibility
and attribution, not another model comparison.
