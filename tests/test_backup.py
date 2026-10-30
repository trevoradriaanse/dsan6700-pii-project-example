import sqlite3

import pytest

from needtoknow import backup, migrate, store


def test_a_backup_holds_the_counts_and_a_restore_brings_them_back(tmp_path):
    db, copy = str(tmp_path / "n.db"), str(tmp_path / "backups" / "copy.db")
    migrate.up(db)
    store.record(db, "regex", 3)
    store.record(db, "regex", 2)
    assert backup.backup(db, copy)["documents"] == 2
    store.record(db, "regex", 7)                         # counted after the backup
    assert store.stats(db)["documents"] == 3
    backup.restore(copy, db)
    assert store.stats(db)["documents"] == 2             # back to the backup: the third count is lost
    assert store.schema_version(db) == len(migrate.available())


def test_a_backup_taken_while_writes_are_pending_is_whole(tmp_path):
    db, copy = str(tmp_path / "n.db"), str(tmp_path / "copy.db")
    migrate.up(db)
    writer = store.connect(db)                           # an open connection, like the app's, with changes in the -wal
    writer.execute("INSERT INTO usage_by_detector (day, detector, documents, items) VALUES ('2026-10-30', 'regex', 5, 9)")
    writer.commit()
    assert backup.backup(db, copy) == {"schema": len(migrate.available()), "documents": 5}
    writer.close()


def test_a_damaged_copy_is_refused_before_anything_is_replaced(tmp_path):
    db, bad = str(tmp_path / "n.db"), tmp_path / "bad.db"
    migrate.up(db)
    store.record(db, "regex", 1)
    bad.write_bytes(b"not a database at all" * 100)
    with pytest.raises(SystemExit):
        backup.restore(str(bad), db)
    assert store.stats(db)["documents"] == 1             # untouched
    assert sqlite3.connect(db).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
