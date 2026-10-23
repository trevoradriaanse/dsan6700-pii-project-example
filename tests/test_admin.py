from fastapi.testclient import TestClient

from needtoknow.api.main import app


def test_admin_stats_is_left_out_of_the_docs_but_still_answers(counting, sample_pdf):
    with TestClient(app) as client:
        client.post("/api/detect", files={"file": ("lease.pdf", sample_pdf, "application/pdf")})
        assert "/admin/stats" not in client.get("/openapi.json").json()["paths"]
        r = client.get("/admin/stats")       # no key, no login: hidden is not private
        assert r.status_code == 200
        assert r.json()["days"][0]["documents"] == 1 and r.json()["schema_version"] >= 2
