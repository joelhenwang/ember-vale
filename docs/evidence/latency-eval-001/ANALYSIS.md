# Latency eval 001: replay of captured role requests (2026-09-28, corrected)

Frozen fixture `fixture.json` (sha c0c5cb31…, seed 20260928): 41 prompts —
narrator 10 (5 known-hard), director 7, reaction 8, resolver 8,
character_decision 8. One variable changes per arm; user prompt, max_tokens,
and system template are identical across arms for each item.

## What "passed" means (correction 3)

Results are **passed replay checks**, not "usable". Scope: schema-parse for
all roles; narrator additionally runs `beats_valid` with audience/keys/budget
parsed from the prompt, with `fact_speakers=None`, so the speaker-to-source
attribution check is disabled. Nothing here proves valid execution or useful
behavior. Temperature 0 improved schema-pass counts for structured roles in
this small sample; that is all it showed.

Qualifications: system prompts regenerated from today's files (narrator and
reaction templates changed 2026-09-24, inside the capture window), so the
baseline is not byte-identical to every historical call. Repair policy is one
uniform repair call per item.

## Per-arm results (passed / n; elapsed-to-terminal p50; validated-only p50 (n))

| role | A deepseek t0.2 | B GLM t0.2 | C deepseek t0.0 | D1 narr JSON mode |
|---|---|---|---|---|
| narrator (10) | 2/10; 120s; 83s (2) | 4/10; 81s; 54s (4) | 2/10; 63s; 65s (2) | 0/10; 74s; N/A (0) |
| director (7) | 4/7; 28s; 57s (4) | 2/7; 17s; 45s (2) | 5/7; 68s; 68s (5) | n/a |
| reaction (8) | 4/8; 34s; 43s (4) | 1/8; 31s; 44s (1) | 3/8; 27s; 22s (3) | n/a |
| resolver (8) | 5/8; 28s; 29s (5) | 3/8; 71s; 98s (3) | 8/8; 43s; 43s (8) | n/a |
| decision (8) | 1/8; 25s; 3s (1) | 1/8; 10s; 48s (1) | 0/8; 19s; N/A (0) | n/a |
| totals passed | 16/41 | 11/41 | 18/41 | 0/10 |

Failure detail is mixed, not uniform: reasoning-only output dominates
(empty content with thinking), plus schema/validation failures on repair
exhaustion. Zero empty-content failures without reasoning.

## Arm notes

- B: the approved r2 pin id `olafangensan-glm-4.7-flash-heretic` is rejected
  by the gateway (`not a valid model ID`, $0 spent). Substituted public
  route `z-ai/glm-4.7-flash` — a separate tested configuration, not better
  than baseline overall.
- C: deterministic sampling raised schema-pass counts for resolver (8/8)
  and director (5/7); narrator (2/10) and decisions (0/8) unchanged or worse.
- D1: JSON response mode gave narrator 0/10 (9 reasoning-only, 1 exhausted).
  Structured mode itself issues no call: ~0s, $0; its quality is the
  room-committed side of the ratepack ballot below.

## Cost, corrected (correction 2)

The previously reported **$0.064 total is withdrawn**: failed calls were
costed at zero because gateway-error records kept usage only inside the
truncated diag string. All failed-call usage was recovered offline from the
retained diagnostics (usage_missing = 0 in every row, no paid rerun needed).

Reasoning-token/completion-token overlap is unestablished (observed
reasoning > completion, e.g. 4150 reasoning vs 4096 completion), so cost
covers prompt + completion tokens only; reasoning is reported separately
and never costed or added. The runner tripwire now tracks billable tokens
the same way.

Estimated from catalog prices (deepseek $0.021/1M in + $0.32/1M out;
GLM $0.0605/1M + $0.40/1M): A $0.0295, B $0.0447, C $0.0331, D1 $0.0156 —
total ≈ **$0.123** against the $2 cap. Failed calls are the larger share
(e.g. arm-A narrator: 17.6k ok tokens vs 37.7k failed tokens). Billed cost:
reconcile against the gateway receipt for 18:14–20:26 local on 2026-09-28
(arm windows in the result files); the runner writes no model_call rows.

## Blinded ratings (editorial, not a config ranking)

The pack as built contains 15 samples across 4 items, all arm-A/arm-C or
room-committed: arm-B samples were omitted by a pack-builder defect (cause
undetermined; the extraction verifies cleanly now). Rankings below are
presentation preferences over the presented samples only. Key in
`ratepack-key.json`.

- `1d6cdf95: Z > X > Y` — all three room-committed; top is the spoken
  dialogue beat over two `attempt:`-prefixed narration beats.
- `703d2583: V > X > W > Y > Z` — room > arm-C > room > room > arm-A.
  The last-place arm-A sample voices the attempt ("Ash, one last probe
  question for the road?") as dialogue — the exact misattribution the
  disabled speaker-to-source check cannot catch.
- `96ba807f: Y > Z > X` — all room-committed; dialogue beat on top.
- `9d6fe343: W > Z > X = Y` — room, room above arm-A = arm-C; X/Y repeat
  the instruction as speech and Z quotes it. None adequately presents the
  unanswered request.

A corrected pack including arm-B samples can be built offline on request;
no new paid calls needed.

## Duplicate beats: mechanism (read-only)

Withdrawing the timeout-recovery attribution. For every fixture event, the
duplicate rows carry distinct narration IDs, the same event and scene IDs,
identical kind/text/citations, committed in one ~5ms burst — not a late
second commit. The fixture prompts themselves list each `attempt:` fact
twice: `_perceive_scene` (stage1.py) emits one observation per
(observer, fact), and with two audience members each attempt fact reaches
the narrator twice. Fallback rendering (one beat per visible fact) and the
room feed (no text-level dedup in the reading path; distinct IDs render
twice) faithfully reproduce the duplication. The fix, if wanted, is
dedup-by-key at narration assembly or per-observer scoping — not taken
here: no production change is justified by this report.
