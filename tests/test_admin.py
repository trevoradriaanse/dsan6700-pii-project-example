import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from needtoknow.api.main import app
from needtoknow.config import settings

KEY = "test-key-not-a-real-one"


@pytest.fixture
def admin_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", SecretStr(KEY))


def test_admin_stats_is_left_out_of_the_docs(admin_key):
    with TestClient(app) as client:
        assert "/admin/stats" not in client.get("/openapi.json").json()["paths"]


def test_admin_stats_needs_the_key(admin_key):
    with TestClient(app) as client:
        r = client.get("/admin/stats")
        assert r.status_code == 401 and "X-Admin-Key" in r.json()["detail"]
        assert client.get("/admin/stats", headers={"X-Admin-Key": "guess"}).status_code == 401


def test_admin_stats_with_the_key(admin_key, counting, sample_pdf):
    with TestClient(app) as client:
        client.post("/api/detect", files={"file": ("lease.pdf", sample_pdf, "application/pdf")})
        r = client.get("/admin/stats", headers={"X-Admin-Key": KEY})
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert r.json()["days"][0]["documents"] == 1 and r.json()["schema_version"] >= 2


def test_admin_routes_are_off_without_a_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", SecretStr(""))   # the default
    with TestClient(app) as client:
        assert client.get("/admin/stats", headers={"X-Admin-Key": ""}).status_code == 404
        assert client.get("/admin/stats").status_code == 404
