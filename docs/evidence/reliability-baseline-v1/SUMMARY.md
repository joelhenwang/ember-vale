# Reliability and beat-latency baseline v1

Fixed small scenario, normal configuration, frozen prompts/models/budgets/retries.
Question: how often does a player receive a useful response, and how long do they wait?

## Corrected reading (schema 2)

The schema-1 headline "5/5 useful" overstated what was measured and is withdrawn.
The supported findings are reported on separate lines:

- Four advances committed (4/4 fake, 4/4 live).
- API retrieval checks passed: every committed event re-readable from the
  timeline with non-empty narration text (all-events requirement, not merely one).
- Narration used fallback in all 8 committed advances, fake and live.
- Live browser display was **not measured successfully** (dev server down during
  the live run; retained as an error row). Read-only room rendering was measured
  on a fake story: 1769ms initial render, 908ms reload render — combined display
  cost, not isolated rendering time.
- Answer usefulness remains **unevaluated**: HTTP 200 is reported as validation
  'accepted', never as gameplay success; nothing here establishes an answered
  question or accepted model output.

Schema-1 files below are kept as evidence and labeled legacy: the follow-up beat
was player-as-Ash authoring the answer itself (a second player-authored
communication, not an NPC response), the browser pass committed an extra beat
outside the stated cap, `useful` counted reload as a fifth beat and display
rested on a some-events check, and `admission_ms` measured the execution-slot
claim. Schema-2 files use the corrected scenario (Wren stays controlled and asks
twice; Ash's committed answer is traced, never authored) and corrected labels.

## Failure layer (exported, not inferred)

The stored live failures carry `finish_reason: "length"` with
`reasoning_only: true`, `content_type: "NoneType"`, and reasoning-token usage up
to 558 against the 512-token cap: the model spent the whole budget on reasoning
and returned no content. This is reasoning exhaustion rejected at extraction —
not truncated JSON reaching validation. The model-runs view now exports
`finish_reason`, `reasoning_tokens`, content type/length, and `reasoning_only`
per call so the distinction is measurable (covered in
`backend/tests/test_reliability_audit.py`).

Narrowed provider claim: three live calls did succeed (director x1,
character_decision x2 in the follow-up/ordinary beats). Committed-source tracing
shows the committed intents were Wren's player-authored `communicate` attempts
plus fallback `wait` decisions; narration was fallback in every scene. So the
accurate statement is: no live beat carries model-authored narration, and the
succeeded provider calls are not traced to accepted NPC content — not that the
provider contributed nothing anywhere.

## Method (schema 2)

- Harness: `scripts/reliability-baseline.mjs` (schema 2). Capped at exactly four
  advances plus reads; the read-only browser pass never commits, so the live cap
  holds exactly. Every beat checkpoints to disk immediately; the final report is
  written in a `finally` block. Transport failures distinguish timeout,
  connection, and other transport errors.
- Scenario: travel (Wren Hearth -> Market) -> question (Wren asks Ash) ->
  follow-up (Wren asks again; Ash's answer traced via committed scene intents) ->
  ordinary watcher advance -> reload reads (not counted, never 'useful').
- Fake mode pins to a throwaway `fake-echo` profile (deterministic: identical
  layer outcomes across runs). Live mode uses the environment default untouched:
  `openrouter / deepseek-v4-flash-0731`. `--pin-profile/--pin-revision` pins
  either mode to an explicit revision for a future pinned-budget comparison
  with sampling otherwise unchanged.
- Read-only observability only: per-call latency, error code, finish reason,
  reasoning tokens, content type/length, reasoning-only flag, retry attempts,
  manifest budgets, transmitted `max_tokens`, pin revision;
  `X-Worldsim-Slot-Claim-Ms` (execution-slot wait, not run admission) plus
  `X-Worldsim-Execution-Ms` on advance.
- Small sample: individual beat timings and min/max ranges; no tail percentiles.

## Timings (ms, individual beats)

Schema-2 fake advances (wall / slot-claim / execution):
536/23/502, 441/14/407, 433/9/415, 363/11/336 (second run: 382/11/348,
339/24/304, 405/11/379, 386/19/359).
Schema-1 live advances (unchanged raw data, relabeled): 17937/10/17914,
51341/10/51321, 41594/9/41576, 17127/9/17105.

Reads stay flat in both modes (timeline 15-44, narration 13-150, reload
124-212). Slot-claim (~10-24ms), reads (<150ms), and display (~0.9-1.8s) are
noise next to live generation (17-51s).

Generation by role, live (each traced call includes its retries; summed
durations double-count concurrent character calls, so wall and sum are apart):

| beat | roles (calls x latency) | tokens prompt+completion(+reasoning) | retries |
|---|---|---|---|
| travel (17.9s) | director 1x3718 failed, character 2x19541 failed | 5675+1536 | 0 |
| question (51.3s) | character/reaction/resolver/narrator 1x each failed (~10-16s) | 10381+2048 | 0 |
| follow-up (41.6s) | character 2x2809 ok, reaction/resolver/narrator failed ~10-15s | 13427+1578 | 0 |
| ordinary (17.1s) | director 1x3015 ok, character 2x16947 failed | 6174+1371 | 0 |

Roles run sequentially behind barriers, so generation sums to the wall. All
failures are `malformed` at the gateway with `finish_reason: length` and
`reasoning_only: true` (see Failure layer).

## Bottleneck and one proposed experiment

**Bottleneck: model generation, specifically reasoning-budget exhaustion.**
Live calls burn the full 512-token budget on reasoning, return no content, fail
`malformed` (never retried by policy), and every role falls back. The wait
(17-51s/beat) buys no model-authored narration; the three succeeded calls are
not traced to accepted NPC content.

**Proposed experiment (not an established fix): compare explicit pinned budgets
512 versus 4096** with the same model, prompts, sampling, scenario, and bounded
call count (`--pin-profile/--pin-revision` support is in the harness). Earlier
4096-token runs still showed reasoning exhaustion, so raising the cap may only
buy latency and tokens. Measure whether accepted NPC answers (Ash's committed
`communicate` intents answering Wren, narrated beats) improve enough to justify
the cost.

## Files

- Schema 2 (corrected): `baseline-fake-mugq5pe2.json`, `baseline-fake-mugq68rx.json`
  (determinism pair, browser skipped), `baseline-fake-mugq6qil.json` (read-only
  browser pass measured: room-render 1769, reload 908; still exactly 4 advances).
- Schema 3 (persistence-first attempts, reaction tracing): `baseline-fake-mugqv4hh.json`.
- Schema 4 (schema 3 plus: unresolved-transport resolution with halt/blocked
  steps, narration-failure-proof source tracing, `reaction:{id}` citation
  matching): `baseline-fake-mugse6ih.json` (4/4 committed, 0 blocked, answers
  no-answer with narration retrieval complete).
- Schema 4 with the shared halt-then-finalize driver (`runPlannedScenario`,
  covered by the travel/question/timeout scenario test):
  `baseline-fake-mugsswpd.json` (4/4 committed, 0 blocked; finalization runs
  even on the happy path).
- Schema 4 with blocked-steps persisted before finalization and skeleton-first
  reload (`onBlocked`, per-read reload errors): `baseline-fake-mugt5wp3.json`
  (4/4 committed, 0 blocked).
- Schema 4 with single-append blocked steps (`onBlocked` is the only append
  path): `baseline-fake-mugtr3xj.json` (4/4 committed, 0 blocked).
- Schema 1 (legacy, superseded semantics but retained): `baseline-fake-mugcisle.json`
  (setup probe with seat 403s), `baseline-fake-mugcjgeb.json`,
  `baseline-fake-mugcjo6c.json` (determinism pair, Ash-seat follow-up),
  `baseline-fake-mugcprbi.json` (committing browser pass),
  `baseline-live-mugclwxu.json` (capped live sample, 4 advances + reads; browser
  error retained; follow-up was Ash-authored).
- `browser-room-fake.png`: room render during a display pass.
- Harness: `scripts/reliability-baseline.mjs`. Maintained tests:
  `backend/tests/test_reliability_audit.py` (6 passed; neighbors green, 242/242
  vitest, typecheck clean).
- Tree note: baselines ran with the read-only observability patch applied
  (slot-claim headers + model-runs attribution fields, rebuilt into the compose
  API); prompts, models, budgets, and retry behavior unchanged.
