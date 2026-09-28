# Provider comparison: Venice @1024 vs deepseek @4096 (schema-3 rerun)

Same fixed scenario (travel → question → follow-up → ordinary watcher
advance → reload reads), same sampling (temperature 0.2, no top_p/top_k),
same harness (`scripts/reliability-baseline.mjs`, schema 3, `--no-browser`).
Only the pinned profile differs:

- Venice arm: connection `venice` (OpenAI-compatible transport at the
  Venice endpoint, credential `VENICEAI_API_KEY`), profile rev2,
  `olafangensan-glm-4.7-flash-heretic`, `max_tokens` 1024.
- Deepseek arm: connection `Live deepseek low-temp`, profile rev10,
  `deepseek/deepseek-v4-flash-0731`, `max_tokens` 4096 (fresh rerun of the
  recorded 4096 arm under the current schema).

No budget was raised for this comparison: 1024 sits between the 512
exhaustion point and the 4096 experiment.

## Per-arm results

| | Venice @1024 | Deepseek @4096 rerun |
|---|---|---|
| Advances committed | 4/4 | 2/4 (follow-up 180s timeout unresolved, 4th blocked by the halt rule) |
| Retrieval complete | 4/4 | 2/2 of committed |
| Provider calls ok | 2/14 (both director, ordinary beat) | 6/8 (director x2, character x2, reaction, resolver) |
| Committed NPC answers | 0 | **1** (question: Ash answers Wren via committed reaction) |
| Model-authored narration | 0 beats | 0 beats (fallback everywhere) |
| Beat waits | 26s, 49s, 45s, 29s | 164s, 110s, >180s timeout |
| Tokens prompt+completion(+reasoning) | 8.6k+3.1k(0); 14.0k+4.1k(0); 14.1k+4.1k(0); 10.4k+3.9k(0) | 6.1k+8.5k(8.5k); 10.4k+6.3k(6.3k); timeout |

## Why Venice fails

Every Venice call burns its whole completion budget and returns empty
`content` with `finish_reason: length` and `reasoning_tokens: 0`. A direct
envelope probe shows why: the model thinks in `reasoning_content`
(DeepSeek-R1/Venice convention — e.g. a 5-word greeting spends all 64
tokens thinking and returns nothing), which the gateway taxonomy did not
recognize. `reasoning_effort: low` was tried and does not stop the
thinking; `thinking`/`include_reasoning` are rejected as unrecognized
keys. So Venice @1024 is fallback-only with 26–49s waits: faster than
deepseek, delivering nothing.

Two follow-ups landed from this finding (no budget change):

- `_has_reasoning` now recognizes `reasoning_content`, so the exported
  failure layer reports these as reasoning exhaustion
  (`reasoning_only: true`) instead of reasoning-less malformed with zero
  reasoning tokens. Covered in `backend/tests/test_model_diag.py`.
- Venice stays unwired for sessions: it needs a thinking control the
  provider does not offer before it can compete.

## Selection

**Deepseek @4096 (rev10) is the session configuration.** It is the only
arm delivering real NPC content (decisions plus a traced Ash answer).
Caveats, stated plainly: narration is still fallback in every beat, waits
run 110–164s per beat with tails past the 180s beat timeout (a 10-beat
session means ~20–30 minutes of waiting), and one wedged follow-up was
halted rather than forced. Venice is not promoted: a fallback-only
session with shorter waits is still a fallback-only session.

## Files

- `baseline-live-mul4ne64.json`: Venice arm (4/4 committed, no answers).
- `baseline-live-mul4sr6e.json`: deepseek rerun
  (2 committed, 1 unresolved timeout, 1 blocked; `complete: true` means
  the scenario finished, not that all beats committed).
- Pins: Venice profile `853ddde0` rev2 (1024); deepseek profile
  `0e02a2fb` rev10 (4096), same model and sampling as the recorded arm.
