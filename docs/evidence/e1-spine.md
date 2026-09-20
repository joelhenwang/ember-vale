# E1 backend spine — evidence

Date: 2026-09-20. Vendored engine: PixelSaga @ `653614d` (read-only source).

## What was added (no UI redesign)

- `backend/` — coherent worldsim subsystem: `src/worldsim`, 31 Alembic
  migrations (`0001`–`0031`), `prompts`, `scripts`, `pyproject.toml`,
  `uv.lock`, `alembic.ini`, `Dockerfile`. Internal package name kept.
- `content/` — seeds, definitions, dnd tables, schemas, visual styles.
- `backend/README.md` — provenance + excluded paths.
- `compose.yaml` — isolated stack: db `embervale` on host port 5433, volume
  `pgdata-embervale`, api on host port 8101. Separate from any PixelSaga install.
- `.env.example` (+ local untracked `.env` with dev-only API key for the
  compose public bind; health probes stay exempt).
- `vite.config.ts` — dev proxy `/api` → `http://localhost:8101`.
- `src/api/client.ts` — URL joining, readiness envelope, error shape; full DTOs
  come from the generated contract in E2.
- `src/api/api-client.spec.ts` — 4 tests (durable collateral for the spine).

## Live proof (this checkout, fresh empty DB)

- `docker compose up -d db` → healthy (pgvector pg16, `embervale`).
- `docker compose build api` → `ember-vale-api` built.
- `docker compose up -d api` → entrypoint ran `alembic upgrade head`, then serve.
- `GET :8101/api/v1/health/live` → `{"status":"ok"}`.
- `GET :8101/api/v1/health/ready` → `migration_head: 0031_settings_pipeline`,
  database ok, migrations ok, extensions ok (vector), model profile `active:fake`,
  seed `degraded` (`worlds:0` — expected pre-seed; E2 seeds starter presets).
- Vite proxy proof: `GET :5173/api/v1/health/live` → `{"status":"ok"}`.
- One wrinkle fixed: engine refuses `0.0.0.0` without
  `WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW=true` + API key; local `.env` supplies
  dev-only values (documented in `.env.example`).

## Gates

`vue-tsc --noEmit` pass, `eslint .` pass, `vitest run` 41/41 pass
(37 existing + 4 new `src/api/api-client.spec.ts`).

## Not yet (E2)

Starter seed (Ember Vale + Hearth/Market + Wren/Ash), generated TS contract,
story-draft atomic create, first committed turn, Home-on-real-catalog,
leave/reload/resume proof.
