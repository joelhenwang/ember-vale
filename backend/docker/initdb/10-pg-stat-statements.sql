-- Query statistics for performance work (docs/evidence/perf-infra-001).
-- Runs once, on a fresh volume; compose.yaml preloads the library.
-- An existing volume needs this once by hand (it is idempotent):
--   docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/10-pg-stat-statements.sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
