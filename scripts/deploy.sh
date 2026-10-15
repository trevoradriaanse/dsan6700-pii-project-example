#!/usr/bin/env bash
# Deploy (or roll back to) one image that CI built and tested:
#   scripts/deploy.sh v0.2.0           a release
#   scripts/deploy.sh sha-1a2b3c4      any commit CI published
#   scripts/deploy.sh @sha256:9f2c...  one exact image, by digest
# The deploy counts only when /ready reports the commit the image was built from.
# Exit codes: 1 usage, 2 the image could not be pulled, 3 a migration failed, 4 /ready never reported that commit.
set -euo pipefail
cd "$(dirname "$0")/.."
REF="${1:?usage: scripts/deploy.sh <v0.2.0 | sha-1a2b3c4 | @sha256:...>}"
REPO="ghcr.io/trevoradriaanse/needtoknow"
case "${REF}" in
  @*) IMAGE="${REPO}${REF}" ;;
  *)  IMAGE="${REPO}:${REF}" ;;
esac
PORT="$(grep -E '^APP_PORT=' .env | cut -d= -f2 || true)"; PORT="${PORT:-8000}"
PREVIOUS="$(grep -E '^APP_IMAGE=' .env | cut -d= -f2 || true)"
log() { echo "$(date -u +%FT%TZ) $(whoami) $*" | tee -a deploy.log; }

# 1. Make sure we have the image before touching anything. An image already on the instance (like the one we are
#    rolling back to) needs no network at all; otherwise pull it. A typo fails here, and the running app and .env
#    stay as they were.
if ! docker image inspect "${IMAGE}" >/dev/null 2>&1 && ! docker pull -q "${IMAGE}"; then
  log "FAILED ${IMAGE}: could not pull it"
  exit 2
fi
# The image itself says which commit it was built from (a label CI sets), whatever name we used to ask for it.
WANT="$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "${IMAGE}")"
DIGEST="$(docker image inspect -f '{{index .RepoDigests 0}}' "${IMAGE}")"

# 2. Migrate the database with the NEW image, as a one-off task, while the old version is still serving. So every
#    migration must keep the old version working (add, never rename or drop in the same release). Images from
#    before the usage counts have no migrations to run.
if docker run --rm --entrypoint python "${IMAGE}" -c 'import importlib.util as u, sys; sys.exit(u.find_spec("needtoknow.migrate") is None)'; then
  if ! APP_IMAGE="${IMAGE}" docker compose run --rm --no-deps app python -m needtoknow.migrate up; then
    log "FAILED ${IMAGE}: migration"
    exit 3
  fi
fi

# 3. Pin the new image and restart. Compose replaces the container only if the image changed.
if grep -qE '^APP_IMAGE=' .env; then sed -i "s|^APP_IMAGE=.*|APP_IMAGE=${IMAGE}|" .env; else echo "APP_IMAGE=${IMAGE}" >> .env; fi
docker compose up -d --no-build app

# 4. Wait until the app says it is running that commit.
for _ in $(seq 1 60); do
  GOT="$(curl -s "localhost:${PORT}/ready" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("commit",""))' 2>/dev/null || true)"
  if [ "${GOT}" = "${WANT}" ]; then
    log "deployed ${IMAGE} ${DIGEST} commit ${WANT}"
    exit 0
  fi
  sleep 2
done
log "FAILED ${IMAGE}: /ready did not report commit ${WANT} within 120 s"
BACK="${PREVIOUS#"${REPO}"}"; BACK="${BACK#:}"     # "sha-1a2b3c4" or "@sha256:..."
[ -n "${BACK}" ] && echo "To roll back: scripts/deploy.sh ${BACK}" >&2
exit 4
