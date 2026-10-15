"""One-off task: bring the usage database up to date. Run it in the same image and settings as the app:

    docker compose run --rm app python -m needtoknow.migrate status
    docker compose run --rm app python -m needtoknow.migrate up

Each file in needtoknow/migrations (0001_usage.sql, 0002_...) is applied once, in order, in its own transaction,
together with a row in schema_migrations that says it was. Before changing a database that already has data, it
copies it to backups/ next to it. The app never migrates itself: two copies starting at once would both try.
"""

import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from needtoknow.config import settings
from needtoknow.store import connect, schema_version

LEDGER = ("CREATE TABLE IF NOT EXISTS schema_migrations "
          "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")


def available() -> list[tuple[int, str, str]]:
    found = [f for f in files("needtoknow").joinpath("migrations").iterdir() if f.name.endswith(".sql")]
    return [(int(f.name[:4]), f.name, f.read_text()) for f in sorted(found, key=lambda f: f.name)]


def backup(path: str, before: int) -> Path:
    db = Path(path)
    stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    dest = db.parent / "backups" / f"{db.stem}-{stamp}-before-{before:04d}.db"
    dest.parent.mkdir(exist_ok=True)
    with closing(connect(path)) as src, closing(sqlite3.connect(dest)) as dst:
        src.backup(dst)   # a consistent copy, even while the app is writing
    return dest


def up(path: str) -> None:
    current = schema_version(path)
    pending = [m for m in available() if m[0] > current]
    if not pending:
        print(f"schema is at {current}: nothing to do")
        return
    if current > 0:
        print(f"backed up to {backup(path, pending[0][0])}")
    with closing(connect(path)) as con:
        con.isolation_level = None            # we say where each transaction begins and ends
        con.execute(LEDGER)
        for version, name, sql in pending:
            try:
                con.execute("BEGIN")
                for statement in sql.split(";"):  # our migrations keep ";" out of comments and strings
                    if statement.strip():
                        con.execute(statement)
                con.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)",
                            (version, name, datetime.now(UTC).isoformat(timespec="seconds")))
                con.execute("COMMIT")
            except sqlite3.Error as exc:
                con.execute("ROLLBACK")       # the migration and its ledger row, or neither
                sys.exit(f"{name} failed, nothing from it was applied: {exc}")
            print(f"applied {name}")
    print(f"schema is at {schema_version(path)}")


def status(path: str) -> None:
    current = schema_version(path)
    for version, name, _ in available():
        print(f"{'applied' if version <= current else 'pending'}  {name}")
    print(f"schema is at {current}")


def main() -> None:
    if not settings.db_path:
        sys.exit("NTK_DB_PATH is not set: there is no database to migrate")
    {"up": up, "status": status}[sys.argv[1] if len(sys.argv) > 1 else "status"](settings.db_path)


if __name__ == "__main__":
    main()
