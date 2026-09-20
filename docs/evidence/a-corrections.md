# Delivery A — corrections evidence (lead review, 2026-09-20)

## A1. Database configuration consistency — done, proven

- `compose.yaml`: API URL now interpolates the configured username:
  `postgresql+asyncpg://${POSTGRES_USER:-embervale}:...@db:5432/${POSTGRES_DB:-embervale}`.
  Container address (`db:5432`) stays distinct from the host address
  (`localhost:5433`); both documented in `.env.example`.
- `.env.example`: bare `DATABASE_URL` removed; the typed
  `WORLDSIM_DATABASE__URL` host URL is supplied with a comment explaining that
  the backend/Alembic read only the typed key, plus how a host process loads
  it (`set -a; source .env; set +a`). Public-bind/API-key guard documented
  with copyable startup (root README has the full sequence); the guard itself
  is unchanged.
- Proof on a FRESH volume (`docker compose down -v`, recreated): with
  non-default `POSTGRES_USER=embervale_app`, db healthy, entrypoint migrated
  0001→0031, `psql: current_user=embervale_app, current_database=embervale`,
  `/health/ready` → database ok, migrations ok (`0031_settings_pipeline`),
  extensions ok, seed `degraded (worlds:0)`, model `active:fake`. No PixelSaga
  database touched (own `pgdata-embervale` volume, ports 5433/8101).

## A2. Readiness contract — done, tested

- `src/api/client.ts` realigned to the authoritative DTOs
  (`backend/.../interfaces/http/schemas.py`, `readiness.py`): top status
  `ready|degraded`, check status `ok|degraded|failed`, integer
  `schema_version`.
- `allChecksPass` is now positive: non-empty checks, every status exactly
  `ok`. `degraded`/`failed`/unknown all fail (covered per-status in tests).
- `seedStatus` exposes the world-count check as ADVISORY with a doc comment:
  `degraded` on an empty install must not block onboarding/preset
  selection/first-story creation; no fake seeding to turn it green.
- `modelProfileDetail` surfaces `model_profile` detail (e.g. `active:fake`)
  separately — readiness never claims live generation works.
- `src/api/client.contract.spec.ts`: 7 tests, all passing.

## A3. Backend regression coverage — done, runnable subset green

- `backend/tests/` + `fixtures/` vendored from donor HEAD
  `653614d2840c8746b1ed215049a6ee78de0fb0d1` (donor tree clean apart from
  untracked docs), excluding `__pycache__`. No environment changes needed:
  tests read `WORLDSIM_DATABASE__URL` and create/drop scratch databases on
  that server.
- Results against the compose db (host URL, `embervale_app`):
  - migrations + tx + seed + uow + task leases: **34 passed**
  - `test_stage0_foundation` (seed, fixed-key advance, fault-after-commit,
    restart, reconcile, same-key replay, fresh-key progress, consistency
    audit): **1 passed**, wrote `evidence/stage0-foundation-v1/`
  - `test_stage1_gate` + `test_scene_commit`: **8 passed, 1 skipped**
    (skip is the opt-in live-provider case; deprecation warning only)
  - wrote `evidence/stage1-three-phase-v1/`
- Engine still NOT declared verified beyond this: the subset covers
  migrations, atomic commit, idempotency, turn commit and reload; full-suite
  and live-provider paths remain for later packets.

## A4. Visual baseline — done

- `docs/evidence/e0-visual/`: 8 desktop (1440×900, full-page) shots — home,
  new-story cast, library characters, library worlds, stories, settings,
  character studio (Wren), world studio (Ember Vale) — plus 2 narrow
  (390×844): home, stories. Captured from unmodified Vue source over stable
  in-memory fixtures via Playwright/Chromium; no fake runtime data added.
- Home spot-checked: hero card, Begin-a-tale, library summary, recent stories
  all render as designed.

## Hygiene

- `backend/src/worldsim.egg-info` removed from git and disk; `*.egg-info`
  ignored. Root README gained the backend startup/migration/test section.
- Full donor SHA + empty-diff provenance recorded in `backend/README.md`.
