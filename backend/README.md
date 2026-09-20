# Backend (vendored worldsim engine)

Coherent subsystem vendored from `joelhenwang/pixelsaga` @ `653614d`
(branch `feat/ember-vale-integration`; plan pinned `785713d`). Read-only
source; do not edit the engine's domain/application semantics to rename things.

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
