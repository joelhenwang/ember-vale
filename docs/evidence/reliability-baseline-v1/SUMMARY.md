# Reliability and beat-latency baseline v1

Fixed small scenario, normal configuration, frozen prompts/models/budgets/retries.
Question: how often does a player receive a useful response, and how long do they wait?

## Method

- Harness: `scripts/reliability-baseline.mjs` (`--mode fake|live`, capped at four
  committed advances plus reads; timeouts and failures retained, never retried).
- Scenario per run: travel beat (Wren Hearth -> Market) -> question beat (Wren asks
  Ash, player seat) -> follow-up beat (Ash answers, player seat) -> ordinary watcher
  advance -> reload (fresh detail + timeline + narration reads).
- Fake mode pins the story to a throwaway `fake-echo` provider profile (deterministic).
  Live mode uses the environment default untouched: `openrouter / deepseek-v4-flash-0731`.
- New read-only observability (no behavior change): per-call latency, error code,
  task id, retry attempts, manifest budgets, transmitted `max_tokens`, and pin
  revision on the watcher-only model-runs view; failed-call token usage preserved;
  `X-Worldsim-Admission-Ms` / `X-Worldsim-Execution-Ms` headers on advance.
- Sample is small (4 advances + reload per mode). Individual beat timings and
  min/max ranges below; no tail percentiles implied.

## Outcome layers (provider ok is not game success)

| beat | fake layers | live layers |
|---|---|---|
| travel | provider ok / committed yes / narration fallback / display yes | provider **degraded** (director + 2x character malformed) / committed yes / narration fallback / display yes |
| question | ok / yes / fallback / yes | degraded (character+reaction+resolver+narrator malformed) / yes / fallback / yes |
| follow-up | ok / yes / fallback / yes | degraded (reaction+resolver+narrator malformed) / yes / fallback / yes |
| ordinary | ok / yes / fallback / yes | degraded (2x character malformed) / yes / fallback / yes |
| reload | display yes, 0 committed events missing | display yes, 0 committed events missing |

Useful (committed + displayable + narration not failed): **5/5 in fake, 5/5 in live.**
Provider-ok advances: 4/4 fake, **0/4 live**. Every live beat landed entirely through
fallback paths; zero model-authored beats. Canon still commits (`success` resolutions,
timeline grows 5 -> 12 entries) and reload renders everything.

## Timings (ms, individual beats)

Fake advances (wall / admission / execution): 554/20/506, 592/15/551, 594/14/565,
558/22/516. Range: wall 554-594, admission 14-22, execution 506-565.
Live advances: 17937/10/17914, 51341/10/51321, 41594/9/41576, 17127/9/17105.
Range: wall 17127-51341, admission 9-10, execution 17105-51321.

Reads stay flat in both modes: timeline 15-44, narration reads 13-146, reload 132-212.
Browser (fake story, Edge headless): room render 13020 (first-hit Vite compile
included), in-page commit 1446 vs server execution 501 (**display overhead ~945**),
reload render 889. Live browser pass failed on a dead dev server and was not
retried against the live story, so no extra live generation was spent; the live
report retains that error row.

Generation by role, live (each traced call includes its retries; summed durations
double-count the concurrent character calls, so wall and sum are reported apart):

| beat | roles (calls x latency) | token prompt+completion | retries |
|---|---|---|---|
| travel (17.9s) | director 1x3718 failed, character 2x19541 failed | 5675+1536 | 0 |
| question (51.3s) | character 1x11485, reaction 1x12765, resolver 1x16161, narrator 1x9904, all failed | 10381+2048 | 0 |
| follow-up (41.6s) | character 2x2809 ok, reaction/resolver/narrator failed ~10-15s each | 13427+1578 | 0 |
| ordinary (17.1s) | director 1x3015 ok, character 2x16947 failed | 6174+1371 | 0 |

Roles execute sequentially behind barriers, so generation sums to the wall
(question: 11.5+12.8+16.2+9.9 = 50.3s of 51.3s). Admission (~10ms), reads (<150ms),
and display overhead (~0.9s) are noise next to generation.

## Attribution

Every call carries story/run/call ids, actor, task id, profile, transmitted
`max_tokens`, pin revision, budgets, outcome, error code, and per-attempt records;
failed calls keep their reported usage (e.g. `character_decision failed malformed
lat=13278 tok=2758/512`). Validation-failure repairs appear as paired traced calls
under one task id (fake mode: 2 calls per task); gateway failures skip repair and
appear once (live mode). One `started` leftover row is surfaced, not hidden
(covered in `backend/tests/test_reliability_audit.py`).

## Bottleneck and one proposed improvement

**Bottleneck: model generation, specifically truncation.** Every failed live call
reports `completion_tokens` exactly equal to the transmitted budget (512) — the
completions hit the cap, arrive truncated, fail schema validation (`malformed`,
never retried by policy), and every role falls back. The player waits 17-51s per
beat for content the provider never authors. Admission, commit overhead, reads,
and display are all two orders of magnitude smaller.

**Proposal (one): raise the live chat profile's transmitted `max_tokens` budget
until completions fit, then re-run this baseline unchanged and confirm the
malformed rate drops.** No prompt, model, budget-structure, or retry-policy change
beyond the single cap value; the baseline decides whether it worked.

## Files

- `baseline-fake-mugcjgeb.json`, `baseline-fake-mugcjo6c.json`: determinism pair
  (identical layer outcomes; timings vary). `baseline-fake-mugcisle.json` is a
  superseded setup probe (pre-seat-fix 403s, retained).
- `baseline-fake-mugcprbi.json`: fake run with the browser display pass.
- `baseline-live-mugclwxu.json`: capped live sample (4 advances + reads).
- `browser-room-fake.png`: room render during the display pass.
- Harness: `scripts/reliability-baseline.mjs`. Maintained tests:
  `backend/tests/test_reliability_audit.py` (5 passed; neighboring suites green,
  242/242 vitest, typecheck clean).
- Tree note: the baseline ran with the read-only observability patch applied
  (headers + model-runs fields, rebuilt into the compose API); prompts, models,
  budgets, and retry behavior unchanged.
