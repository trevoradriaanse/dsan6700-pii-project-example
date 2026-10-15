# Need to Know: runbook

For someone who was not in the room: how to release, deploy, check, and roll back Need to Know, and what to do when it
breaks. Every command is run on the instance from `~/needtoknow` unless it says otherwise.

## What runs where

- **One container**, `app`, on the team's Jetstream2 instance, started by Docker Compose from `~/needtoknow`. It serves
  the page and the API on port 8000 (the only published port).
- **The image** comes from GitHub. Every push to `main` that passes the tests is built once and pushed to
  `ghcr.io/trevoradriaanse/needtoknow`, tagged `sha-` plus the first 7 characters of the commit. A release tag
  (`v0.6.0`) is a second name for one of those images; it is never rebuilt.
- **State:**
  - Documents: none. Each request reads the PDF in memory and forgets it.
  - Usage counts: `/data/needtoknow.db` in the `data` volume, numbers per day and detector only. Backups made before
    each migration are in `/data/backups/`.
  - Model weights: the `models` volume.
  - Settings: `~/needtoknow/.env`.

## Before you start

1. SSH access to the instance, and the repository cloned at `~/needtoknow`.
2. If the package is private, a GitHub classic token with `read:packages`:
   `docker login ghcr.io -u <github-user>` (paste the token). Run `docker logout ghcr.io` when you are done.
3. What to deploy: a release (`v0.6.0`, from CHANGELOG.md) or a commit (`sha-1a2b3c4`, from the Actions run summary).
   Read that version's "Note for whoever deploys" in CHANGELOG.md first.

## Release (on your laptop)

1. Raise `version` in `pyproject.toml`, run `uv lock`, and add a section to `CHANGELOG.md`.
2. Merge, and wait for CI on that commit to be green.
3. Tag it and push the tag:
   ```bash
   git tag -a v0.6.0 -m v0.6.0 && git push origin v0.6.0
   ```
   You should see a green "Release" run whose summary names the `sha-` image it promoted, with one digest for both.

## Deploy

```bash
cd ~/needtoknow && git pull            # the scripts and compose.yml; the code itself comes in the image
scripts/deploy.sh v0.6.0
```

The script pulls the image (if it is not here already), runs any database migrations with the new image, pins it in
`.env`, restarts, and waits for `/ready`. It counts only when it prints `deployed ...`. Every attempt is written to
`deploy.log`. If it fails, the exit code says where:

| Exit | What failed | What is running now |
|---|---|---|
| 2 | Pulling the image (a typo, or not logged in) | The old version; `.env` unchanged |
| 3 | A migration (the message names the file) | The old version; the database as it was |
| 4 | `/ready` never reported the new commit | The new container, not ready: roll back, then read `docker compose logs app` |

## Check it worked

```bash
curl -s localhost:8000/ready           # {"status":"ready", ..., "version":"0.6.0", "commit":"1a2b3c4"}
scripts/smoke.sh                       # finds a phone number in a sample lease, checks it was counted, redacts it
```

Then open the page in a browser, upload `scripts/smoke-lease.pdf`, and download the redacted copy.

## Roll back

Run the deploy script with the previous version (the last `deployed` line in `deploy.log` before this one). The old
image is still on the instance, so a rollback needs no network:

```bash
scripts/deploy.sh v0.5.0
scripts/smoke.sh
```

A rollback changes the code, not the data. Before rolling back past a release, read its "Note for whoever deploys" in
CHANGELOG.md. **After v0.6.0's migration, do not roll back to v0.4.0 or earlier**: they write a table that no longer
exists, `/ready` still says ready, and `smoke.sh` fails with "the document was not counted". If you must go back that
far, restore the backup.

## Restore the counts from a backup (cannot be undone)

This replaces the database with the copy made before a migration. Counts recorded since that copy are lost.

1. Find the backup: `docker compose run --rm app ls -l /data/backups`
2. Stop the app: `docker compose stop app`
3. Copy it into place (use the file name from step 1):
   ```bash
   docker compose run --rm app sh -c 'cp /data/backups/needtoknow-20261015T210000Z-before-0003.db /data/needtoknow.db && rm -f /data/needtoknow.db-wal /data/needtoknow.db-shm'
   ```
4. Deploy the version that matches that schema (for `before-0003`, v0.5.0 or v0.4.0): `scripts/deploy.sh v0.5.0`

## One-off tasks

Run them in the same image and settings as the app, then let the container go away:

```bash
docker compose run --rm app python -m needtoknow.migrate status   # which migrations are applied
docker compose run --rm app python -m needtoknow.prefetch         # download model weights before switching detector
```

## Free disk space

```bash
docker system df
scripts/prune.sh                       # lists what it would remove: all but the running image and the last 3 deployed
scripts/prune.sh --yes
```

Do not use `docker image prune -a`: it removes every image no container is using, including the ones you roll back to.

## Gotchas, in the order they will bite you

1. **`denied` or `unauthorized` when pulling**: the image is private; log in to ghcr.io with a classic token that has
   `read:packages`.
2. **The first CI push fails with `permission_denied`**: an image pushed by hand earlier is not linked to this
   repository; in the package's settings, under Manage Actions access, add the repository with write access.
3. **`port is already allocated`**: another copy is running; `docker compose ps` and stop the old one.
4. **`/ready` answers 503 "the database schema is at ..."**: someone ran `docker compose up` instead of `deploy.sh`;
   run `docker compose run --rm app python -m needtoknow.migrate up`.
5. **`/ready` never reports the new commit**: `docker compose logs app`; a model-based detector downloads its weights
   on first start (run the prefetch task first).
6. **The page looks unchanged after a deploy**: check `/ready` first; if the commit is new, the browser is showing a
   cached copy, so reload.
7. **The address changed**: unshelving gives the instance a new public IP; update `USER_BRIEF.md`.

## Who to call

The team member who owns deployment this week (see the pinned issue "Deploy rota"), then the rest of the team in the
team channel.
