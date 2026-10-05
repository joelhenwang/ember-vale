# Backend (vendored worldsim engine)

Coherent subsystem vendored from `joelhenwang/pixelsaga` @ full SHA
`653614d2840c8746b1ed215049a6ee78de0fb0d1` (branch
`feat/ember-vale-integration`; the earlier handoff pinned `785713d`).
Originally read-only; Ember Vale now carries engine fixes in `backend/src`
(narrator validation and repair, orchestration timing, reliability fixes).
They are candidates for upstreaming; keep the internal `worldsim` names.

Provenance note: `git diff 785713dcf6fd4c071b04944469c5cbbb56a628bc..653614d`
over `backend/` + `content/` is EMPTY — the I00–I08b commits between the two
revisions touched only `frontend/`, `docs/`, `evidence/` and `mocks/`, none of
which were vendored. The vendored engine content is therefore identical at
both revisions; the newer SHA was recorded because it is the donor branch tip.
No deliberate engine fixes were made during vendoring — only environment
adaptations live outside `backend/src` (compose ports/database/volume,
`.gitignore`, dev proxy). PixelSaga's frontend, CSS, router, App, AGENTS.md
and static-mock approval process were not imported.

Vendored paths (kept aligned so the Dockerfile's `/app` layout resolves like
a repo-root checkout):

- `backend/src/worldsim` — domain, application, infrastructure, interfaces
  (FastAPI `create_app`, CLI `serve`, 16 HTTP route groups under `/api/v1`).
- `backend/migrations` — Alembic revisions (`0001`–`0040` at the time of writing).
- `backend/prompts` — versioned role prompts.
- `backend/scripts` — contract/client generators.
- `content/` — seeds, definitions, dnd tables, schemas, visual styles.
- `backend/pyproject.toml`, `backend/uv.lock`, `backend/alembic.ini`,
  `backend/pyrightconfig.json`, `backend/Dockerfile`.

Excluded from the copy: `__pycache__`, `.venv`, `.pytest_cache`, `.ruff_cache`,
PixelSaga frontend, AGENTS.md, repo-level instructions.

Ember Vale owns: `compose.yaml` (isolated DB/volume/ports), `.env.example`,
vite `/api` proxy, `src/api/` client. API projections for Ember Vale arrive in
E2; the engine's internal package name (`worldsim`) is kept.

## Development checks

Run from `backend/` (CI runs exactly these, see `.github/workflows/ci.yml`):

```bash
uv run ruff check . && uv run ruff format --check .
uv run basedpyright        # zero errors; strict for src, relaxed private/unknown rules for tests
uv run pytest -n 8         # routine suite in parallel (~2.5 min; ~9 min serially)
uv run pytest -m sim_gate -n 8   # multi-phase simulations (~8 min); CI runs these nightly
```

While iterating, run the affected test files directly (`uv run pytest
tests/test_x.py`); run the parallel routine suite before committing.
Tests are parallel-safe: every database test clones its own scratch
database from a migrated template, namespaced per xdist worker. More than
about 8 workers is slower locally (the database becomes the bottleneck).

Tests need Postgres with an explicit URL. Do not source the repo `.env`
wholesale: it selects the live OpenRouter provider. Export only the URL:

```bash
export WORLDSIM_DATABASE__URL="$(grep '^WORLDSIM_DATABASE__URL=' ../.env | cut -d= -f2-)"
```

Without it, settings fall back to `localhost:5432` and every database test
times out (the compose database listens on 5433).

Tests never modify tracked files by default. Evidence bundles go to a
scratch directory; `WORLDSIM_WRITE_EVIDENCE=1` regenerates the committed
bundles under `evidence/`, `WORLDSIM_WRITE_FIXTURES=1` the narrator fixture.
