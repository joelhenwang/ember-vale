# Structured narration live experiment 001

Pin: deepseek `deepseek-v4-flash-0731` rev10 (profile
`0e02a2fb-4e8c-4ac2-8c4e-b2db3c0dd80c`, max_tokens 4096) — same pin as the
validation-story session. Harness: `scripts/reliability-baseline.mjs`
(4-advance scenario + reload reads, `--no-browser`), extended with reusable
`--setup-only` / `--world` flags (measurement untouched). Stop-on-unresolved
held in both runs.

## Run A — stale code (story 4287abb1, invalid as experiment, kept as control)

The API container was running a 3-day-old image without the structured-mode
change (uncommitted working tree, no source mount). The verified
`narration.mode=structured` flag was therefore ignored. Findings still valid
as main-line behavior on this pin:

- Beat 1 travel: 47s wall, committed, retrieval complete. Calls: director
  18.5s + 2.6s, character 5.7s + 25.0s, all succeeded. Narration `fallback`
  via the quiet path (no narrator call either way).
- Beat 2 question: client transport timeout at 180s (character 112.5s +
  reaction 27.3s + resolver 28.3s + narrator 16.6s ≈ 184s+). Halt rule fired
  correctly: follow-up + ordinary advance blocked, no retry, resolution
  recorded `unresolved`.
- Server-side post-timeout: the beat ran to completion — Ash answered
  ("Dawn bell means the market's waking..."), scene committed to the
  timeline, narrator call failed `malformed` (reasoning 4096/4096,
  `finish=length`) in 16.6s, fallback beats persisted. Story clock stayed at
  index 2, so the run's final phase state is unconfirmed from the client
  side; the committed scene event itself is in the timeline.
- Provider variance note: this narrator failure took 16.6s vs 62–137s for
  the same signature in the validation session.

## Run B — structured code live (story 002208e2, flag verified)

Rebuilt the API image from the working tree, restarted, verified
`NARRATION_MODE_KEY` imports in the live container. Fresh story, flag
verified `narration.mode='structured'` via read-back.

- Beat 1 travel: client transport timeout at 180s; halt rule blocked the
  remaining three beats. Traced so far: director 10.8s + 23.6s, character
  26.4s + 41.6s (all succeeded), reaction 65.0s FAILED (`malformed`,
  reasoning 4097/4096) then reaction retry SUCCEEDED after 95.2s
  (comp 3298, reasoning 3234).
- Zero narrator calls traced (the beat never reached narration). No
  conclusion on narrator latency yet — the blocker is upstream.
- The beat then stalled: no new traced row for 10+ minutes after the
  successful reaction (no resolver invocation began), clock still at 1, no
  error or traceback in container logs, API reads healthy. Indistinguishable
  from outside whether the worker is hung or awaiting an untraced step.

## Outcome

The core question — a live structured-mode beat completing with status
`structured` and zero narrator calls — is unanswered. After the reaction
retry succeeded, no new traced row appeared for 20+ minutes (no resolver
invocation began), clock stayed at 1, no error or traceback in container
logs, API reads healthy throughout. The worker is stuck or dead without a
trace; the run row for index 1 remains open.

Contributors, owned and observed:

1. Stale-image error (owned): the first run executed pre-experiment code.
   Fixed by rebuild + restart + in-container import check.
2. Provider degradation upstream of narration (observed): 65–95s reaction
   calls with 3200–4100 reasoning tokens on deepseek rev10 today, vs 4–74s
   in earlier arms. Structured mode cannot shorten any of this — it only
   removes the narrator call at the end of the chain.
3. Silent stall post-reaction (observed, unexplained): no resolver row, no
   error. Needs diagnosis before any retry, not more spend.

No further advances launched under the halt; a retry now would face the
open index-1 run row plus degraded provider conditions. Recommendation:
diagnose the post-reaction stall (candidate: worker fate after client
disconnect; resolver-graph invocation tracing) on the deterministic suite
first, then re-attempt the live run when the provider is responsive.
Usability milestone remains open.
