#!/usr/bin/env bash
# Put a backup back: the database and the painted pictures.
#
#   scripts/restore-backup.sh            list the backups
#   scripts/restore-backup.sh latest     restore the newest
#   scripts/restore-backup.sh <stamp>    restore that one (e.g. 20261009-030000)
#
# Everything since that backup is replaced. The API stops while it runs and
# starts again after. A backup of the current state is taken first, so a
# restore can itself be undone.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -eq 0 ]; then
  docker compose run --rm -T backup list
  exit 0
fi
echo "Backing up the current state first..."
docker compose run --rm -T backup now
docker compose stop api worker >/dev/null 2>&1 || docker compose stop api
docker compose run --rm -T backup restore "$1"
docker compose start api
echo "Restored $1. The API is starting again."
