#!/bin/sh
# Ember Vale backups: the database and the painted pictures, on your disk.
#
# Runs as the compose `backup` service (Postgres image: pg_dump, tar).
# A backup is a folder ./backups/<UTC stamp>/ holding database.dump
# (pg_dump custom format), pictures.tar.gz (the generated-art volume) and
# stories.txt (how many stories it holds). The folders live on the host,
# outside Docker's volumes, so `docker compose down -v` cannot take them.
#
#   backup.sh loop              back up when the newest is older than
#                               BACKUP_EVERY_HOURS (default 24), then every
#                               BACKUP_EVERY_HOURS; keep BACKUP_KEEP (7)
#   backup.sh now               one backup now
#   backup.sh list              the backups, newest first, with story counts
#   backup.sh restore <stamp|latest>
#                               replace the database and pictures with that
#                               backup (stop the api first: scripts/restore-backup.sh)
#
# The database is dumped first, then the pictures, so the archive covers
# every picture the dump refers to: the picture sweep deletes only files
# that were already unused one sweep (6 hours) earlier, never one that a
# row referred to a moment ago.
# Pruning never removes the newest backup that holds any story, so a wiped
# database followed by a week of empty backups cannot rotate the last good
# one away (the 2026-10-08 wipe had no backup at all).
set -eu

BACKUPS=/backups
PICTURES=/generated
KEEP=${BACKUP_KEEP:-7}
EVERY=${BACKUP_EVERY_HOURS:-24}
export PGHOST=${PGHOST:-db} PGUSER=${POSTGRES_USER:-embervale}
export PGPASSWORD=${POSTGRES_PASSWORD:-changeme-local-only}
DB=${POSTGRES_DB:-embervale}

log() { echo "[backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

stamps() { ls -1 "$BACKUPS" 2>/dev/null | grep -E '^[0-9]{8}-[0-9]{6}$' | sort -r || true; }

stories_in() { cat "$BACKUPS/$1/stories.txt" 2>/dev/null || echo 0; }

backup_now() {
  stamp=$(date -u +%Y%m%d-%H%M%S)
  part="$BACKUPS/.$stamp.partial"
  mkdir -p "$part"
  if pg_dump -d "$DB" -Fc -f "$part/database.dump" \
    && tar -C "$PICTURES" -czf "$part/pictures.tar.gz" . \
    && psql -d "$DB" -Atc "select count(*) from story_catalog" > "$part/stories.txt"; then
    mv "$part" "$BACKUPS/$stamp"
    log "saved $stamp ($(stories_in "$stamp") stories, $(du -sh "$BACKUPS/$stamp" | cut -f1))"
  else
    rm -rf "$part"
    log "FAILED; nothing kept for $stamp"
    return 1
  fi
  prune
}

prune() {
  protect=""
  for s in $(stamps); do
    if [ "$(stories_in "$s")" -gt 0 ]; then protect=$s; break; fi
  done
  n=0
  for s in $(stamps); do
    n=$((n + 1))
    if [ "$n" -gt "$KEEP" ] && [ "$s" != "$protect" ]; then
      rm -rf "${BACKUPS:?}/$s"
      log "pruned $s"
    fi
  done
}

age_hours() {
  newest=$(stamps | head -n 1)
  [ -n "$newest" ] || { echo 99999; return; }
  then=$(date -u -d "$(echo "$newest" | sed -E 's/(....)(..)(..)-(..)(..)(..)/\1-\2-\3 \4:\5:\6/')" +%s)
  echo $(( ($(date -u +%s) - then) / 3600 ))
}

restore() {
  want=${1:-latest}
  [ "$want" = latest ] && want=$(stamps | head -n 1)
  dir="$BACKUPS/$want"
  [ -n "$want" ] && [ -f "$dir/database.dump" ] || { log "no backup '$1'"; exit 1; }
  log "restoring $want ($(stories_in "$want") stories)"
  dropdb --force --if-exists --maintenance-db=postgres "$DB"
  createdb --maintenance-db=postgres "$DB"
  pg_restore -d "$DB" --no-owner "$dir/database.dump"
  find "$PICTURES" -mindepth 1 -delete
  tar -C "$PICTURES" -xzf "$dir/pictures.tar.gz"
  log "restored $want"
}

case "${1:-loop}" in
  now) backup_now ;;
  list)
    for s in $(stamps); do
      echo "$s  $(stories_in "$s") stories  $(du -sh "$BACKUPS/$s" | cut -f1)"
    done
    ;;
  restore) shift; restore "${1:-latest}" ;;
  loop)
    until pg_isready -q -d "$DB"; do sleep 2; done
    if [ "$(age_hours)" -ge "$EVERY" ]; then backup_now || true; else log "newest backup is recent; next in ${EVERY}h"; fi
    while true; do
      sleep $((EVERY * 3600))
      backup_now || true
    done
    ;;
  *) echo "usage: backup.sh loop|now|list|restore <stamp|latest>"; exit 2 ;;
esac
