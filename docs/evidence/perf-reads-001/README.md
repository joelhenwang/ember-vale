# perf-reads-001: per-character reads, long stories, and push vs poll (2026-10-08)

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
