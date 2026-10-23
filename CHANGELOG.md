# Changelog

What changed in each release, for the people who deploy and use Need to Know. Versions follow semantic versioning:
MAJOR.MINOR.PATCH, where a new feature raises MINOR and a fix raises PATCH (before 1.0, anything may still change).

## [Unreleased]

### Changed
- `scripts/deploy.sh` now pins the image by digest: `.env` gets `ghcr.io/...needtoknow@sha256:...`, the exact
  image it pulled, instead of the tag we asked for. A tag moved later can no longer change what runs.

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
