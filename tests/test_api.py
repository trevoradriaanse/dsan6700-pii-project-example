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


def test_download_name_is_safe_for_any_file_name(sample_pdf):
    remove = json.dumps([{"page": 0, "text": "123-45-6789"}])
    with TestClient(app) as client:
        r = client.post("/api/redact", files={"file": ("Łukasz 李.pdf", sample_pdf, "application/pdf")}, data={"remove": remove})
        assert r.status_code == 200
        assert 'filename="_ukasz__-redacted.pdf"' in r.headers["content-disposition"]


def test_refuses_an_oversized_upload_before_reading_it():
    with TestClient(app) as client:
        r = client.post("/api/detect", content=b"x", headers={"content-length": str(50 * 1024 * 1024)})
        assert r.status_code == 413
