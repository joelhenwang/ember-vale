# perf-infra-001: API image, server process, Postgres and the developer loop

**Question.** How long do builds, container starts and checks take, and what can be made
faster now or kept from getting slower later?

**Setup.** 2026-10-08, Windows 11 with Docker Desktop (14 CPUs, 11.4 GiB to the VM).
- Image runs used a separate container (`ev-bench`, port 8104) on the compose network, so
  the shared API on 8101 was untouched.
- The read benchmark is `backend/scripts/api_bench.py` (n=40, Mara's story).
- Load runs are 600 requests at concurrency 16.
- Every pair ran twice, interleaved. Other workers were benchmarking at the same time, so
  expect about ±25% noise on latency.

## 1. API image: build context, layer order, entrypoint

| | before | after |
|---|---|---|
| build context sent to Docker | **~4.3 GB** (whole repo: local-models 2.4 GB, launcher/target 1.1 GB, backend/.venv 332 MB, .git 233 MB, node_modules 157 MB, **.env**) | 32 kB code + content (allow-list `.dockerignore`) |
| rebuild, no change | 27 s | **2 s** |
| rebuild after a code change | 36 s (`COPY src` before `uv sync` reinstalled every dependency) | **7 s** (deps layer from the lock alone, then the project) |
| container start to `/health/live` | 19.3 s / 18.2 s | **7.4 s / 8.5 s** |
| memory at idle | 144 MiB | **121 MiB** |
| image size | 460 MB | 506 MB (+46 MB of precompiled bytecode, which buys the start-up time) |
| request latency (read bench p50) | same within noise | same within noise |

Start-up was slow because the entrypoint ran `uv run` twice, which re-resolves and checks
the project on every container start, and because nothing was precompiled. The venv is
now on PATH and called directly, and `UV_COMPILE_BYTECODE=1` compiles once at build time.

## 2. Server process: uvloop and httptools

The same image was run with uvloop and httptools added (uvicorn picks them up
automatically). Requests per second at concurrency 16, two runs each:

| route | asyncio + h11 | uvloop + httptools |
|---|---|---|
| /health/live | 201, 247 | 193, 220 |
| /library/presets | 74, 87 | 97, 99 |
| /world/presentation | 22, 34 | 23, 30 |

There is no consistent win: run-to-run noise is larger than the effect. **Not adopted.**
The ceiling is the work done per request, not the event loop:
- Health is only ~200–250 req/s, so every request pays ~4–5 ms of fixed overhead.
- **Two `BaseHTTPMiddleware` layers** (ApiKeyMiddleware, RequestIdMiddleware) each add a
  task and stream wrappers per request.
- **Recommendation (HTTP layer owner):** rewrite both as pure ASGI middleware.

One worker process is right for now. The autoplay runner and image runner start in the
app lifespan, so more uvicorn workers would duplicate them. Scaling out later needs those
runners moved to their own process, or a leader lease, first.

## 3. Postgres

- `pg_stat_statements` is now preloaded (compose `command`). The extension is created by
  `backend/docker/initdb/10-pg-stat-statements.sql` on fresh volumes; it was created by hand
  on the dev volume. The db restart took 3 s and the API reconnected (`pool_pre_ping`).
- `database.statement_timeout_ms` existed but was never applied. It is now sent on every app
  connection (`server_settings`). The default went from 5 s to **60 s**:
  - it is a backstop for runaway queries and stuck locks;
  - lock waits count toward it, and beats hold row locks;
  - reads take 5–50 ms;
  - migrations use their own engine.
  - The test checks that the setting is applied and that it cuts a 2 s `pg_sleep`.
- Dev config: `shared_buffers` 128 MB, max_connections 100, and the database is 100 MB. The
  app pool is 5 + overflow 10 per process. No change was needed.
- Biggest tables: `recall_vector` 43 MB (heap only 2.6 MB, the rest is index and TOAST),
  `model_call` 12 MB and `context_manifest` 11 MB, both of which store the full prompt
  JSON. `model_call` has no index on `world_id`, `phase_run_id` or `created_at`, which is a
  note for the DB owner if the cost and report queries become routine.
- **53 scratch test databases** have leaked from interrupted runs (`worldsim_stage0_*`,
  about 8–23 MB each). It is safe to drop them when no test run is active, but an automatic
  sweep could kill a concurrent session's template, so none was added.

## 4. Developer loop

| check | time |
|---|---|
| pytest `-n 4`, full suite | 400 s under concurrent load from other workers (CLAUDE.md says ~2m40s when idle) |
| vitest run | 10.0 s |
| vue-tsc --noEmit | 15.5 s |
| eslint . | 12.3 s |

The slowest tests are a few 10–29 s simulations and migration-history tests (e.g.
`test_long_talk_is_noticed…` 28.8 s, `test_every_call_gets_a_cost_row` 16.3 s).
Per-test **setup and teardown reach 7–9 s under load**.

**Measured, not adopted.** On an idle server, `DROP DATABASE … WITH (FORCE)` takes
1.0–1.6 s and `CREATE … TEMPLATE` (WAL_LOG) 0.1–0.4 s; FILE_COPY is slower, 1.3–1.8 s.
- `synchronous_commit=off` on scratch DBs: 5.1 → 3.3 ms per commit.
- Moving the drops to a background thread plus `synchronous_commit=off`, A/B on a
  DB-heavy subset of 6 files, 4 interleaved runs: new 84 / 60 s vs old 65 / 64 s.
- That is no measurable gain under the shared load, so it was reverted.

**CI** already caches npm (`setup-node cache`) and uv (`setup-uv enable-cache`).
- Added: the frontend job now runs `vite build`. CLAUDE.md makes it required, because only
  the bundler catches handlers that prettier breaks.
- Not changed: GitHub service containers cannot take a `command`, so CI Postgres keeps
  fsync on.

## Verdict

- **Adopted:**
  - the `.dockerignore` allow-list;
  - dependency-first layers with a uv cache mount;
  - bytecode compiled at build, and no `uv run` at start;
  - pg_stat_statements;
  - statement_timeout applied (60 s);
  - the CI vite build.
- **Not adopted, measured:**
  - uvloop and httptools;
  - deferred scratch drops and `synchronous_commit=off` in tests.
- **For other owners:**
  - pure-ASGI middleware;
  - lifespan runners must leave the API process before it can run more than one worker;
  - indexes on `model_call` if reports run often;
  - a manual scratch-DB cleanup.
