# Structured narration mode — experiment 001 (controlled measurement)

Date: 2026-09-28. No paid calls made; no live run yet (needs spend confirmation).

## Corrections to the earlier proposal

1. Narrator failures are cohort-bounded, not universal. Measured cohort: 8
   failed narrator calls across the five live trace arms (venice-1024 x2,
   deepseek-4096-rerun x1, budget-512 x2, budget-4096 x1, baseline-v1-live x2;
   all `malformed`/`finish=length`) plus 3 failed narrator calls in sampled
   validation-story beats 2/4/9 — 11 failed in this measured cohort. Round-7
   evidence (`docs/evidence/live-quote-2026-09-24/PROVENANCE.md`, beat 2 at
   4096 budget) records a successful model narrator, so the failure is
   configuration/cohort-specific.
2. `_decide_all()` already fans character decisions out over
   `asyncio.gather()`; the observed Player loop has one eligible autonomous
   character, so that concurrency offers little there. Call sums ~= walls
   describes these runs, not the architecture.
3. Reasoning exhaustion is established; the prompt as the cause is not —
   multiple unsuccessful budgets do not isolate prompt, model, provider, or
   their interaction.

## Implementation (opt-in, default unchanged)

- World-config key `narration.mode`: `"structured"` selects the mode; absent
  or any other value keeps model narration. No profile IDs hardcoded, no
  history-based auto-disable.
- Structured scenes persist the same `fallback_beats()` as the quiet path
  (shared `_save_fallback_beats` helper): committed-utterance facts become
  cited DIALOGUE beats with speaker attribution; audience filtering and
  normal persistence unchanged. No narrator gateway call, no model-call row.
  Beats and their source commit atomically (deterministic and model paths);
  a crash between narration persistence and phase completion resumes with
  the exact source, no extra beats, no narrator calls.
- Status `"structured"` distinguishes configured skips from attempted
  generation (`"narrated"`/`"fallback"`/`"failed"`). Recorded failures
  persist `"failed"` (replayable even with no beats); a later legitimate
  resume that narrates successfully replaces `failed`, never a known
  source; `skipped` writes nothing and reports the stored source when
  known. Frontend shows no fallback notice for it (only exact `"fallback"`
  triggers one); quality `fallback_rate` counts only `"fallback"`.
- Recruit/combat accounting: the structured path skips
  `_recruit_from_narration()` and `_resolve_combat_tags()`, identical to the
  existing quiet/over-budget and failure paths. Additionally, structured
  mode applies only to roster-free scenes; scenes with a roster proceed to
  the model path. The earlier over-budget skip still applies to any scene
  regardless of roster (behavior preserved, not widened). The mode is
  therefore bounded to roster-free scenarios such as the starter scenario.
  No general gameplay equivalence claimed.
- Harness `classify()` preserves per-scene statuses in
  `layers.narration_kinds` and labels the beat explicitly: uniform known
  statuses pass through (`structured`, `fallback`, `skipped`, `narrated`),
  any mix reads `mixed`, failure keeps precedence. All-`skipped` reads
  `skipped` (source unknown), never `fallback`; nothing falls through to
  `narrated` by elimination.

## Controlled measurement (deterministic, zero provider spend)

Fake narrator sleeps 1.0s before answering; identical fixtures both runs:

- model_wall=1.70s, structured_wall=0.67s, saved=1.03s
- narrator gateway time: model 1.00s, structured 0.00s (zero calls, zero
  traced rows)
- upstream constant: same scene count, same resolution outcomes, same event
  volume; committed Ash answer persisted as cited DIALOGUE in structured run;
  duplicate replay adds no canon and re-reads identically.
- The maintained regression asserts the deterministic sleep-accounted
  narrator time plus zero narrator calls, not a wall-clock comparison of
  two database-backed runs; the observed walls above stand as evidence.

Tests: 11 new in `backend/tests/test_stage1_orchestration.py` (zero calls,
dialogue persistence, reload/replay, default path, status distinction,
roster deferral, delayed saving, stored structured/model/fallback replay,
legacy-`unknown` replay, post-commit interruption resume, failed-to-success
resume); mixed-outcome classify cases in
`scripts/reliability-baseline-lib.spec.mjs`. Full orchestration module,
migration cycle, and narration-graph suites green; `ruff check` clean.

## Bounded live run (executed; see structured-narration-live/LIVE-001.md)

Two short harness runs against deepseek rev10 (story 4287abb1 stale-build
excluded; story 002208e2 on the fixed build). Core live datum: the
structured branch executed (zero narrator calls, beats persisted) but beats
took 185–236s on upstream calls. Duplicate-report inference fixed via
migration 0039 with live recovery proof. Compare
attribution/persistence correctness, answer occurrence, per-beat waits,
failures, and unresolved outcomes separately — not equal spoken-line counts
(upstream reactions vary), and historical walls are reference only. Success
criterion: one measured latency reduction; the usability milestone stays open
(a 152s resolver-class call remains untouched by this change).
