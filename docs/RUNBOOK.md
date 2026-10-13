# Need to Know: runbook

For someone who was not in the room: how to deploy, check, and roll back Need to Know, and what to do when it breaks.

## What runs where

- **One container**, `app`, on the team's Jetstream2 instance, started by Docker Compose from `~/needtoknow`. It serves the page and the API on port 8000 (the only published port).
- **The image** comes from GitHub: every push to `main` that passes the tests is built once and pushed to `ghcr.io/trevoradriaanse/needtoknow`, tagged `sha-` plus the first 7 characters of the commit.
- **State**: none for documents (each request reads the PDF in memory and forgets it). One volume, `models`, caches model weights. Settings live in `~/needtoknow/.env`.

## Before you start

- SSH access to the instance, and the repository cloned at `~/needtoknow`.
- A GitHub token with `read:packages`, to pull private images: `docker login ghcr.io -u <github-user>` (paste the token), and `docker logout ghcr.io` when you are done.
- The tag to deploy, from the commit page or the Actions run summary, for example `sha-1a2b3c4`.

## Deploy

```bash
cd ~/needtoknow && git pull            # scripts and compose.yml; the code itself comes in the image
scripts/deploy.sh sha-1a2b3c4          # pins APP_IMAGE in .env, pulls, restarts, waits for /ready
```

The deploy counts only when the script prints `deployed ...`: that means `/ready` reported the commit we asked for. Every attempt is written to `deploy.log`.

## Check it worked

```bash
curl localhost:8000/ready              # {"status":"ready", ..., "commit":"1a2b3c4"}
scripts/smoke.sh                       # finds and removes a phone number in a sample lease
```

Then open the page in a browser, upload `scripts/smoke-lease.pdf`, and download the redacted copy.

## Roll back

Run the deploy script with the previous tag (the last `deployed` line in `deploy.log` before this one):

```bash
scripts/deploy.sh sha-0f9e8d7
```

A rollback changes the code, not the data. Need to Know keeps no documents, so the only thing a rollback cannot undo is a change to the model cache; if a new detector was added, its weights simply stay in the volume.

## One-off tasks

Run them in the same image and settings as the app, then let the container go away:

```bash
docker compose run --rm app python -m needtoknow.prefetch   # download model weights before switching detector
```

## Gotchas, in the order they will bite you

1. **`denied` when pulling**: the image is private; log in to ghcr.io with a token that has `read:packages`.
2. **`port is already allocated`**: another copy is running; `docker compose ps` and stop the old one.
3. **`/ready` never reports the new commit**: `docker compose logs app`; a model-based detector downloads its weights on first start (run the prefetch task first).
4. **The page looks unchanged after a deploy**: check `/ready` first; if the commit is new, the browser is showing a cached copy, so reload.
5. **The address changed**: unshelving gives the instance a new public IP; update `USER_BRIEF.md`.

## Who to call

The team member who owns deployment this week (see the pinned issue "Deploy rota"), then the rest of the team in the team channel.
