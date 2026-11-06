# Changelog

What changed in each release, for the people who deploy and use Need to Know. Versions follow semantic versioning:
MAJOR.MINOR.PATCH, where a new feature raises MINOR and a fix raises PATCH (before 1.0, anything may still change).

## [0.10.1] - 2026-11-06

### Fixed
- The first refusal of each kind, after every restart, never showed up on the dashboard. A labeled count only exists
  from its first event on, so Prometheus first saw it at 1, with no earlier sample to count that 1 from. The app now
  creates every count it knows of (each refusal reason, each review decision, its detector) at 0 when it starts.

## [0.10.0] - 2026-11-06

### Added
- Logs as JSON, written with loguru: one object per line, each with a `request_id` and a `trace_id`, plus one line
  per request (method, path, status, milliseconds; not the caller's address). The request id is also sent back in
  the `X-Request-ID` header.
- `/metrics` for Prometheus: requests, errors and durations per route, and our own counts (documents checked,
  findings per page, detection time, uploads refused by reason, findings users removed or unchecked).
- Traces with OpenTelemetry: a span for each request, and for reading the PDF, detecting and redacting. Counts only.
- An `observability` profile in compose.yml: grafana/otel-lgtm, with Prometheus collecting `/metrics`, the
  Need to Know dashboard, and two alerts (uploads failing, the API not answering). Grafana is on port 3000 of the
  instance only.
- `scripts/locustfile.py`, a stepped load test that prints the uploads a second and p50/p95/p99 at each step.

### Changed
- `/health` answers on the event loop, so it no longer waits for a free worker thread behind slow uploads.
- The page tells the API how many findings the user unchecked before downloading (a count, nothing else).
- Each service's Docker logs are rotated (three files of 10 MB).
- uvicorn runs with `--reset-contextvars`, so a request never starts inside the previous one's trace.

### Fixed
- `.env.example`: the comment after the empty `DETECTOR_EXTRA=` was read as its value by Docker Compose, so
  `docker compose build` failed with "invalid reference format". The comment now has its own line.

### Note for whoever deploys
- Caddy now answers 404 for `/metrics`; restart it once: `docker compose up -d caddy --force-recreate`.
- To see the dashboards, add the two lines in the README's "Watch it run" section to `.env`.

## [0.9.0] - 2026-10-30

### Added
- `scripts/backup.sh` copies the usage counts out of the volume while the app keeps running, using SQLite's own
  backup (`python -m needtoknow.backup`), which reads one consistent snapshot. Copying the file with `cp` while the
  app writes to it can give a broken copy. `scripts/restore.sh` stops the app, checks that the newest copy in
  `backups/` (or the one named) is whole, puts it back, and starts the app again.

### Changed
- The page gives every request a 70-second limit (a little longer than Caddy's), and says what happened when one
  fails: the app is not answering (502 or 504), it didn't answer in time, or the app's own reason (415, 422, 429 with
  how long to wait, 503 while starting). Before, an error page without JSON, or an app that never answered, left "Reading the document..." on
  the page for good. Failure messages now show in the warning color; a CSS rule kept them grey before.
- Caddy stops waiting for the app after 60 seconds and answers `504 Gateway Timeout`. Before, a stuck app kept the
  user's request open as long as the app was stuck.

### Note for whoever deploys
- Caddy reads its Caddyfile when it starts, and deploy.sh restarts only the app: run `docker compose up -d caddy
  --force-recreate` once after this deploy.
- A backup on the instance is lost with the instance. Copy `backups/` somewhere else (for example `scp` it to your
  laptop), and keep a copy of `.env`, which is not in Git.

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
