import json

from fastapi.testclient import TestClient

from needtoknow.api.main import app


def test_health_and_ready():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json()["status"] == "ready"


def test_detect_then_redact(sample_pdf):
    with TestClient(app) as client:
        r = client.post("/api/detect", files={"file": ("lease.pdf", sample_pdf, "application/pdf")})
        assert r.status_code == 200
        findings = r.json()["findings"]
        assert any(f["text"] == "123-45-6789" for f in findings)
        remove = json.dumps([{"page": f["page"], "text": f["text"]} for f in findings])
        r = client.post("/api/redact", files={"file": ("lease.pdf", sample_pdf, "application/pdf")}, data={"remove": remove})
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert b"123-45-6789" not in r.content


def test_rejects_what_is_not_a_pdf():
    with TestClient(app) as client:
        r = client.post("/api/detect", files={"file": ("notes.docx", b"PK\x03\x04 not a pdf", "application/octet-stream")})
        assert r.status_code == 415
