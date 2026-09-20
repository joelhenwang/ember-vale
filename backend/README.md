# Backend (vendored worldsim engine)

Coherent subsystem vendored from `joelhenwang/pixelsaga` @ full SHA
`653614d2840c8746b1ed215049a6ee78de0fb0d1` (branch
`feat/ember-vale-integration`; the earlier handoff pinned `785713d`).
Read-only source; do not edit the engine's domain/application semantics to
rename things.

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
- `backend/migrations` — 31 Alembic revisions (`0001`–`0031`).
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
