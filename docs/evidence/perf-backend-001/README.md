# perf-backend-001: backend read paths, HTTP and the database

**Question.** How fast are the reads that the player and library screens make? Where does the time go,
and how do those reads hold up as a story grows from tens of turns to thousands?

**Verdict.** The read paths ran queries per row: the stories list, the chronicle and the presentation's
scene pictures. Once batched, every read stays flat up to a 300x longer story (9,000 events). The
presentation is polled while a turn is pending. At 300x it went from 765 ms (178 queries) to 100 ms
(17 queries), and the chronicle from 1.7 s (528 queries) to 60 ms (8 queries). JSON is now gzipped,
and pictures are cached by the browser for good.

## Setup

- `backend/scripts/api_bench.py`. Read-only: it never advances, paints or writes. It times the
  requests that Adventure, Home and the Library make, against Mara's player story
  (`bdea0982…`, 30 events, 18 scenes, 3 pictures).
  - `--inprocess` builds the app in the same process against a database URL. It also counts SQL
    statements (`before_cursor_execute`) and pool checkouts (one per unit of work) per request.
- `backend/scripts/bench_amplify.py` makes one story K times longer in a database whose name must end
  in `_bench`. It copies the story's history into its past with fresh ids and moves the clock on.
  The bench database is a `pg_dump` copy of the dev database, so dev data is never touched:

  ```bash
  docker compose exec -T db sh -c 'dropdb -U embervale_app --if-exists embervale_bench &&
    createdb -U embervale_app embervale_bench &&
    pg_dump -U embervale_app embervale | psql -q -U embervale_app embervale_bench'
  python scripts/bench_amplify.py --db .../embervale_bench --world <id> --times 10   # x10
  python scripts/bench_amplify.py --db .../embervale_bench --world <id> --times 10   # x100
  python scripts/bench_amplify.py --db .../embervale_bench --world <id> --times 3    # x300
  ```

  At 300x the story has 9,000 events, 5,400 scenes, 8,100 narration beats, 9,600 observations and
  900 pictures.
- `backend/scripts/query_profile.py` times each statement of one request, slowest first.
- Machine: Windows host, Postgres in Docker. From the host each round trip costs about 1–1.5 ms;
  inside the API container it is a fraction of that. Absolute numbers carry noise, because other work
  ran on the machine at the same time. **Query counts and the interleaved A/B below are the robust
  measures**, not single latencies.

## Results

### A/B: old code against new code, interleaved in the same time window

The old code is a worktree at `50d143f` (before these commits) and the new code is HEAD. Three rounds
each, run alternately, n=15 per endpoint per round; the medians of the rounds are shown. In-process.
Raw files are in `data/{dev,bench}-{old,new}-{1,2,3}.json`.

Today's size (x1):

| endpoint | p50 old | p50 new | queries old → new | sessions old → new |
|---|---:|---:|---:|---:|
| stories list | 433 ms | 20 ms | 81 → 3 | 41 → 1 |
| chronicle (100) | 536 ms | 50 ms | 168 → 8 | 2 → 1 |
| presentation | 89 ms | 60 ms | 30 → 17 | 2 → 1 |
| map | 39 ms | 37 ms | 5 → 3 | 2 → 2 |
| suggestions | 47 ms | 40 ms | 10 → 8 | 1 → 1 |
| others (presets, items, autoplay, character…) | about the same | about the same | unchanged | unchanged |

300x longer story (9,000 events):

| endpoint | p50 old | p50 new | p95 old | p95 new | queries old → new |
|---|---:|---:|---:|---:|---:|
| stories list | 536 ms | 26 ms | 615 ms | 32 ms | 81 → 3 |
| chronicle (100) | 1,725 ms | 60 ms | 2,296 ms | 73 ms | 528 → 8 |
| presentation | 765 ms | 100 ms | 1,035 ms | 130 ms | 178 → 17 |
| map | 41 ms | 27 ms | 66 ms | 36 ms | 5 → 3 |

### Scaling with the batched reads (before the presentation fixes)

p50 latency by story size:

| endpoint | x1 | x10 | x100 | x300 |
|---|---:|---:|---:|---:|
| stories list | 18 | 20 | 14 | 13 |
| chronicle (100) | 37 | 34 | 49 | 43 |
| presentation | 48 | 46 | 63 | **133** (p95 358) |
| map | 20 | 15 | 21 | 19 |
| suggestions | 29 | 19 | 23 | 20 |

The presentation was the only read that grew. Per-statement timing at 300x showed where:

- `journey_counts`, 20 ms. It aggregates the player's whole history: places, people and deeds. An
  index does not help, because the cost is in aggregating 3,300 rows, not in finding them.
  - Fix: cache the counts per (story, player, newest event sequence) in `AppState.journeys`.
  - Every scene commit appends an event in the same transaction, so the key moves exactly when the
    counts can change.
  - `world.version` would not be a safe key: not every scene commit saves the world row.
- Scene pictures, 8 ms. All 900 were loaded to keep the newest 40. Fix: `list_recent_for_world`
  walks `ix_scene_picture_world` backwards with `LIMIT 40`.
- After the fixes, at 300x the request takes 81 → 40 ms in total, and SQL 47 → 19 ms. The remaining
  SQL is about 17 round trips of roughly 1 ms each from the host.

### What was batched

| place | before | after |
|---|---|---|
| stories list | per story: new session, catalog, world, clock, role grant | one session; `worlds.get_many`, `roles.get_for_worlds` |
| chronicle | per event: narration query, plus the run's scenes with participants and intents | `narrations_for_events`, `scene_ids_for_events` (2 queries per page) |
| presentation scene art | per picture: scene (3 queries), job, repaint job | `participants_for_scenes`, `assets.get_jobs` |
| `characters.list_for_world` | 1 + one per character | one join (the beat engine uses it too) |
| `scenes.list_for_run` | 1 + 2 per scene | 3 in total |
| role lookups on polled routes | a second session per request | in the request's own session |

### Pool checkouts

`pool_pre_ping` costs extra per checkout: 300 checkouts of `select 1` (`tmp/ping.py`):

| where | pre_ping on | pre_ping off |
|---|---:|---:|
| Windows host → Docker DB | 5.2–6.2 ms | 2.7–3.7 ms |
| inside the API container | 1.8–2.8 ms | 1.1–1.6 ms |

Pre-ping stays on, because it keeps the API working through a database restart. The fix was fewer
checkouts instead: hot routes look up the role in the session they already hold.

### HTTP

`GZipMiddleware` is outermost; it applies to bodies over 1 KB, and pictures and event streams are
excluded. Sizes on the wire:

| response | raw | gzipped |
|---|---:|---:|
| chronicle, 100 entries (x1) | 14.8 KB | 3.6 KB |
| story drafts | 12.7 KB | 1.5 KB |
| presentation (x1) | 3.1 KB | 1.4 KB |
| chronicle, 100 entries (x300) | 49.9 KB | 7.0 KB |

Pictures (`/assets/{id}`, `/library/assets/{id}/bytes`):
- They now carry `Cache-Control: private, max-age=31536000, immutable` and an ETag. The bytes behind
  an asset id never change: a new painting gets a new asset id.
- A request with `If-None-Match` gets a 304, but only after the perspective check. A player holding an
  ETag still gets 403 for a face they may not see (tested in `test_revamp_p04`).
- The Vite proxy passes the headers through unchanged.

### Indexes

`EXPLAIN (ANALYZE, BUFFERS)` at 300x found no hot statement missing an index. Every per-request
statement uses an index or reads a few rows. The one sequential scan, in `journey_counts`, is now
behind the cache. **No migration was needed.**

`pg_stat_statements` is available but not loaded. It needs `shared_preload_libraries`, which means a
change to the db service's compose command and a restart.

## Left for later

- **The client reads the chronicle oldest-first.** `useAdventure.readChronicle` pages 50 entries per
  request and 20 pages per read. On a 9,000-event story, Adventure needs about nine reads to reach the
  newest turn when it opens. The server side is cheap (60 ms per 100-entry page at 300x). The fix
  belongs in the client: read the tail first, for example `after = watermark - N`, then backfill
  older entries on scroll.
- `database.statement_timeout_ms` (5000) is defined in settings but never applied to connections.
  `connect_args={"server_settings": {"statement_timeout": ...}}` would guard against runaway queries.
  First check that the beat engine's commits and recall queries stay well under the limit on long
  stories.
- Enable `pg_stat_statements` in compose for ongoing profiling.
- Python per request is about 5 ms of CPU (Pydantic validation and SQLAlchemy compilation). It is not
  worth touching until round trips stop dominating.
