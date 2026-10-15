"""Usage counts: how many documents were checked and how many items were found, per day and detector.

Never the document, its name, or any text found in it. Off when NTK_DB_PATH is empty (tests, development).
Only numbered migrations change the tables (needtoknow/migrations), applied by `python -m needtoknow.migrate up`.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime

SCHEMA_REQUIRED = 2   # the newest migration this code needs; /ready refuses to be ready on an older database


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
    with closing(connect(path)) as con, con:  # one transaction: both tables or neither
        con.execute("INSERT INTO usage_by_detector (day, detector, documents, items) VALUES (?, ?, 1, ?) "
                    "ON CONFLICT (day, detector) DO UPDATE "
                    "SET documents = documents + 1, items = items + excluded.items", (day, detector, items))
        # Still written, so that rolling back to v0.3.0 (which reads only this table) loses nothing.
        con.execute("INSERT INTO usage (day, documents, items) VALUES (?, 1, ?) "
                    "ON CONFLICT (day) DO UPDATE SET documents = documents + 1, items = items + excluded.items",
                    (day, items))


def stats(path: str) -> dict:
    with closing(connect(path)) as con:
        rows = con.execute("SELECT detector, MIN(day), SUM(documents), SUM(items) "
                           "FROM usage_by_detector GROUP BY detector").fetchall()
    return {"since": min((r[1] for r in rows), default=None),
            "documents": sum(r[2] for r in rows), "items_found": sum(r[3] for r in rows),
            "by_detector": {r[0]: {"documents": r[2], "items_found": r[3]} for r in rows}}
