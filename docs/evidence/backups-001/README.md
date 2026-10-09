# backups-001: backups of the database and the pictures (2026-10-09)

**Question.** On 2026-10-08 at 15:05 the dev database and picture volumes were deleted and recreated, and every story was lost with no way back. Backup/restore (plan packet E9: "a database backup must include asset storage and be restore-tested") was not built.

**What changed.**
- **`backend/docker/backup/backup.sh`**, run by a new compose service `backup` on the same Postgres image. It writes `./backups/<UTC stamp>/` on the host disk, outside Docker's volumes, so `docker compose down -v` cannot remove it. Each backup holds:
  - `database.dump`: `pg_dump`, custom format;
  - `pictures.tar.gz`: the generated-art volume;
  - `stories.txt`: how many stories it holds.

  The database goes first and the pictures second. Pictures only accumulate, so the archive covers every picture the dump refers to.
- **When it runs:** at start, when the newest backup is at least a day old, then every 24 hours (`BACKUP_EVERY_HOURS`).
- **Retention:** the newest 7 are kept (`BACKUP_KEEP`). The newest backup that holds any story is never pruned, so a wiped database followed by a week of empty backups cannot rotate the last good one away.
- **`scripts/restore-backup.sh [latest|<stamp>]`:**
  1. backs up the current state first, so a restore can be undone;
  2. stops the API;
  3. drops and recreates the database and restores the dump;
  4. replaces the pictures;
  5. starts the API again.

  With no argument it lists the backups.
- `./backups/` is gitignored. The launcher runs `docker compose up -d`, so the service starts with the game.

**Restore test** (the plan's bar; nothing live was overwritten). The script was copied into throwaway containers whose volumes were named volumes:
1. A real backup of the dev database and pictures: 2 stories, 1.9 MB.
2. A restore into a scratch database (`embervale_restoretest`) and a scratch picture volume.

| | Original | Restored |
|---|---|---|
| Stories | 2 | 2 |
| Events | 32 | 32 |
| Scene pictures | 5 | 5 |
| Assets | 15 | 15 |
| Presets | 5 | 5 |
| Schema | 0057_image_job_claims | 0057_image_job_claims |
| Picture files | 14 | 14, md5-identical |

The app, started in-process on the restored database, listed both stories and served the watched story's presentation (turn 14, 4 pictures, its cast).

The test also caught a bug before it shipped: `dropdb`/`createdb` take `--maintenance-db`, not `-d`.

**Pruning test.** With 9 empty backups, one older backup holding 5 stories and today's backup: the newest 7 were kept, the 3 oldest empty ones were pruned, and the older 5-story backup survived.

**Live, after the file-sharing fix** (later on 2026-10-09). Docker Desktop had dropped the project folder from Settings → Resources → File Sharing, so every bind mount hung and later failed with "not shared from the host". With the folder shared again:
- `docker compose up -d backup` started the service, and it saved `20261009-082318` (2 stories, 1.9 MB) at once.
- `scripts/restore-backup.sh latest` ran the real path:
  1. it backed up the current state (`20261009-082350`);
  2. it stopped the API;
  3. it restored the database and pictures;
  4. it started the API, which came back healthy.
- Before and after: 2 stories, 32 events, 5 pictures.
- `scripts/restore-backup.sh` with no argument lists both backups.
