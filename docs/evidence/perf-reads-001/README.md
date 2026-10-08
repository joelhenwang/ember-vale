# perf-reads-001: per-character reads, long stories, and push vs poll (2026-10-08)

**Correction (same day, after a load test, section 7).** The capacity figures in the verdict and section 3 were estimates, and they were about 2x too generous. Measured: one process carried about 40 viewers watching autoplay before p95 passed 0.5 s, not 90. After the two fixes in section 7 it carries about 60. The load test also found that `WORLDSIM_APP__WORKERS=4` failed requests under load, by running out of database connections. That is fixed (section 7). The original numbers are kept below.

**Question.** `perf-summary-001` left three open items:
- about 7 per-character reads per model call;
- observations that pile up with story length, with no window on the salient set;
- whether pushing updates (SSE) should replace polling.

What do they cost, and what should change?

**Verdict.**
- **Per-character reads: done.** A turn's non-model work is 17–20% faster, with 11–22% fewer statements and 29% less SQL time. Prompts are byte-identical.
- **Long stories: flat to 1,000 turns.** Cost grows only through salient observations, which have no time limit. They are now capped at the newest 200 per character. Prompts are unchanged for any story under about 2,800 turns.
- **SSE: not needed yet.** One API process serves about 90 viewers watching autoplay, or about 540 idle players. The design for when that is exceeded is below.

## 1. Per-character reads (`f9fbbdb`)

Setup: `beat_bench.py` (fake model, throwaway database). It now caps crowd reactions at 2 bystanders like production (`--bystanders 2`). Ten characters ran 30 turns and 25 characters ran 20. The "before" ran from a clean copy of `4365873`.

| | Statements a turn | SQL time a turn* | Wall p50 |
|---|---|---|---|
| 10 characters, before | 907 | 7.9 s | 2.60 s |
| + memories shared per phase | 878 | 5.4 s | 2.10 s |
| + batched inserts, shared item reads | **808 (−11%)** | **5.7 s (−29%)** | **2.17 s (−17%)** |
| 25 characters, before | 2,189 | 22.5 s | 6.03 s |
| + memories shared per phase | 2,042 | 17.3 s | 5.92 s |
| + batched inserts, shared item reads | **1,711 (−22%)** | **16.0 s (−29%)** | **4.82 s (−20%)** |

\* Summed over concurrent sessions, so it is larger than wall time.

The changes:
- **One read of a character's own material per phase.** Observations, memories, relationships, digests and recent turns are memoised in the phase view (`phase_reads`). A reactor answering several attempts read them once per attempt. The intention stays a fresh read, because a reply can restate it mid-phase.
- **No flush per perception row.** `add_observation` and `add_memory` flushed each row, which meant 209 single-row INSERTs a turn at 25 characters. A commit now writes them in one batched INSERT.
- **Decision item ids reuse the context's reads.** The two item queries per decision now hit the shared view.

Check: `beat_bench.py --verify-reads` rebuilds every context from fresh reads and compares them byte for byte. It passed after each change.

**What is left per call, and why it stays.** Tracing writes 5 statements per model call (start plus manifest, then finish plus cost) in 2 transactions, about 39% of a turn's statements. The first transaction is the crash audit: it records the call before the provider answers. Merging the two would lose it. The intention read (1 per call) stays fresh, as explained above.

## 2. Long stories

**Flat to 1,000 turns** (3 characters, `data/long-cast3-1000.json`):

| Turns | Wall p50 | Statements | SQL time |
|---|---|---|---|
| 1–100 | 840 ms | 334 | 715 ms |
| 101–200 | 811 ms | 333 | 695 ms |
| 301–400 | 598 ms | 331 | 513 ms |
| 601–700 | 608 ms | 330 | 532 ms |
| 901–1000 | 586 ms | 331 | 523 ms |

By turn 1,000 each character has about 1,300 observations.

**The fake model never cites, so nothing became salient.** In live play, cited rows get a salience bump, and `perf-llm-001` found about 7% of rows salient. A context reads every recent row (last 30 turns) plus every salient row of any age. So I made Wren's rows salient in the 1,000-turn database:

| Salient | Rows a context reads | Query time |
|---|---|---|
| 0% | 39 | 1.7 ms |
| 7% | 118 | 0.6 ms |
| 50% | 695 | 1.3 ms |

The database is not the problem. Ranking is: each row becomes candidates that are scored and sorted on every call (`data/rank_bench.py`, 3 facts a row):

| Rows | 40 | 120 | 239 | 400 | 1,000 | 3,000 |
|---|---|---|---|---|---|---|
| ms per context | 0.7 | 2.1 | 4.2 | 7.4 | 18.3 | 62.0 |

At 7%, a 10,000-turn story would rank about 900 rows, about 16 ms per call. A 10-character turn makes ~50 calls, so that is ~0.8 s of event-loop time a turn, and it keeps growing.

**The cap (`OLDER_SALIENT_KEPT = 200`).** A context reads every recent row, plus only the newest 200 salient rows from before the window (`older_limit` on `observations_for_observer` and `memories_for_owner`). Memories get the same cap. At 7% the cap first binds after about 2,800 turns, so every shorter story's prompts are unchanged. A salient row from thousands of turns ago scores close to nothing anyway (half-life 40 turns). Long-term material lives on through the day-end digests. Test: `tests/test_salient_cap.py`.

**Day-end digests read every observation ever made.** They filtered salience in Python. The filter now runs in SQL, with identical results.

## 3. Push instead of poll (SSE): study and design, not built

Measured cost of one presentation poll: about 22 ms of CPU and DB time, or about 45 a second in one process (`perf-summary-001`). The ETag middleware saves bytes, not work: the handler still runs before the 304.

| Screen and state | Poll | Viewers one process carries |
|---|---|---|
| Adventure, idle | 12 s | ~540 |
| Adventure, picture painting | 4 s | ~180 |
| Adventure, turn being written | 1.5 s | ~67 |
| Watch, idle | 15 s | ~675 |
| Watch, autoplay playing | 2 s | ~90 |

The game today has one player. `WORLDSIM_APP__WORKERS=N` multiplies these figures by N.

**Decision: keep polling.** Revisit when one process regularly serves about 50 or more viewers with an active turn or autoplay.

The design for when that happens:
1. **A per-story change stamp.** A counter bumped in the same transaction as every change a viewer sees: event commit, narration written, picture finished, autoplay state, clock.
2. **A cheap 304.** Reads that include the stamp in their ETag answer `If-None-Match` from one indexed read, without building the presentation. Polling stays, and an unchanged poll drops from ~22 ms to ~1 ms. This is the bigger win per line of code.
3. **SSE on the same stamp,** only if needed after step 2: one `GET /stories/{id}/events` stream per viewer, which sends the new stamp. The client then fetches as it does today. With several processes, a stamp change reaches the other processes through Postgres `LISTEN/NOTIFY`.

The risk in steps 1–2 is a change that forgets to bump the stamp, which leaves a stale screen. A test must hold every presentation-visible write to it. That is why this waits for real need.

## 4. Browser check of the perf pass

A fresh quick-start story on the dev API (Venice), one turn, about $0.01. The checks:
- Home, New Story review and Adventure render.
- The turn's narration, reply, story lead and place art appear.
- There are no console errors.
- 12 polls came back as 304.
- Presentation is gzipped (2.2 to 1.4 KB).
- Portraits and map tokens load `?w=` variants.

The Adventure stage loads its 1,672 px original on purpose. It covers a tall box (658×889 CSS px), so the picture is drawn about 1,580 px wide even at 1×.

## 5. Watch screen under live autoplay

A new watcher story (Wren and Ash on Venice): Play for 60 s, Pause, then 40 s idle. Headless Edge, script `data/watch-live.mjs`, raw output `data/watch-live.json`. The run took 8 turns and 45 model calls, about $0.04 at list price.

| Window | Requests | Wire | Notes |
|---|---|---|---|
| Load | 6 | 4 KB | |
| Playing, 60 s | 104 | 456 KB | 32 ticks at 2 s, each presentation + autoplay + chronicle (about 4 KB a tick); 3 paintings make up most of the bytes |
| Paused, 40 s | 4 | 1 KB | presentation + autoplay every 15 s; the chronicle is skipped while nothing changes |

The page had one long task (75 ms) and no console errors.

Revalidation, checked directly: an unchanged presentation answers `304` with 0 bytes, but it takes 17 ms against 16.5 ms for the full answer. A 304 saves bytes, not server work, which is the case for the change stamp in section 3.

## 6. The salience cap under live-like citation

The 1,000-turn bench in section 2 used a fake model that never cites, so nothing became salient. `beat_bench.py --cite 0.3` makes the fake day-end summary cite 30% of its sources, which raises their salience as live play does. By turn 1,000, 22–23% of observations were salient, about 3x the live 7%. `--salient-cap` overrides the cap. 3 characters, 1,000 turns each (`data/long-cite30-*.json`):

| Turns | Decide, no citing | Decide, citing, no cap | Decide, citing, cap 200 |
|---|---|---|---|
| 1–100 | 201 ms | 196 ms | 160 ms |
| 401–500 | 137 ms | 412 ms | 241 ms |
| 801–900 | 143 ms | 403 ms | 287 ms |
| 901–1000 | 143 ms | 433 ms | 272 ms |
| Mean turn | 713 ms | 1,064 ms | 843 ms |

Without the cap the decision phase kept growing, to 2.2x by turn 1,000. With it, the phase levelled off near 280 ms once the cap began to bind (about turn 550 at this citation rate). The rest of the gap to no citing is the 200 kept rows plus the recent window, which is the intended cost of remembering important things.

## 7. Poll load test (`data/poll_load.py`)

N simulated viewers each read presentation, autoplay and the chronicle every 2 s, as Watch does while playing. They send If-None-Match like a browser. 30 s per step, against the dev container with Docker Desktop and 14 CPUs. About 90% of the answers were 304s.

**One process, before the fixes** (`data/poll_load.json`):

| Viewers | Requests/s achieved (wanted) | p50 | p95 | Errors |
|---|---|---|---|---|
| 10 | 15 (15) | 13 ms | 28 ms | 0 |
| 25 | 37.5 (37.5) | 16 ms | 44 ms | 0 |
| 50 | 75 (75) | 44 ms | 640 ms | 0 |
| 100 | 133 (150) | 541 ms | 1.4 s | 0 |
| 200 | 103 (300) | 1.6 s | 6.5 s | 0 |

**Four processes (`WORKERS=4`) failed under load.** Each process opened up to 10+20 connections, 120 in all, against Postgres's default `max_connections` of 100. At 300 viewers, 536 requests failed with `TooManyConnectionsError`. The fixes:
- compose now runs Postgres with `max_connections=200`;
- `WORLDSIM_DATABASE__CONNECTION_BUDGET` (default 150) is shared between API processes, so N processes can never exceed it (`pool_share` in `interfaces/cli.py`, `tests/test_pool_share.py`).

After the fixes, 4 processes served 300 viewers with 0 errors. They saturated near 270 requests/s, about 68 per process and CPU-bound. They held 150 viewers at p95 about 0.55 s (`data/poll_load_workers4.json`).

Repeated three times at 150 viewers (three clients of 50, `data/poll_load_workers4_150x3.txt`), p95 was 380–400 ms, then 185–190 ms, then 1.4–1.5 s. In the last repetition p50 also rose to about 440 ms. The host is shared with Docker Desktop's VM and other apps, so 150 viewers is at the edge for four processes. The dependable figure is about 100 viewers (p95 122 ms).

**Profile of a quiet tick** (`data/poll_profile.py`, in-process): about 50 statements a tick. There is no single hot spot, so the cost is the number of database round trips plus framework overhead. Two fixes:
- **An empty chronicle page returns early.** With nothing after the cursor, the reads that only dress entries (config, people, places, narration, scenes) are skipped: 8 to 3 queries, same response.
- **One access log, not two.** uvicorn's access line duplicated `worldsim.access` on every request; it is off now.

**One process, after** (`data/poll_load_after.json`):

| Viewers | p50 | p95 | Errors |
|---|---|---|---|
| 10 | 9 ms | 27 ms | 0 |
| 25 | 18 ms | 70 ms | 0 |
| 50 | 26 ms (was 44) | **159 ms (was 640)** | 0 |
| 100 | 525 ms | 2.5 s | 4 client timeouts at saturation |

**The SSE decision still stands, now measured.** One player is far below every limit. One process now carries about 60 watching viewers, and `WORKERS=N` scales near-linearly in viewers until the CPU runs out. 90% of the load is unchanged 304s that still cost full work, so the change stamp in section 3 is the next lever. It would make most requests about 3 queries. Build it when real viewers approach ~50 per process.

## 8. The change stamp: why it is designed but not built

The stamp would let an unchanged poll skip building the presentation, the lever on the 90% of load that is 304s. Building it needs one value that changes whenever anything the presentation shows changes. The presentation reads 19 repository methods over 11 kinds of data:
- events and their narration;
- people, places, journeys and activities;
- rumours;
- phase runs;
- pictures, image assets and their paint jobs;
- the world and its config.

Those are written from at least six places: turn commits, background narration, the director, the image runner (a separate process when scaled), autoplay, and story settings and interventions.

Three ways to keep the stamp, and what goes wrong with each:

| Way | Problem |
|---|---|
| The app bumps it on every write | A write that forgets the bump leaves a screen stale with no error. The risk grows with every new feature that writes. |
| A Postgres trigger on every world table bumps one row per story | It cannot forget, but every write in a turn then updates the same row. The turn's commits, which run in parallel (`1caa5e7`, `4de0533`), would wait on that row lock and run one after another. That throws away the beat engine's main speed-up. |
| A fingerprint query (max sequence, versions and counts over the 11 inputs) | No lock, but it is about 11 lookups a poll. A quiet tick is already 3 + 16 + 3 queries, so it saves about half and still needs every input listed. |

**Decision:** not now. One player uses a fraction of one process, and `WORKERS=N` adds about 60 viewers per process, which is cheaper and carries no staleness risk. If it is ever needed, the fingerprint query is the safe first step. It should come with a test that runs a scripted story (turns, background narration, a painted picture, a director rumour, autoplay) and checks after every step that the fingerprint changed whenever the presentation body did.

## 9. The fingerprint, built and measured (opt-in)

Section 8 rejected the fingerprint on an assumption: about 11 lookups a poll. Written as one SQL statement with sub-selects, it is a single round trip. So I built it, behind `WORLDSIM_APP__PRESENTATION_FINGERPRINT` (default **off**).

- **The fingerprint** (`WorldRepository.presentation_fingerprint`) covers every input of the presentation:
  - the world row and clock, phase runs, places, people and their state, activities, rumours, the newest event, picture assets, the world config, scene pictures and image jobs;
  - versioned tables count as row count plus sum of versions, since versions only grow;
  - small and unversioned tables are hashed whole.
- **The tag** mixes in the role, the viewer, and a hash of the presentation code and schemas, so a deploy never matches an old tag.
- **On a matching `If-None-Match`** the route answers 304 straight after role resolution and the fingerprint, without building anything.
- **The staleness test** (`tests/test_presentation_fingerprint.py`) plays a scripted story: 12 turns across a day's end, a rumour opened and settled, and a config change. After every step it checks, for a watcher and a player, that a changed presentation came with a changed fingerprint. Checked against a mutant: with rumours left out of the fingerprint, it fails on "rumour opened".

**One process, the same poll load test** (`data/poll_load_fingerprint*.json`, `data/poll_load_after_knee.json`):

| Viewers | p95, without | p95, fingerprint | p50, without | p50, fingerprint |
|---|---|---|---|---|
| 10 | 27 ms | 16 ms | 9 ms | 10 ms |
| 25 | 70 ms | 20 ms | 18 ms | 10 ms |
| 50 | 159 ms | **39 ms** | 26 ms | 13 ms |
| 75 | 458 ms | **73 ms** | 68 ms | 21 ms |
| 90 | 1.7 s (saturated) | 2.3 s (saturated) | 411 ms | 519 ms |

A revalidated presentation takes 7–11 ms instead of 17. Under load the tail is 4–6x shorter, and the point where one process tips moves from about 60 viewers to about 80. Past that, the remaining per-request work saturates the process near 110 requests/s: auth and role resolution, the autoplay and chronicle reads, and the framework. The fingerprint does not touch any of those.

(The without-fingerprint 60-viewer step in `poll_load_after_knee.json` shows 357 errors. Those were connection refusals while the restarted API came up, because the load started too early. They are not failures under load.)

**Decision: built, tested, off by default.** For one player it changes nothing measurable (about 10 ms either way). Turn it on when a process serves dozens of viewers. Every new feature that writes something the presentation shows must extend `_FINGERPRINT` and the scripted test; the comment on the query says so. Section 8's analysis of app-side bumps and triggers stands. The fingerprint avoids both problems: it needs no bumps and takes no locks.

**Fingerprint cost on a long story.** On a 300-turn, 10-character bench story (1,367 events, 300 phase runs), the fingerprint took 1.65 ms p50. With 3,000 image jobs inserted it took 3.39 ms, all of the growth from hashing every job's status. Every status change goes through `save_job`, which raises the job's version, so that hash duplicated the version sum. It was removed: 1.55 ms p50 with the 3,000 jobs, and the staleness test still passes. A build of the presentation takes about 17 ms.
