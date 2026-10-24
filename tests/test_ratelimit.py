from fastapi.testclient import TestClient

from needtoknow.api.main import app
from needtoknow.config import settings


def upload(client, pdf):
    return client.post("/api/detect", files={"file": ("lease.pdf", pdf, "application/pdf")})


def test_the_31st_upload_in_a_minute_waits(monkeypatch, sample_pdf):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 30)
    with TestClient(app, client=("203.0.113.7", 50000)) as one, TestClient(app, client=("203.0.113.8", 50000)) as other:
        assert all(upload(one, sample_pdf).status_code == 200 for _ in range(30))
        r = upload(one, sample_pdf)
        assert r.status_code == 429 and "too many" in r.json()["detail"]
        assert 1 <= int(r.headers["retry-after"]) <= 60
        assert upload(other, sample_pdf).status_code == 200       # another client has a limit of its own


def test_redact_counts_against_the_same_limit(monkeypatch, sample_pdf):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    with TestClient(app) as client:
        assert upload(client, sample_pdf).status_code == 200
        r = client.post("/api/redact", files={"file": ("lease.pdf", sample_pdf, "application/pdf")}, data={"remove": "[]"})
        assert r.status_code == 429


def test_zero_turns_the_limit_off(monkeypatch, sample_pdf):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 0)
    with TestClient(app) as client:
        assert all(upload(client, sample_pdf).status_code == 200 for _ in range(40))


def test_clients_gone_quiet_are_forgotten(monkeypatch):
    from needtoknow import ratelimit

    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    window = ratelimit.SlidingWindow()
    for i in range(100):
        window.check(f"10.0.0.{i}", 30)
    now[0] += 61                        # a minute later, one new request sweeps out the others
    window.check("10.0.0.200", 30)
    assert list(window.hits) == ["10.0.0.200"]
