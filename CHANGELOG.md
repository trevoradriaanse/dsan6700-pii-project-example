# Changelog

What changed in each release, for the people who deploy and use Need to Know. Versions follow semantic versioning:
MAJOR.MINOR.PATCH, where a new feature raises MINOR and a fix raises PATCH (before 1.0, anything may still change).

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
