#!/usr/bin/env bash
# Free disk space without losing a rollback. Lists the Need to Know images on this instance that we would remove:
# everything except the one running now and the last KEEP images deployed (from deploy.log).
#   scripts/prune.sh          list only
#   scripts/prune.sh --yes    remove them
# `docker image prune -a` would remove every image no container is using, including the ones we roll back to.
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP=3
REPO="ghcr.io/trevoradriaanse/needtoknow"
RUNNING="$(grep -E '^APP_IMAGE=' .env | cut -d= -f2 || true)"
RECENT="$(grep ' deployed ' deploy.log 2>/dev/null | awk '{print $4}' | tac | awk '!seen[$0]++' | head -n "${KEEP}")"
keep_ids="$(for ref in ${RUNNING} ${RECENT}; do docker image inspect -f '{{.Id}}' "${ref}" 2>/dev/null || true; done | sort -u)"

docker image ls "${REPO}" --format '{{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}' | while read -r id ref size; do
  full="$(docker image inspect -f '{{.Id}}' "${id}")"
  if grep -qx "${full}" <<< "${keep_ids}"; then
    echo "keep    ${ref} ${size}"
  elif [ "${1:-}" = "--yes" ]; then
    docker image rm "${ref}" >/dev/null && echo "removed ${ref} ${size}"
  else
    echo "remove  ${ref} ${size}"
  fi
done
