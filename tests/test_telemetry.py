import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from loguru import logger
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from needtoknow import telemetry
from needtoknow.api.main import app

PRIVATE = ["Maria", "555-0143", "123-45-6789"]   # the file name and two findings in the sample: none may leak


@pytest.fixture(scope="module")
def spans():
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


@pytest.fixture
def log_lines():
    """The same JSON lines the app writes to stdout, collected in a list for the test to read."""
    lines = []
    sink = logger.add(lambda message: lines.append(telemetry.as_json(message.record)), level="DEBUG")
    yield lines
    logger.remove(sink)


def test_metrics_count_documents_findings_and_refusals(sample_pdf):
    with TestClient(app) as client:
        client.post("/api/detect", files={"file": ("lease.pdf", sample_pdf, "application/pdf")})
        client.post("/api/detect", files={"file": ("notes.docx", b"PK\x03\x04", "application/octet-stream")})
        text = client.get("/metrics").text
    assert 'needtoknow_documents_checked_total{detector="regex"}' in text
    assert 'needtoknow_findings_per_page_count{detector="regex"}' in text
    assert 'needtoknow_detection_seconds_bucket{detector="regex",le="0.005"}' in text
    assert 'needtoknow_uploads_refused_total{reason="not_pdf"}' in text
    assert 'http_requests_total{handler="/api/detect",method="POST",status="2xx"}' in text


def test_every_known_series_starts_at_zero():
    with TestClient(app) as client:
        text = client.get("/metrics").text
    for reason in telemetry.REASONS:
        assert f'needtoknow_uploads_refused_total{{reason="{reason}"}}' in text
    for decision in telemetry.DECISIONS:
        assert f'needtoknow_findings_reviewed_total{{decision="{decision}"}}' in text
    assert 'needtoknow_documents_checked_total{detector="regex"}' in text


def test_every_refusal_reason_is_known():
    """A reason missing from REASONS would still be counted, but its first refusal would never show up."""
    source = (Path(__file__).parents[1] / "src/needtoknow/api/main.py").read_text()
    used = set(re.findall(r'refused\(\d+, "(\w+)"', source))
    assert used and used <= set(telemetry.REASONS)


def test_redact_counts_what_users_unchecked(sample_pdf):
    remove = json.dumps([{"page": 0, "text": "123-45-6789"}])
    with TestClient(app) as client:
        before = client.get("/metrics").text
        r = client.post("/api/redact", files={"file": ("lease.pdf", sample_pdf, "application/pdf")},
                        data={"remove": remove, "unchecked": "2"})
        after = client.get("/metrics").text
    assert r.status_code == 200

    def count(text, decision):
        line = next((x for x in text.splitlines()
                     if x.startswith(f'needtoknow_findings_reviewed_total{{decision="{decision}"}}')), None)
        return float(line.split()[-1]) if line else 0.0

    assert count(after, "unchecked") - count(before, "unchecked") == 2
    assert count(after, "removed") - count(before, "removed") == 1


def test_traces_hold_counts_but_no_text_or_file_name(sample_pdf, spans):
    spans.clear()
    with TestClient(app) as client:
        client.post("/api/detect", files={"file": ("Maria Delgado lease.pdf", sample_pdf, "application/pdf")})
    finished = {s.name: s for s in spans.get_finished_spans()}
    assert {"POST /api/detect", "pdf.extract", "detect"} <= finished.keys()
    assert finished["detect"].attributes["findings"] > 0
    assert finished["POST /api/detect"].attributes.get("net.peer.ip", "") == ""   # not the caller's address
    dump = " ".join(s.to_json() for s in finished.values())
    assert not [p for p in PRIVATE if p in dump]


def test_log_lines_carry_ids_and_no_personal_information(sample_pdf, log_lines):
    with TestClient(app) as client:
        r = client.post("/api/detect", files={"file": ("Maria Delgado lease.pdf", sample_pdf, "application/pdf")})
    lines = [json.loads(line) for line in log_lines]
    detect = next(line for line in lines if line["message"] == "detect")
    request = next(line for line in lines if line["message"] == "request")
    assert detect["request_id"] == request["request_id"] == r.headers["x-request-id"]
    assert detect["trace_id"] and detect["trace_id"] == request["trace_id"]
    assert request["status"] == 200 and request["path"] == "/api/detect"
    assert detect["service"] == "needtoknow-api" and detect["findings"] > 0
    assert not [p for p in PRIVATE if p in " ".join(log_lines)]


def test_health_answers_without_logging_a_line(log_lines):
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    assert not [line for line in log_lines if '"path": "/health"' in line]
