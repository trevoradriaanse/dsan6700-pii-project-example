"""One-off task: copy the usage counts to a file, or put such a copy back. Run it in the same image as the app:

    docker compose exec app python -m needtoknow.backup /data/backups/needtoknow-2026-10-30.db    (app running)
    docker compose run --rm app python -m needtoknow.backup --restore /restore/backup.db           (app stopped)

Copying needtoknow.db with cp while the app is writing to it can give a broken copy: SQLite keeps the newest changes
in a separate -wal file until it folds them in. SQLite's own backup reads one consistent snapshot instead. A copy
that stays on this machine is lost with this machine, so scripts/backup.sh also brings it out of the volume, from
where it can go somewhere else.
"""

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from needtoknow.config import settings
from needtoknow.store import connect


def check(path: str) -> dict:
    """What a copy holds, after making sure it is a whole, readable SQLite database. A copy never changes, so it is
    opened as immutable: read-only, with no lock files next to it (it may sit on a read-only mount)."""
    with closing(sqlite3.connect(f"file:{path}?immutable=1", uri=True)) as con:
        try:
            result = con.execute("PRAGMA integrity_check").fetchone()[0]
            version = con.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
            documents = con.execute("SELECT COALESCE(SUM(documents), 0) FROM usage_by_detector").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            sys.exit(f"{path} is not a usable copy of the counts: {exc}")
    if result != "ok":
        sys.exit(f"{path} is damaged: {result}")
    return {"schema": version, "documents": documents}


def backup(db: str, dest: str) -> dict:
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(db)) as src, closing(sqlite3.connect(dest)) as out:
        src.backup(out)                     # a consistent snapshot, even while the app is writing
    return check(dest)


def restore(src: str, db: str) -> dict:
    found = check(src)                      # refuse a broken copy before touching the database
    for leftover in (db + "-wal", db + "-shm"):
        Path(leftover).unlink(missing_ok=True)   # changes from after the backup must not be folded back in
    with closing(sqlite3.connect(f"file:{src}?immutable=1", uri=True)) as inp, closing(sqlite3.connect(db)) as out:
        inp.backup(out)
    return found


def main() -> None:
    if not settings.db_path:
        sys.exit("NTK_DB_PATH is not set: there is no database to back up or restore")
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--restore":
        found = restore(args[1], settings.db_path)
        print(f"restored {args[1]}: schema {found['schema']}, {found['documents']} documents counted")
    elif len(args) == 1:
        found = backup(settings.db_path, args[0])
        print(f"backed up to {args[0]}: schema {found['schema']}, {found['documents']} documents counted")
    else:
        sys.exit("usage: python -m needtoknow.backup <copy.db> | --restore <copy.db>")


if __name__ == "__main__":
    main()
