#!/usr/bin/env bash
# Put a backup of the usage counts back (counts recorded after that backup are lost):
#   scripts/restore.sh                                            the newest copy in backups/
#   scripts/restore.sh backups/needtoknow-2026-10-30T150405Z.db   that copy
# The app is stopped while the database is replaced, then started again. Afterwards: scripts/smoke.sh <port>.
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:-$(ls -t backups/*.db 2>/dev/null | head -1)}"
[ -n "${FILE}" ] || { echo "no backup given, and none in backups/" >&2; exit 1; }
FILE="$(realpath "${FILE}")"
echo "restoring ${FILE}"
docker compose stop app
docker compose run --rm --no-deps -v "${FILE}:/restore/backup.db:ro" app \
  python -m needtoknow.backup --restore /restore/backup.db
docker compose up -d app
