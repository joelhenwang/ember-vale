# Structured narration live experiment 001

Pin: deepseek `deepseek-v4-flash-0731` rev10 (profile
`0e02a2fb-4e8c-4ac2-8c4e-b2db3c0dd80c`, max_tokens 4096) — same pin as the
validation-story session. Harness: `scripts/reliability-baseline.mjs`
(4-advance scenario + reload reads, `--no-browser`), extended with reusable
`--setup-only` / `--world` flags (measurement untouched). Stop-on-unresolved
held in both runs. Deployed build for run B: image
`sha256:e65cb63952ac3da9e7209eae788e201d83a20ed2b6df78facd3eb08a0f19dcec`
(code import-checked in-container; alembic head `0039` on the live DB).

## Reconciliation (read-only row evidence, supersedes earlier clock reads)

`phase_run.state` and `task_run.state` are authoritative. The story
`absolute_index` clock ticks at the *next* advance's start, so it lags one
beat behind completion by design — clock readings do not establish commit
state. Corrected record:

- Run A (story 4287abb1, idx1 + idx2): **both runs `completed`**,
  execution tasks `succeeded`, owners released. No open rows. The "two open
  run rows" statement in the prior draft was wrong.
- Run B (story 002208e2, idx1): **run `completed`** 236s after creation,
  execution task `succeeded`. The "stalled worker" was a misread: the
  deterministic `impossible` resolution needs no resolver call, so no
  missing trace implies no missing invocation — the precise stopping point
  was phase completion all along.
- Committed scenes vs completed phases: run A idx1: 2 scenes committed
  (resolutions `impossible`); run A idx2: 1 scene committed (resolution
  `success`, Ash reaction committed, Ash DIALOGUE beat with citation
  persisted); run B idx1: 1 scene committed (resolution `impossible`,
  4 fallback beats persisted, **zero narrator calls traced** — with the
  flag set, no roster, non-quiet intents (wait+observe), and no over-budget
  state, the structured branch is the only no-call path: it executed live).
- DB waits/locks: connections idle, zero ungranted locks. No checkpointer
  tables exist (graphs persist task checkpoints as `model_call` started/
  succeeded rows plus `task_run` rows, all present and terminal).
- Client timeout, task cancellation, and worker death are separate cases:
  there is no evidence of cancellation or death — completions at 185s and
  236s prove the workers stayed alive through both 180s client timeouts.
  The demonstrated gap is client cap (180s) vs server reality (185–236s):
  slow beats read `unresolved` client-side while committing server-side.

## Run A — EXCLUDED stale-build run, not a baseline

The API ran a 3-day-old image without the experiment code, so the verified
flag was ignored. Observations preserved below; none of them feed any
calculation of the intervention's effect (that rests solely on the
deterministic controlled measurement):

- Beat 1 travel: 47s wall, committed, retrieval complete (director 18.5s +
  2.6s, character 5.7s + 25.0s, all succeeded; quiet-path fallback).
- Beat 2 question: client timeout at 180s; server completed at ~185s (scene
  committed, Ash answered, narrator failed `malformed` in 16.6s, fallback
  beats persisted). Halt rule fired correctly; no retry.
- Narrator failure latency varies by run (16.6s here vs 62–137s in the
  validation session) — provider variance observation only.

## Run B — structured code live

- Beat 1 travel: client timeout at 180s; server completed at ~236s
  (directors 10.8s + 23.6s, characters 26.4s + 41.6s overlapping via the
  existing gather fan-out, reaction 65.0s failed + 95.2s retry succeeded
  with 3234 reasoning tokens, deterministic `impossible` resolution, scene
  committed, 4 beats persisted, zero narrator calls). Halt rule blocked the
  remaining three beats; no retry launched.
- With the flag verified set and the structured branch the only applicable
  no-call path, the live datum is positive on attribution mechanics
  (committed facts voiced, zero narrator time) but the beat still took
  236s: structured mode removes only the narrator call at the end of the
  chain, and nothing upstream changed.

## Spend accounting (recorded, not "beats worth")

Per-call USD from `model_cost` (`pricing s3-prov-v1`, all `estimated=true`;
reasoning-token billing treatment unknown; failed calls have no cost rows):

| Run | Calls with costs | Prompt+completion USD |
|---|---|---|
| A idx1 | director x2, character x2 | 0.0142 |
| A idx2 | character, reaction, resolver (narrator failed: unrecorded) | 0.0289 |
| B idx1 | director x2, character x2, reaction retry (first reaction failed: unrecorded) | 0.0302 |
| Recorded total | | **≈ $0.073** |

Failed-call usage is known in tokens from traces (A narrator: 1113 prompt /
4096 completion; B reaction: 2856 / 4096) but has no USD rows; at the
inferred estimated rates ($1.00/1M prompt, $3.00/1M completion, derived from
the recorded rows — not billed rates) that is ≈ $0.013 + $0.015 ≈ $0.028
additional estimated, ≈ $0.10 all-in estimated. Billed cost and remaining
allowance are unknown (no billing access).

## Recovery proof (fixed build, zero spend)

Diagnosis found a reporting defect in the recovery path itself:
`_duplicate_report` labeled any scene with beats as `narrated`, mislabeling
structured/fallback replays as model narration. Fixed by persisting the
`_narrate_scene` outcome on the scene row (migration
`0039_scene_narration_status`, nullable; first-write-wins so resumes never
downgrade to `skipped`) and replaying the stored status; legacy NULL rows
replay as `unknown`. Backend regressions added (stored structured/model/
fallback replay verbatim; legacy replays `unknown` with beats intact).

Live proof on the fixed build, both runs, normal path, no row edits:

- B idx1 replay: `duplicate=true`, narration `unknown` (legacy row),
  resolution/attribution intact.
- A idx2 replay: `duplicate=true`, narration `unknown`, resolution
  `success`, Wren's communicate intent preserved verbatim
  ("What did the market bell mean at dawn?").
- No new canon: world events still 7 (A) / 4 (B) with identical timestamps;
  traced call counts unchanged (4 / 6); story clock unmoved. Zero model
  calls issued by either replay.

## Standing gates

- Before any future paid run: verify build identity by image digest (not
  just an import check) and run a zero-spend smoke test against that
  deployed build which actually reaches narration and returns `structured`.
- Do not gate on waiting for provider responsiveness: first the stall
  question is closed (no stall occurred), and the live decision is now
  upstream-call cost, which structured narration does not address.
- Structured narration remains experimental; the usability milestone
  stays open.
