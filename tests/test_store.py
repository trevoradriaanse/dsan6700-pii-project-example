import sqlite3

from fastapi.testclient import TestClient

from needtoknow import migrate, store
from needtoknow.api.main import app
from needtoknow.config import settings


def test_migrations_apply_once_in_order(tmp_path, capsys):
    path = str(tmp_path / "n.db")
    migrate.up(path)
    assert store.schema_version(path) == len(migrate.available())
    migrate.up(path)                                    # a second run changes nothing
    assert "nothing to do" in capsys.readouterr().out


def test_a_database_with_data_is_backed_up_before_a_migration(tmp_path, monkeypatch):
    path = str(tmp_path / "n.db")
    migrate.up(path)
    store.record(path, "regex", 4)
    newest = migrate.available()[-1]
    monkeypatch.setattr(migrate, "available", lambda: [newest, (newest[0] + 1, "9999_test.sql", "CREATE TABLE t (x)")])
    migrate.up(path)
    (backup,) = (tmp_path / "backups").iterdir()
    assert sqlite3.connect(backup).execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == newest[0]


def test_a_failed_migration_leaves_nothing_behind(tmp_path, monkeypatch):
    path = str(tmp_path / "n.db")
    migrate.up(path)
    before = store.schema_version(path)
    monkeypatch.setattr(migrate, "available", lambda: [(before + 1, "9999_bad.sql", "CREATE TABLE t (x); SELECT nope")])
    try:
        migrate.up(path)
    except SystemExit:
        pass
    con = sqlite3.connect(path)
    assert store.schema_version(path) == before
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name = 't'").fetchall()


def test_each_document_is_counted_and_nothing_else_is_kept(counting, sample_pdf):
    with TestClient(app) as client:
        assert client.get("/api/stats").json()["documents"] == 0
        client.post("/api/detect", files={"file": ("lease.pdf", sample_pdf, "application/pdf")})
        r = client.get("/api/stats")
        assert r.json()["documents"] == 1 and r.json()["items_found"] > 0
        assert r.headers["cache-control"] == "public, max-age=60"
    dump = "\n".join(sqlite3.connect(counting).iterdump())
    assert "123-45-6789" not in dump and "lease.pdf" not in dump


def test_not_ready_on_an_old_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "empty.db"))
    with TestClient(app) as client:
        r = client.get("/ready")
        assert r.status_code == 503 and "migrate up" in r.json()["detail"]
