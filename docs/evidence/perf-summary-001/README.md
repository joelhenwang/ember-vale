# perf-summary-001: whole-project performance pass (2026-10-08)

**Question.** Where does Ember Vale spend time, bytes, CPU and money? What can be cut now, and
what has to change before the game serves more than one player or much longer stories?

**Verdict.** Every layer had cheap, large wins:
- pages load 3–8x fewer bytes;
- idle pages stop burning CPU;
- reads stay flat on stories 300x longer;
- a beat's own overhead (model wait aside) is 2–3x lower, and 25-character casts no longer fail;
- the API image builds in seconds and starts 2.5x faster.

The work is behaviour-neutral: prompts are proven byte-identical, and no copy or animation was
removed. What is left is listed under *Open*. The one item that needs a product decision is
how many characters react in crowds.

Thirty-four commits, `969b100` to `b9e3e92`, plus this write-up. Each area has its own evidence folder with method
and raw data:

| Area | Folder | Worker |
|---|---|---|
| Backend reads, HTTP, DB | `perf-backend-001` | P1 |
| Beat engine (non-model) | `perf-beat-001` (+ Addendum P5) | P2, P5 |
| Frontend runtime and loading | `perf-frontend-001` | P3 |
| LLM spend and the image pipeline | `perf-llm-001` | P4 |
| Docker, server and dev loop | `perf-infra-001` | P4 |
| Cross-cutting fixes and final numbers | this folder | coordinator |

## Setup

- **Dev API:** the compose container on 8101 (Docker Desktop, Windows 11 host).
- **Database:** Postgres 16 on 5433.
- **Frontend:** the production build served by `vite preview` on 5181, measured with
  `scripts/page-bench.mjs` (Edge through playwright-core, full motion, median of 3, cold
  cache, 10 s untouched).
- **API reads:** `backend/scripts/api_bench.py` (n = 20, Mara's story `bdea0982…`).
- **Turns:** `backend/scripts/beat_bench.py` (fake model, throwaway databases).
- **Cost:** no paid model calls were made. Krea was not used.

## Final numbers

### Pages (production build): before `perf-frontend-001` "before", after `data/pages-final.json`

| Page | KB before → after | LCP ms before → after | Main thread idle | Browser CPU idle (10 s) | Idle after 70 s |
|---|---|---|---|---|---|
| Home | 4154 → **1173** | 2440 → 1848 | 23.6% → 0.4% | 105% → 53% | 0.1% |
| Stories | 5691 → **1236** | 2380 → 1548 | — → 0.3% | — → 29% | — |
| Library | 3780 → **825** | 600 → 396 | 17.5% → 0.3% | 73% → 35% | — |
| New story | — → 1150 | — → 1152 | 19.4% → 0.3% | 80% → 44% | — |
| Character studio | 2077* → **499** | — → 512 | — → 0.3% | — → 33% | — |
| Adventure | 3158 → **749** | 2040 → 1644 | 19.7% → 0.6% | 86% → 50% | **43% → 0.4%**† |
| Watch | 5277 → **616** | 2480 → 2484‡ | 12.6% → 0.4% | 66% → 48% | 0.3% |
| Settings | — → 374 | — → 504 | — → 0.3% | — → 31% | — |

Notes on the table:
- \* Measured mid-pass, before `815a29b`.
- † Rested Adventure was still at 43% after P3's work. The cause was the wake-on-content
  observer (`6525eef`), which every idle re-render tripped; `b9e3e92` fixed it.
- ‡ Watch's LCP element is the event-feed text at 1.1 s warm. The cold-run figure includes the
  first request for a picture variant, which encodes it once (`edcba3e`).
- "Browser CPU" is the whole browser while ambient loops run, mostly compositor and GPU work.
  After 60 s without input or new story content, the loops rest (`0d62f92`, `b9e3e92`).

Where the bytes went:
- full paintings drawn small: `?w=` variants (`edcba3e`, `815a29b`);
- the PNG starter art and maps, now WebP (`e6d48f9`, `7f6b321`);
- fonts: Latin subsets only, EB Garamond dropped (`813223a`, `6525eef`);
- a vendor chunk: entry JS 129 → 24 kB (`6d7c4c0`).

### API reads (container, p50 ms): `data/api-before.json` → `data/api-final.json`

| Read | Before | After | Note |
|---|---|---|---|
| Stories list | 79.8 | **10.0** | 81 → 3 queries (`969b100`) |
| Presentation (polled) | 24.7 | **18.9** | Flat to 300x story length (`9311413`, `fa8655d`, `9c1ed92`) |
| Chronicle (100 entries) | 422§ | **13.7** | 168 → 8 queries |
| Autoplay | 12.5 | 8.2 | |
| Suggestions | 11.1 | 11.7 | |
| Story drafts | 6.8 | 8.0 | 12.7 → 1.5 KB on the wire (gzip, `2c8f1fa`) |

§ The baseline asked for 200 entries, over the limit; P1's interleaved A/B is 536 → 50 ms at
today's size and 1,725 → 60 ms at 300x.

Bytes on the wire: JSON over 1 KB is gzipped, 4–8x smaller (`2c8f1fa`). An unchanged poll is
a bare 304 (`45dfb09`). Pictures are cached for a year, keyed by ETag (`2c8f1fa`).

**Throughput.** In-process, the app costs about 0.4 ms per request on the health route under
cProfile, so about 2,400 req/s. Through the container it measures 330–470 req/s. That figure
is bounded by the Python load client and Docker Desktop's port forwarding, not by the app.
Before `26f0dc1`, the two `BaseHTTPMiddleware` layers capped it at 200–250 req/s. Presentation
runs at about 45 req/s in one process, about 22 ms of CPU and DB time each. That is plenty
for one player and the reason multi-process support exists now (below).

### Beats without the model (fake provider, `perf-beat-001`)

| Story | Before | After |
|---|---|---|
| 3 characters, beat 50 | 1,101 queries, 2.45 s | 365 queries, 0.74 s |
| 10 characters, beat 30 | 3,188 queries, 8.2 s | 1,492 queries, 3.8 s (P2); then 2,010 → 986 statements with phase-shared reads (P5, partly a lighter call mix) |
| 25 characters | Beat fails (pool timeout) | All 30 beats complete |

The levers, by commit:
- `721652c`: batched event reads.
- `1dcbe3c`: role graphs compile once (about 45 compiles a beat at 17–91 ms).
- `07330b4`, `d70183c`: one pooled HTTP client (TLS handshakes; 25 ms of SSL setup per call).
- `47cd36f`: bounded parallel model calls; pool 5+10 → 10+20.
- `97b9105`: the schema is rendered once, and picture encoding moved off the event loop
  (77–221 ms stalls).
- `50913cf`: phase-shared reads, prompts verified byte-identical in CI (`tests/test_phase_reads.py`).
- `5663e38`: tracing does 2 fewer statements per call.
- `59528c7`: a cancelled request now stops the director instead of hanging. This was a latent
  bug that plain ASGI exposed: asyncio cancels once, where the old anyio path re-delivered.

### Model spend and latency (`perf-llm-001`, offline from the dev DB)

- **Prompts stay bounded.** They level off near 6.6k tokens after about 20 beats.
- **Cache hits are 56–69%.** Warming the cache was rejected: +2 points for +1.6 s per turn.
- **Stored Venice cost was about 4.5x too high.** Calls were priced at the fallback rate;
  fixed with list prices (`9845502`).
- **Day-end summaries were cut short.** 9 of 71 hit the 1,024-token cap; it is now 1,536.
- **Hedging.** Background summaries and digests are no longer hedged, and twins are now
  recorded (`b57ad3a`). By duration, about 36% of summaries had likely fired a twin.

### Infrastructure (`perf-infra-001`)

- **Build context:** 4.3 GB → 32 kB. It had included `.env`; a `.dockerignore` now excludes it.
- **Rebuilds:** 27 s → 2 s with no change, 36 s → 7 s after a code change.
- **Start-up:** 18 s → 8 s.
- **Idle memory:** 144 → 121 MiB.
- **Postgres:** `pg_stat_statements` is on, and the 60 s statement timeout is now really
  applied (`0ae4f81`).
- **Test runs:** scratch databases carry their creation time; a run sweeps leftovers older
  than 6 h that nobody is connected to (`7e75efe`). 53 had leaked.

## Future-proofing (designed and built)

- **More than one API process** (`49c777e`):
  - Image jobs are claimed with `FOR UPDATE SKIP LOCKED` plus a 10-minute lease (migration
    0057), so two runners never paint the same job. Autoplay already claimed stories with a lease.
  - `WORLDSIM_APP__BACKGROUND_LOOPS=false` keeps autoplay, painting and indexing out of the API;
    `python -m worldsim.interfaces.worker` (compose profile `scale`) runs them instead.
  - `WORLDSIM_APP__WORKERS=N` serves HTTP from N processes, and refuses to start while every
    process would also run the loops. The default is unchanged: one process doing everything.
- **Long stories:**
  - reads are batched and capped: the newest 40 pictures, renown cached per event sequence;
  - Adventure opens on the newest page and backfills older ones (`f9117e6`);
  - the log and feed draw a window, not every line.
  - Tested to 9,000 events (300x Mara's story).
- **Big casts:** bounded model concurrency, a larger pool, phase-shared reads, and crowded
  scenes fold extra attempts instead of failing the resolver (`9b534db`).
- **Pictures:** stored as WebP no larger than they are shown, with variants encoded once and
  served immutable. Image jobs record created, started and finished times, so queue wait and
  paint time can now be measured.
- **Observability:** `pg_stat_statements`, phase timings, hedge-twin records, the upstream
  provider in traces, and four benches to re-run:
  - `api_bench.py --inprocess`, which counts queries;
  - `beat_bench.py --verify-reads`;
  - `page-bench.mjs`, with `--rested` and `--memory`;
  - `llm_usage_report.py`.

## Open (ranked)

**Update (2026-10-08, later):** items 1 and 4 were done (`crowd-reactions-001`, `summary-tags-001`), and items 2, 3 and 6 are in `perf-reads-001`. Items 2 and 3 were shipped, and item 6 (SSE) was studied and deferred with a design.

1. **Reactions grow with the square of a crowd.** Everyone present reacts to every attempt:
   about 465 reaction calls in a 25-character beat, each a paid model call in live play.
   Capping reactors (the addressee plus N nearest bystanders) is a story-quality change. It
   needs a decision and a scorecard run before and after: about 3 scenarios × 3 runs, roughly
   $0.40–0.80 with the current model.
2. **About 7 per-character reads per call remain** (observations, memories, relationships,
   intention). Sharing them needs in-beat writes to update the shared view.
3. **Observations accumulate with story length.** The salient set (about 7% of rows) has no
   window; re-check past 1,000 beats.
4. **Live-check the summary cap.** One paid playtest to the first day-end, about $0.04–0.05,
   confirms the new 1,536 cap.
5. ~~**Watch idle polling.**~~ Done after this write-up: a quiet, unchanged story now reads only presentation and autoplay on an idle tick; while a turn runs or autoplay plays, the feed still reads every tick.
6. **Push instead of poll (SSE).** Only worth it with many viewers; the ETag revalidation
   covers one player.

## Decided against (with reasons, in each worker's folder)

- **uvloop / httptools:** no gain above noise.
- **Reordering prompts for the cache:** +2–4 points; see `prefix_eval`.
- **Turning off the DB pre-ping:** it saves 110 ms a beat but breaks the first request after a
  DB restart.
- **Caching map, config and hooks across a whole beat:** stale after mid-beat commits; per
  phase only.
- **New indexes:** EXPLAIN at 300x found none missing.
- **Background test-DB drops:** no gain under shared load.

## How to re-measure

```bash
# pages (production build)
npx vite build --outDir "$TEMP/ev-build" && npx vite preview --port 5181 --outDir "$TEMP/ev-build"
node scripts/page-bench.mjs --runs 3 --idle 10 [--rested --idle 70] [--memory 30]
# API reads (export WORLDSIM_SECURITY__API_KEY alone)
backend/.venv/Scripts/python.exe backend/scripts/api_bench.py --story <world_id> --n 20 [--inprocess]
# beats (fake model, throwaway DB; see the script's docstring)
backend/.venv/Scripts/python.exe backend/scripts/beat_bench.py --help
# model spend from the dev DB (read only)
backend/.venv/Scripts/python.exe backend/scripts/llm_usage_report.py
```
