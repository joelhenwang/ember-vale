# Pinned-budget comparison: 512 vs 4096 (bounded experiment)

Same model (`deepseek/deepseek-v4-flash-0731`), same sampling (temperature 0.2,
no top_p/top_k), same prompts, same 5-step scenario; only the transmitted
`max_tokens` differs via explicit story pins: rev9 (512) vs rev10 (4096) on the
live connection. Four advances plus reads per arm; browser skipped (display was
not in this experiment's question list). A higher budget remains an experiment,
not an established remedy.

## Per-arm results

| | 512 (rev9) | 4096 (rev10) |
|---|---|---|
| Advances committed | 4/4 | 2/4 |
| Retrieval complete | 4/4 | 2/2 of committed |
| Provider-ok advances | 0/4 | 1/4 (travel) |
| Narration | fallback x4 | fallback x2 (of committed) |
| NPC answers (Ash) | no-answer x2 | **answered x1** (question), follow-up unjudged (timeout) |
| Answer usefulness | unevaluated | unevaluated |
| Beat walls | 29.2s, 52.4s, 66.5s, 35.3s | 45.9s, 112.5s, >180s timeout (unresolved), no 4th attempt (blocked) |
| Tokens prompt+completion(+reasoning) | 8577+1583(1536); 10361+1991(1951); 13980+2560(2686); 6184+3095(2990) | 6120+4794(4560); 10368+8471(8177); timeout; n/a |

## Provider outcomes (exported failure layer, not inferred)

- 512: every failure is `malformed` / `finish_reason: length` /
  `reasoning_only: true`, reasoning 511-578 tokens against the 512 cap.
  Reasoning exhaustion, identical to the legacy unpinned run — the explicit
  pin changed nothing at the same budget.
- 4096: character, reaction, and resolver calls succeed (travel fully ok).
  The question-beat narrator still fails `length`/`reasoning_only` with 3834
  reasoning tokens: the bigger budget moved the exhaustion point but did not
  eliminate it. Read this arm as **two confirmed commits, one unresolved
  timed-out advance, and one subsequent rejected advance** (recorded under the
  older schema without the resolution field; the follow-up's clock equality
  does not establish its commit state). The follow-up exceeded the 180s client
  timeout with phase 3 left open (`scenes_assembled`, read-only status
  confirmed); the timeout alone does not establish a permanently wedged story
  or its cause — the open phase warrants investigation, and ordinary-user
  recovery is the next question, not another budget increase. Under corrected
  harness semantics the follow-up would halt the scenario with the fourth
  advance preserved as blocked instead of attempted into 409s.

## Committed NPC answer (4096 question beat)

Wren's intent (`communicate`, "What did the market bell mean at dawn?") ->
Ash's decision `wait` -> Ash's committed **reaction** `communicate` addressed
to Wren ("The dawn bell means the fish auction is starting.") -> model
resolver (`resolver: model`, rationale cites the communication) -> fallback
narration that voices Ash's answer verbatim with Ash as speaker (citation
`c89ca52b`). This is the WAIT-decision-plus-reaction path the harness now
traces; an intent-only check would have reported it absent, and the reaction
qualified only because its target is Wren.

## Narration source, latency, tokens

- Narration is fallback in all 6 committed beats across both arms; no
  model-authored beats anywhere. The 4096 answer above reaches the player only
  through a structured fallback beat citing the committed reaction.
- Latency roughly doubles to triples at 4096 for comparable beats (question
  112.5s vs 52.4s), and the follow-up never finished within 180s. Token spend
  roughly triples (question: ~10k+8.5k(+8.2k reasoning) vs ~10k+2k(+2k)).
- Verdict: 4096 buys real decisions and one real NPC answer, but narration
  still reasoning-exhausts, tails blow past the beat timeout, and one stuck
  phase wedged its story (open run `6d35e38b`, phase 3 `scenes_assembled`,
  read-only status confirmed; no resume attempted — outside this harness).

## Files

- `baseline-live-mugqwo6j.json`: 512 arm (4/4 committed).
- `baseline-live-mugr0yw9.json`: 4096 arm (2 confirmed commits, 1 unresolved
  timed-out advance, 1 subsequent rejected advance; `complete: true` means the
  scenario finished, not that all beats committed — read the arm description
  above, not the legacy `commit_ambiguous: false`).
- Pins: rev9 `e5b2cc62` (512), rev10 `0e02a2fb` (4096), same model and sampling.
