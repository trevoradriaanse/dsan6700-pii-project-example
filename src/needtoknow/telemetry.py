"""Logs, metrics and traces for Need to Know, set up once when the app starts.

None of them ever holds personal information: no document text, no text found, no file names, and not the caller's
address. Only counts, durations, and names we chose ourselves (a route, a detector, a reason for refusing an upload).

- Logs: loguru writes one JSON object per line on stdout, where `docker compose logs` reads them. Every line from one
  request carries the same request_id and trace_id. With OTEL_EXPORTER_OTLP_ENDPOINT set, the lines also go to the
  OpenTelemetry collector, which stores them in Loki.
- Metrics: /metrics, for Prometheus to collect every few seconds.
- Traces: a span for each request and for each step inside it, sent to the collector (and on to Tempo) when
  OTEL_EXPORTER_OTLP_ENDPOINT is set. Without it, spans still give every request a trace id for the logs.
"""

import inspect
import json
import logging
import os
import re
import sys
import time
import uuid

from fastapi import FastAPI, Request
from loguru import logger
from opentelemetry import trace
from opentelemetry._logs import LogRecord, SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import TraceFlags
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# Our own metrics, next to the standard HTTP ones. A label's values must be a short list we chose: each new value is
# one more time series for Prometheus to keep, so never a file name, a client's address, or anything a user typed.
SECONDS = (.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10, 30, 60)   # from one page with regex to Caddy's limit
DETECTION_SECONDS = Histogram("needtoknow_detection_seconds", "Time to find everything in one document",
                              ["detector"], buckets=SECONDS)
FINDINGS_PER_PAGE = Histogram("needtoknow_findings_per_page", "Findings on each page checked",
                              ["detector"], buckets=(0, 1, 2, 5, 10, 20, 50))
DOCUMENTS = Counter("needtoknow_documents_checked", "Documents checked", ["detector"])
REFUSED = Counter("needtoknow_uploads_refused", "Uploads refused, by reason", ["reason"])
# What users did with the findings before downloading: removed them, or unchecked them as false alarms. A rising
# share of unchecked findings says the detector is flagging things that aren't personal information.
REVIEWED = Counter("needtoknow_findings_reviewed", "Findings users reviewed, by what they decided", ["decision"])
REASONS = ("rate_limited", "too_large", "not_pdf", "no_text_layer", "too_many_pages")   # every reason we refuse for
DECISIONS = ("removed", "unchecked")


def start_at_zero(detector: str) -> None:
    """Create each series we know of at 0 when the app starts. A labeled series only exists from its first event on,
    so Prometheus would first see it at 1 and have no earlier sample to count that 1 from: the first refusal of
    each kind after every restart would never show up in rate() or on the dashboard."""
    for reason in REASONS:
        REFUSED.labels(reason)
    for decision in DECISIONS:
        REVIEWED.labels(decision)
    for metric in (DETECTION_SECONDS, FINDINGS_PER_PAGE, DOCUMENTS):
        metric.labels(detector)

SKIP = ["/health", "/ready", "/metrics"]   # asked every few seconds by Docker and Prometheus: no traces, no counts
tracer = trace.get_tracer("needtoknow")
_providers = []   # flushed when the app stops, so the last few seconds of spans and logs aren't lost


def _add_trace_id(record: dict) -> None:
    """Put the trace id on every line, so a line and its trace can be found from each other (runs as each line is
    logged, in the request's own context)."""
    span = trace.get_current_span().get_span_context()
    if span.is_valid:
        record["extra"]["trace_id"] = trace.format_trace_id(span.trace_id)
        record["extra"]["_span_id"] = span.span_id   # for the collector only; leading _ keeps it out of the JSON


def as_json(record: dict) -> str:
    """One JSON object per line: when, how serious, what happened, and the fields that came with it."""
    line = {"time": record["time"].isoformat(), "level": record["level"].name, "logger": record["name"],
            "message": record["message"]}
    line.update({key: value for key, value in record["extra"].items() if not key.startswith("_")})
    if record["exception"]:
        line["error"] = record["exception"].type.__name__   # the kind of error; the traceback stays out
    return json.dumps(line, default=str)


def _json_line(message) -> None:
    sys.stdout.write(as_json(message.record) + "\n")


def _to_collector(provider: LoggerProvider):
    """A second destination for the same lines: the OpenTelemetry collector, which stores them in Loki."""
    otel = provider.get_logger("needtoknow")
    levels = {"DEBUG": SeverityNumber.DEBUG, "INFO": SeverityNumber.INFO, "WARNING": SeverityNumber.WARN,
              "ERROR": SeverityNumber.ERROR, "CRITICAL": SeverityNumber.FATAL}

    def sink(message) -> None:
        record = message.record
        extra = record["extra"]
        fields = {key: value if isinstance(value, (str, int, float, bool)) else str(value)
                  for key, value in extra.items() if not key.startswith("_") and value is not None}
        ids = {}
        if "trace_id" in extra:
            ids = {"trace_id": int(extra["trace_id"], 16), "span_id": extra["_span_id"], "trace_flags": TraceFlags(1)}
        otel.emit(LogRecord(timestamp=int(record["time"].timestamp() * 1e9), body=record["message"],
                            severity_text=record["level"].name,
                            severity_number=levels.get(record["level"].name, SeverityNumber.INFO),
                            attributes={"logger": record["name"], **fields}, **ids))

    return sink


class ToLoguru(logging.Handler):
    """uvicorn and other libraries log through Python's logging module: send their lines through loguru, as JSON.
    (The handler loguru's own documentation suggests.)"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = inspect.currentframe(), 0   # find the library's own line, so "logger" names it, not us
        while frame:
            filename = frame.f_code.co_filename
            if depth > 0 and filename != logging.__file__ and not ("importlib" in filename and "_bootstrap" in filename):
                break
            frame, depth = frame.f_back, depth + 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def forget_the_caller(span, scope) -> None:
    """The automatic request span records the caller's IP address, which is personal data we have no use for."""
    if span.is_recording():
        span.set_attributes({key: "" for key in ("net.peer.ip", "client.address") if key in span.attributes})


def setup(app: FastAPI, service: str, level: str = "INFO") -> None:
    """Logs, traces and metrics for one service (the API, or later the detector)."""
    collector = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")   # e.g. http://lgtm:4318, set in .env with the profile
    resource = Resource.create({"service.name": service})

    # Logs. enqueue=True writes from a background thread, so a slow terminal never holds up a request.
    logger.remove()
    logger.configure(extra={"service": service}, patcher=_add_trace_id)
    logger.add(_json_line, level=level, enqueue=True, backtrace=False, diagnose=False, catch=True)
    if collector:
        logs = LoggerProvider(resource=resource)
        logs.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        logger.add(_to_collector(logs), level=level, catch=True)
        _providers.append(logs)
    logging.basicConfig(handlers=[ToLoguru()], level=level, force=True)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()    # uvicorn's own lines go through ours
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True   # our line below replaces it, without the caller's address

    # Traces. Spans always exist (they give each request its trace id); they are exported only to a collector.
    spans = TracerProvider(resource=resource)
    if collector:
        spans.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        _providers.append(spans)
    trace.set_tracer_provider(spans)
    FastAPIInstrumentor.instrument_app(app, excluded_urls=",".join(SKIP), exclude_spans=["receive", "send"],
                                       server_request_hook=forget_the_caller)

    # Metrics: requests, errors and durations per route, at /metrics for Prometheus to collect.
    Instrumentator(excluded_handlers=SKIP).instrument(app, latency_lowr_buckets=SECONDS).expose(
        app, include_in_schema=False)

    @app.middleware("http")
    async def one_line_per_request(request: Request, call_next):
        asked = request.headers.get("x-request-id", "")   # a caller (later, the API calling the detector) may send one
        rid = asked if re.fullmatch(r"[\w-]{1,64}", asked) else uuid.uuid4().hex
        t0, status = time.monotonic(), 500     # 500 unless the route answers: an exception becomes a 500 outside us
        with logger.contextualize(request_id=rid):
            try:
                response = await call_next(request)
                status = response.status_code
                response.headers["X-Request-ID"] = rid   # so a user's report can be matched to our logs
                return response
            finally:
                if request.url.path not in SKIP:
                    logger.info("request", method=request.method, path=request.url.path, status=status,
                                ms=round((time.monotonic() - t0) * 1000, 1))


def flush() -> None:
    """Send what is still waiting: the batch processors export every few seconds, and a stop would lose the rest."""
    for provider in _providers:
        provider.shutdown()
    logger.complete()
