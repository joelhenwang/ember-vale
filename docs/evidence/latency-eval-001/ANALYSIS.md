# Latency eval 001: replay of captured role requests (2026-09-28)

Frozen fixture `fixture.json` (sha c0c5cb31…, seed 20260928): 41 prompts —
narrator 10 (5 known-hard), director 7, reaction 8, resolver 8,
character_decision 8. One variable changes per arm; user prompt, max_tokens,
and system template are identical across arms for each item.

Qualifications: system prompts regenerated from today's files (narrator and
reaction templates changed 2026-09-24, inside the capture window), so the
baseline is not byte-identical to every historical call. Non-narrator
validation is schema-parse only (their domain validators need live packets);
narrator validation is schema plus `beats_valid` with audience/keys/budget
parsed from the prompt (`fact_speakers` unavailable, attribution check
skipped). Repair policy is one uniform repair call per item.

## Per-arm results (usable / n, TTUV p50)

| role | A deepseek t0.2 | B GLM t0.2 | C deepseek t0.0 | D1 narr JSON mode |
|---|---|---|---|---|
| narrator (10) | 2/10, 120s | 4/10, 81s | 2/10, 63s | 0/10, 74s |
| director (7) | 4/7, 28s | 2/7, 17s | 5/7, 68s | n/a |
| reaction (8) | 4/8, 34s | 1/8, 31s | 3/8, 27s | n/a |
| resolver (8) | 5/8, 28s | 3/8, 71s | 8/8, 43s | n/a |
| decision (8) | 1/8, 25s | 1/8, 10s | 0/8, 19s | n/a |
| total usable | 16/41 | 11/41 | 18/41 | 0/10 |

Failure mode everywhere: reasoning-only output (thinking, no message text).
Zero empty-content failures. Repairs converted 2/41 (A), few elsewhere.

## Arm notes

- B: the approved r2 pin id `olafangensan-glm-4.7-flash-heretic` is rejected
  by the gateway (`not a valid model ID`, $0 spent). Substituted public
  route `z-ai/glm-4.7-flash`, same family. Not better than baseline.
- C: deterministic sampling fixes structured roles (resolver 8/8, director
  5/7) but not narration (2/10) or decisions (0/8).
- D1: JSON response mode makes narrator worse (0/10; 9 reasoning-only,
  1 exhausted). Structured mode itself issues no call: ~0s, $0, quality in
  the ratepack as room-committed beats.

## Cost (estimated vs billed)

Estimated from catalog prices (deepseek $0.021/1M in + $0.32/1M out;
GLM $0.0605/1M + $0.40/1M): A $0.015, B $0.026, C $0.018, D1 $0.005 —
total ≈ $0.064 against the $2 cap. Billed cost: reconcile against the
gateway receipt for 18:14–20:26 local on 2026-09-28 (arm windows in the
result files); the runner writes no model_call rows, so nothing in-app
double-counts. Tripwire (400k tokens/arm) never fired.

## Finding

No tested configuration returns validated narrator output promptly or
reliably. The blocker is upstream: both flash reasoning models spend the
completion budget thinking and return no content, and neither a model swap,
deterministic sampling, nor JSON mode breaks the pattern. The usable-storytelling
default is still unproven; per-role temp-0.0 helps only the structured roles.
Structured (fallback) narration remains the only path at ~0s/$0 — its quality
is the open ballot in `ratepack.md` (key in `ratepack-key.json`).

## Observation (not verified)

Room beats for fixture events contain exact duplicate rows (same kind+text
committed twice for one event), consistent with timeout-late completions
committing narration more than once. Not pursued; needs a dedicated check.
