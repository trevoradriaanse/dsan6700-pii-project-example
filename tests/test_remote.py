import httpx
import pytest
from fastapi.testclient import TestClient

from needtoknow.api.main import app
from needtoknow.config import settings
from needtoknow.detectors import remote
from needtoknow.detectors.remote import DetectorUnavailable, RemoteDetector, with_retries
from needtoknow.detectors.service import app as detector_app


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Retries wait between tries; the tests record the waits instead of sleeping through them."""
    waits: list[float] = []
    monkeypatch.setattr(remote.time, "sleep", waits.append)
    return waits


def answers(*statuses: int):
    """A client whose server answers with these statuses, in order, and counts the calls."""
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(statuses[len(calls) - 1], json={"detector": "regex", "spans": []})

    return httpx.Client(transport=httpx.MockTransport(handle), base_url="http://detector"), calls


def test_a_503_is_tried_again_and_then_works(no_waiting):
    client, calls = answers(503, 200)
    assert with_retries(lambda: client.post("/detect")).status_code == 200
    assert len(calls) == 2 and len(no_waiting) == 1 and 0.25 <= no_waiting[0] <= 0.75   # 0.5 s, with jitter


def test_a_4xx_is_not_tried_again():
    client, calls = answers(422, 200)
    with pytest.raises(httpx.HTTPStatusError):
        with_retries(lambda: client.post("/detect"))
    assert len(calls) == 1


def test_three_failed_connections_and_we_give_up(no_waiting):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://detector")
    with pytest.raises(DetectorUnavailable, match="ConnectError on all 3 tries"):
        with_retries(lambda: client.post("/detect"))
    assert len(no_waiting) == 2 and 0.5 <= no_waiting[1] <= 1.5   # then 1 s, with jitter


def test_the_detector_service_finds_spans_in_text():
    with TestClient(detector_app) as client:
        assert client.get("/ready").json()["detector"] == "regex"
        spans = client.post("/detect", json={"text": "SSN: 123-45-6789"}).json()["spans"]
        assert [s["text"] for s in spans] == ["123-45-6789"]


def test_the_api_and_the_detector_service_together(sample_pdf, monkeypatch):
    monkeypatch.setattr(settings, "detector_url", "http://detector")
    with TestClient(detector_app) as detector, TestClient(app) as client:
        app.state.detector.client = detector   # the API's calls go to the detector app, in this process
        r = client.post("/api/detect", files={"file": ("lease.pdf", sample_pdf, "application/pdf")})
    assert r.status_code == 200 and r.json()["detector"] == "regex"
    assert any(f["text"] == "123-45-6789" for f in r.json()["findings"])


def test_the_page_hears_when_the_detector_is_down(sample_pdf, monkeypatch):
    monkeypatch.setattr(settings, "detector_url", "http://127.0.0.1:9")   # nothing listens there
    with TestClient(app) as client:
        assert isinstance(app.state.detector, RemoteDetector)
        r = client.post("/api/detect", files={"file": ("lease.pdf", sample_pdf, "application/pdf")})
    assert r.status_code == 503 and "not answering" in r.json()["detail"]
