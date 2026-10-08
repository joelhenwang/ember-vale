# perf-beat-001: the beat engine's own overhead (everything but model wait)

**Question.** With model latency taken out, what does a beat cost in
database round trips, CPU and wall time? How does that grow with story
length and cast size, and what does it cost us now and later?

**Setup.** `backend/scripts/beat_bench.py`. It seeds a ring of places and a
cast in a throwaway database (`embervale_bench2`, recreated each run), then
runs beats through the real `Stage1Orchestrator`. Scripted fake gateways
answer instantly. Characters talk, move, observe and wait in a fixed
rotation, so scenes, reactions, resolution, narration, the director (every
3rd beat) and day-end summaries all run. There is no network and no
spend. Per beat it records:
- wall time;
- SQL statements and summed SQL time (SQLAlchemy cursor events);
- pool checkouts ("sessions");
- statement shapes (`--sql-top`);
- an optional cProfile window (`--profile`).

Run from `backend/`:
`python scripts/beat_bench.py --cast 3 --beats 300`

Machine: Windows 11 host, Postgres in Docker Desktop (port 5433). Each
host→container round trip costs about 1.2 ms. Inside the compose network:
one query costs 0.83 ms, and a session checkout with `pool_pre_ping` costs
2.6 ms (1.4 ms without the ping). So the absolute host numbers overstate
SQL cost about 2–3x against the deployed API. Statement counts are
machine-independent.

"Before" is 50d143f, run from a detached worktree. "After" is HEAD with
this work. Each A/B pair ran back to back in the same window, because
other benchmarks shared the machine. The scripted script picks actions
from call order, so call mixes differ slightly between runs; compare
per-beat figures.

## Results

### Scaling baseline (before), cast 3, 300 beats

| beat | wall p50 | SQL statements |
|---|---|---|
| 10 | 1.23 s | 558 |
| 50 | 2.81 s | 1,134 |
| 100 | 2.18 s | 1,127 |
| 200 | 2.37 s | 1,142 |
| 300 | 1.99 s | 1,200 |

Growth stops at about beat 50. The worst scans used a 60-event window,
and the story-so-far window is 240 events. Before that point, a beat's
SQL roughly doubles.

Cast 10, 100 beats (before): beat 10 took 6.1 s and 2,408 statements;
beat 50 took 14.8 s and 4,526; beat 100 took 19.6 s and 3,540.

Cast 25 (before): **the beat failed**. Every decision and every
attempt–reactor reaction started at once, hundreds of sessions queued on a
5 + 10 pool, and one waited 30 s:
`QueuePool limit of size 5 overflow 10 reached, connection timed out`.

### A/B, same window (wall p50 of the last 10 beats)

| cast, beat | before: SQL / wall | after: SQL / wall | mean beat before → after |
|---|---|---|---|
| 3, beat 10 | 604 / 1.40 s | 372 / 1.01 s | |
| 3, beat 50 | 1,101 / 2.45 s | **365 / 0.74 s** | 2.10 s → 0.92 s |
| 10, beat 10 | 2,882 / 6.96 s | 1,489 / 3.99 s | |
| 10, beat 30 | 3,188 / 8.23 s | **1,492 / 3.80 s** | 7.87 s → 4.31 s |
| 25, beat 10 | fails (pool timeout) | 9,096 / 22.9 s, completes | |
| 25, beat 30 | — | 8,002 / 33.2 s (30/30 beats; ~465 reaction calls a beat) | → 27.9 s |

Sessions per beat after the change: 86 (cast 3), about 320 (cast 10),
about 1,840 (cast 25).

### Where the time went (statement shapes and cProfile)

- **Every beat re-read the last 60 events, one scene at a time.**
  `_open_mentioned_place` called the director's full `_recent_happenings`
  only to learn what was said. For each of 60 events it ran `list_for_run`
  (3 queries), and it loaded every intent singly. At beat 50 that was
  236 participant queries, 236 attempt queries and 99 single intent loads
  per beat. Director beats ran it again, and `_story_so_far` loaded
  observations per event across up to 240 events.
- **Graphs compiled per call.** `StateGraph.compile()` ran about 45 times
  a beat with 3 characters: 17–91 ms of CPU each on the event loop
  (character 20, reaction 26, resolve 34, narration 27, director 91).
  The cost is inspect, ast, dis and typing: 64k `dis` instructions and
  348 `ast.parse` calls in 10 beats.
- **Response schemas regenerated per call.** Each system prompt rebuilt its
  constant JSON schema, about 15 ms of CPU per call.
- **Card loads.** Card loads were the top statement for a 10-character
  cast (153 per beat). Cards are immutable per version.
- **Per-call HTTP clients in production.** Every OpenRouter, Venice,
  writer, local-models, Krea and LangSmith call built and closed an
  `httpx.AsyncClient`:
  - construction costs 25 ms of CPU (it loads an SSL context);
  - to openrouter.ai, a fresh client takes p50 81 ms against 31 ms for a
    kept-alive one;
  - with 8 parallel calls, each takes 124 ms against 94 ms.
- **Picture encoding on the event loop.** The image runner's `shrink` takes
  77 ms for a portrait and 221 ms for a scene, stalling the API and beats
  it shares a process with.

## Changes (commits)

| commit | change |
|---|---|
| 07330b4 | One pooled HTTP client per event loop for all outbound adapters (`infrastructure/http_pool.py`); per-request timeouts; closed at shutdown |
| 721652c (+ stage1 hunks that landed in 9123b76) | Recent-happenings scan and story-so-far read in batched queries: `scenes_for_events`, `get_intents`, `narrations_for_events`, `observations_for_events`. Same results, same order |
| 1dcbe3c | Role graphs compile once (`graphs/compiled.py`, `compile_once` + ContextVar-bound deps); a concurrency test proves calls never see each other's deps |
| 47cd36f | Parallel-call budget per beat (`WORLDSIM_APP__PARALLEL_MODEL_CALLS`, default 12); pool 10 + 20 overflow; cards read once per beat |
| b57ad3a | Hedge twins recorded in the trace (`hedge: {twin_fired, winner, after_s}`, also on failures) with the upstream OpenRouter `provider`. The summary role (day-end summaries and digests) is not hedged. Per-role hedge waits are settings; pinned stories use them too |
| 97b9105 | System prompts memoized (byte-identical); picture shrink and Krea PNG re-encode run in a worker thread |
| (this commit) | Crowded scenes fit the resolver packet: over 16 attempts, active ones first and the rest folded into one line. 21 people at one place used to fail the beat |

## Decided against, and why

- **`pool_pre_ping` off.** Inside compose it costs about 1.2 ms per session,
  about 110 ms per beat at 86 sessions. Kept: after a database restart, the
  first request would otherwise fail. Revisit if sessions per beat climb.
- **Process-wide card cache.** A card read inside a transaction that later
  rolls back could be served stale. The per-beat cache has no such window.
- **Caching world reads within a beat** (locations, config, clock, hooks,
  items: about 300 statements per beat at cast 10). Scenes commit inside
  the beat, so a cache could hand a later reaction stale canon and change
  prompts. That needs a snapshot-scoped read model, not a memo.
- **New indexes** on `character_intent (author_character_id, created_at)`
  and on observations recent-or-salient. At real sizes (about 7% of
  observations are salient: 39 of 1,131 in a 40-beat story) these sorts
  cost about 1 ms. Not worth a migration while several are in flight.

## Left for later

1. **Reactions grow with the square of a crowd.** Each attempt is answered
   by every other person present. Cast 25 with 21 people at one place
   costs about 1,840 sessions and 9k statements per beat (23 s in the
   bench). In live play each is also a model call. This is a product rule:
   for example, only the addressed person and a few bystanders react.
2. **Per-call context building** still runs about 15 queries per decision
   or reaction. A beat-scoped read model built once from the sealed
   snapshot would cut cast-10 beats by about 1,000 statements.
3. Observations for a decision load everything recent or salient, so
   they grow slowly (about 7% of rows) with story length. Watch at 1,000+
   beats.
4. Map reads (`infrastructure/geography/openrouter.py`) still build a
   client per call. They are rare and not on the beat path.

## Verdict

The engine's own cost per beat fell 2–3x (cast 3: 0.74 s from 2.45 s at
beat 50; cast 10: 3.8 s from 8.2 s). It no longer climbs over the first
50 beats. The live path saves a TLS handshake and 25 ms of CPU per model
call. Large casts no longer fail beats on the connection pool or on
crowded scenes.
