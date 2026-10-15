"""Usage counts: how many documents were checked and how many items were found, per day.

Never the document, its name, or any text found in it. Off when NTK_DB_PATH is empty (tests, development).
Only numbered migrations change the tables (needtoknow/migrations), applied by `python -m needtoknow.migrate up`.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime

SCHEMA_REQUIRED = 1   # the newest migration this code needs; /ready refuses to be ready on an older database


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=5)
    con.execute("PRAGMA journal_mode=WAL")   # readers do not wait for a writer
    return con


def schema_version(path: str) -> int:
    with closing(connect(path)) as con:
        try:
            return con.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        except sqlite3.OperationalError:     # no ledger yet: nothing has been applied
            return 0


def record(path: str, detector: str, items: int) -> None:
    day = datetime.now(UTC).date().isoformat()
    with closing(connect(path)) as con, con:  # one transaction
        con.execute("INSERT INTO usage (day, documents, items) VALUES (?, 1, ?) "
                    "ON CONFLICT (day) DO UPDATE SET documents = documents + 1, items = items + excluded.items",
                    (day, items))


def stats(path: str) -> dict:
    with closing(connect(path)) as con:
        since, documents, items = con.execute(
            "SELECT MIN(day), COALESCE(SUM(documents), 0), COALESCE(SUM(items), 0) FROM usage").fetchone()
    return {"since": since, "documents": documents, "items_found": items}
