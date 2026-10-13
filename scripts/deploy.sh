#!/usr/bin/env bash
# Deploy (or roll back to) one image that CI built: scripts/deploy.sh sha-1a2b3c4
# Pins APP_IMAGE in .env, pulls, restarts, and counts the deploy only when /ready reports that commit.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:?usage: scripts/deploy.sh <tag, e.g. sha-1a2b3c4>}"
IMAGE="ghcr.io/trevoradriaanse/needtoknow:${TAG}"
PORT="$(grep -E '^APP_PORT=' .env | cut -d= -f2)"; PORT="${PORT:-8000}"
PREVIOUS="$(grep -E '^APP_IMAGE=' .env | cut -d= -f2 || true)"

if grep -qE '^APP_IMAGE=' .env; then sed -i "s|^APP_IMAGE=.*|APP_IMAGE=${IMAGE}|" .env; else echo "APP_IMAGE=${IMAGE}" >> .env; fi
docker compose pull app
docker compose up -d --no-build app

WANT="${TAG#sha-}"
for _ in $(seq 1 60); do
  GOT="$(curl -s "localhost:${PORT}/ready" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("commit",""))' 2>/dev/null || true)"
  if [ "${GOT:0:7}" = "${WANT:0:7}" ]; then
    echo "$(date -u +%FT%TZ) $(whoami) deployed ${IMAGE} $(docker image inspect -f '{{index .RepoDigests 0}}' "${IMAGE}")" | tee -a deploy.log
    exit 0
  fi
  sleep 2
done
echo "FAILED: /ready did not report ${WANT} within 120 s." >&2
echo "$(date -u +%FT%TZ) $(whoami) FAILED ${IMAGE}" >> deploy.log
[ -n "${PREVIOUS}" ] && echo "To roll back: scripts/deploy.sh ${PREVIOUS##*:}" >&2
exit 1
