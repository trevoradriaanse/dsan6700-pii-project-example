#!/usr/bin/env bash
# Copy the usage counts out of the app's volume, safely, while the app keeps running:
#   scripts/backup.sh        ->  backups/needtoknow-2026-10-30T150405Z.db, in this folder, on this machine
# A copy on this machine is lost with this machine. Copy it somewhere else too, for example from your laptop:
#   scp exouser@<instance>:needtoknow-l8/backups/needtoknow-2026-10-30T150405Z.db .
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="needtoknow-$(date -u +%Y-%m-%dT%H%M%SZ).db"
docker compose exec -T app python -m needtoknow.backup "/data/backups/${NAME}"
mkdir -p backups
docker compose cp "app:/data/backups/${NAME}" "backups/${NAME}"
echo "saved backups/${NAME}"
