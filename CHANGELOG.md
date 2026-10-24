# Changelog

What changed in each release, for the people who deploy and use Need to Know. Versions follow semantic versioning:
MAJOR.MINOR.PATCH, where a new feature raises MINOR and a fix raises PATCH (before 1.0, anything may still change).

## [0.8.0] - 2026-10-24

### Added
- A front door: [Caddy](https://caddyserver.com) answers at `NTK_DOMAIN` on ports 80 and 443, gets the HTTPS
  certificate for that name on its own, and passes each request to the app (`Caddyfile`). It is off unless `.env`
  says `COMPOSE_PROFILES=proxy`. Over plain http, an uploaded PDF and everything we find in it cross the network
  readable; over https, they don't.

### Changed
- `APP_BIND` chooses the address the app's port is published on (`0.0.0.0` by default). Behind Caddy, set it to
  `127.0.0.1` so the only way in from outside is the front door.
- The GLiNER weights are pinned to one commit on Hugging Face (`NTK_GLINER_REVISION`), as `uv.lock` pins our
  packages. Before, a new upload under the same model name would have changed what runs.
- The Dockerfile's base images (`python`, `uv`) are pinned by digest, and Caddy's image too.

### Note for whoever deploys
- Behind Caddy, every request reaches the app from Caddy's address. Set `FORWARDED_ALLOW_IPS=*` so the app reads
  the client's address from the `X-Forwarded-For` header Caddy adds (Caddy replaces any copy the client sent), and
  the rate limit counts each client again. This is safe only with `APP_BIND=127.0.0.1`: anyone who can reach the
  app's port directly could write that header themselves.

## [0.7.0] - 2026-10-24

### Added
- `GET /admin/stats`: every day's counts per detector, the schema version and the migration backups, for whoever
  runs the service. It asks for the key in `NTK_ADMIN_API_KEY`, sent as an `X-Admin-Key` header (a wrong or missing
  key gets 401), and answers 404 when no key is set. It is not in the API docs, which alone would hide nothing.
- A limit on uploads per client: `/api/detect` and `/api/redact` allow `NTK_RATE_LIMIT_PER_MINUTE` requests a minute
  from one address (30 by default, 0 turns it off). Over it, the answer is `429 Too Many Requests` with a
  `Retry-After` header that says how many seconds to wait. Each copy of the app counts on its own.

### Changed
- `scripts/deploy.sh` now pins the image by digest: `.env` gets `ghcr.io/...needtoknow@sha256:...`, the exact
  image it pulled, instead of the tag we asked for. A tag moved later can no longer change what runs.
- CI and the release workflow use each GitHub Action by full commit SHA, with its release in a comment, so a tag
  moved in the action's repository can't change what runs with our token.

### Note for whoever deploys
- The admin route is off until you set `NTK_ADMIN_API_KEY` in `.env` (make one with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`) and restart.
- `NTK_RATE_LIMIT_PER_MINUTE` defaults to 30. Through Docker on the same machine, every local client arrives from
  the bridge gateway's address, so they share one limit.

## [0.6.0] - 2026-10-15

### Removed
- Migration `0003_drop_usage.sql` drops the old `usage` table. The code is the same as v0.5.0.

### Note for whoever deploys
- After this migration, v0.3.0 and v0.4.0 can no longer count documents (they write the dropped table). Roll back
  only as far as v0.5.0, or restore the backup the migration made: stop the app, copy
  `/data/backups/needtoknow-...-before-0003.db` over `/data/needtoknow.db`, remove the `-wal` and `-shm` files, then
  deploy v0.4.0. Counts recorded since the backup are lost.

## [0.5.0] - 2026-10-15

### Changed
- Only the per-detector table is written. The old `usage` table is no longer read or written by this version.

### Note for whoever deploys
- Rolling back to v0.4.0 is safe. Rolling back to v0.3.0 shows the counts as they were when v0.4.0 was replaced.

## [0.4.0] - 2026-10-15

### Added
- Counts per detector (`by_detector` in `/api/stats`), so detectors can be compared after a switch. Migration
  `0002_usage_by_detector.sql` adds a table and copies the counts so far into it as `regex`.

### Note for whoever deploys
- This version writes both the old table and the new one, so rolling back to v0.3.0 loses nothing.

## [0.3.0] - 2026-10-15

### Added
- Usage counts: documents checked and items found per day, shown on the page and at `GET /api/stats`. Numbers only:
  never the document, its name, or the text found. Stored in SQLite at `NTK_DB_PATH` (a volume, `/data`).
- Migrations: numbered SQL files applied once, in order, by `python -m needtoknow.migrate up`, which backs up the
  database first. `scripts/deploy.sh` runs them with the new image before restarting.
- `/ready` answers 503 while the database is older than this version needs.

## [0.2.1] - 2026-10-15

### Fixed
- A release now gives the tested image a second name and checks that its digest is unchanged. Before, `v0.2.0` was
  a new manifest list wrapping the tested image, with a digest of its own.

## [0.2.0] - 2026-10-15

### Added
- Releases: pushing a tag `vX.Y.Z` gives the image CI already tested from that commit a version name.
- `scripts/deploy.sh` accepts a release (`v0.2.0`), a commit (`sha-1a2b3c4`) or a digest (`@sha256:...`), and exits
  with a different code for each kind of failure.
- `scripts/prune.sh` lists (and with `--yes` removes) old images, keeping the ones we may roll back to.
- The page answers `304 Not Modified` when the browser already has it.

### Changed
- CI tests on Python 3.12 and 3.13, caches downloaded packages, and cancels an older run on the same pull request.
- A script requested with an old version in its address is no longer cached for a year.

## [0.1.0] - 2026-10-13

### Added
- Find personal information in a PDF, review it, and download a redacted copy (regex detector).
- CI publishes an image for every commit on `main` that passes the tests; `scripts/deploy.sh` deploys and rolls back.
