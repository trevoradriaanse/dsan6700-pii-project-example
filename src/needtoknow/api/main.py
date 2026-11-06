"""The web service: one page to use it, and three endpoints behind the page.

Nothing a user sends is stored: each request reads the PDF from memory and forgets it. The browser keeps the file
between finding and redacting. Logs, metrics, traces and the usage counts record numbers, never the document, its
name, or the text found (see telemetry.py).
"""

import hashlib
import json
import re
import secrets
import time
from collections import Counter
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from needtoknow import __version__, ratelimit, store, telemetry
from needtoknow.config import settings
from needtoknow.detectors import build_detector
from needtoknow.detectors.remote import DetectorUnavailable, RemoteDetector
from needtoknow.pdf import NotAPdf, NoTextLayer, TooManyPages, extract_pages, leaked, redact
from needtoknow.telemetry import DETECTION_SECONDS, DOCUMENTS, FINDINGS_PER_PAGE, REFUSED, REVIEWED, tracer


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.monotonic()
    if settings.detector_url:   # the detector runs as its own service (needtoknow.detectors.service)
        app.state.detector = RemoteDetector(settings.detector_url, settings.detector_timeout)
    else:
        app.state.detector = build_detector(settings.detector, gliner_model=settings.gliner_model,
                                            gliner_threshold=settings.gliner_threshold,
                                            gliner_revision=settings.gliner_revision)  # once, before the first request
    logger.info("detector ready", detector=app.state.detector.name, seconds=round(time.monotonic() - t0, 1))
    yield
    telemetry.flush()


app = FastAPI(title="Need to Know", version=__version__, lifespan=lifespan,
              description="Find the personal information in a PDF, review it, and download a copy with it removed.")


@app.middleware("http")
async def refuse_large_bodies(request: Request, call_next):
    """Refuse an oversized upload before reading it: otherwise it is received in full, and spooled to /tmp."""
    limit = (settings.max_upload_mb + 1) * 1024 * 1024  # room for the form around the file
    if int(request.headers.get("content-length") or 0) > limit:
        exc = refused(413, "too_large", f"the file is larger than {settings.max_upload_mb} MB")
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


def download_headers(filename: str | None) -> dict:
    """A safe file name for the download: plain ASCII as a fallback, the original (encoded) for browsers that can."""
    stem = (filename or "document.pdf").rsplit("/", 1)[-1].rsplit(".", 1)[0] + "-redacted.pdf"
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
    return {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(stem)}"}


def refused(status: int, reason: str, detail: object, **kwargs) -> HTTPException:
    """An upload we will not process: count it by reason (never by who sent it, or what it was), then say why."""
    REFUSED.labels(reason).inc()
    logger.info("refused", reason=reason, status=status)
    return HTTPException(status, str(detail), **kwargs)


def rate_limit(request: Request) -> None:
    """Refuse a client that has sent too many uploads this minute, and tell it how long to wait."""
    if settings.rate_limit_per_minute == 0:
        return
    # The address the connection came from. Through Docker on the same machine this is the bridge gateway, so every
    # local client looks like one. Behind Caddy, uvicorn reads it from the X-Forwarded-For header Caddy adds, once
    # FORWARDED_ALLOW_IPS says to believe it (see the CHANGELOG, 0.8.0).
    client = request.client.host if request.client else "unknown"
    wait = ratelimit.uploads.check(client, settings.rate_limit_per_minute)
    if wait:
        raise refused(429, "rate_limited", f"too many uploads: at most {settings.rate_limit_per_minute} a minute",
                      headers={"Retry-After": str(wait)})


class Finding(BaseModel):
    id: int
    page: int
    label: str
    text: str


class DetectResponse(BaseModel):
    detector: str
    pages: int
    findings: list[Finding]
    seconds: float


class ToRemove(BaseModel):
    page: int
    text: str


def read_upload(file: UploadFile) -> bytes:
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise refused(413, "too_large", f"the file is larger than {settings.max_upload_mb} MB")
    return data


# Caching. The page itself must never be served stale after a deploy, so browsers and any CDN in front of us must
# check back every time ("no-cache"); its ETag lets them check cheaply, with a 304 and no body. The script it loads is
# named by the commit (/static/app.js?v=<commit>), so it can be cached for a year: a new deploy changes the address.
# API responses carry a user's findings or redacted PDF, so no browser or CDN may keep them at all ("no-store").
STATIC = files("needtoknow").joinpath("static")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        if request.query_params.get("v") == settings.commit:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:  # an old or missing version: this file is not what that address named, so nobody may keep it
            response.headers["Cache-Control"] = "no-cache"
    elif path == "/api/stats":
        response.headers["Cache-Control"] = "public, max-age=60"   # totals for everyone, nobody's document
    elif path.startswith(("/api/", "/admin/")):
        response.headers["Cache-Control"] = "no-store"    # findings, redacted PDFs and admin numbers: never keep a copy
    elif path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


# The page is the same for everyone until the next deploy, so it is built once, and its ETag is a hash of it.
PAGE = STATIC.joinpath("index.html").read_text().replace("{{COMMIT}}", settings.commit)
PAGE_ETAG = '"' + hashlib.sha256(PAGE.encode()).hexdigest()[:16] + '"'


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request) -> Response:
    if request.headers.get("if-none-match") == PAGE_ETAG:   # the browser's copy is current: say so, send nothing
        return Response(status_code=304, headers={"ETag": PAGE_ETAG})
    return HTMLResponse(PAGE, headers={"ETag": PAGE_ETAG})


# async: answered on the event loop itself, so it never waits behind uploads for one of the 40 worker threads.
@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready(request: Request) -> dict:
    detector = getattr(request.app.state, "detector", None)
    if detector is None:
        raise HTTPException(503, "the detector is still loading")
    if settings.db_path and (have := store.schema_version(settings.db_path)) < store.SCHEMA_REQUIRED:
        raise HTTPException(503, f"the database schema is at {have} and this version needs {store.SCHEMA_REQUIRED}: "
                                 "run python -m needtoknow.migrate up")
    return {"status": "ready", "detector": detector.name, "version": __version__, "commit": settings.commit}


@app.post("/api/detect", response_model=DetectResponse, dependencies=[Depends(rate_limit)])
def detect(request: Request, file: Annotated[UploadFile, File()]) -> DetectResponse:
    t0 = time.monotonic()
    data = read_upload(file)
    with tracer.start_as_current_span("pdf.extract") as step:   # spans carry counts only, never text
        try:
            pages = extract_pages(data, settings.max_pages)
        except NotAPdf as exc:
            raise refused(415, "not_pdf", exc) from exc
        except NoTextLayer as exc:
            raise refused(422, "no_text_layer", exc) from exc
        except TooManyPages as exc:
            raise refused(422, "too_many_pages", exc) from exc
        step.set_attribute("pages", len(pages))
    detector = request.app.state.detector
    findings, seen = [], set()
    with tracer.start_as_current_span("detect") as step:
        t1 = time.monotonic()
        for page in pages:
            if time.monotonic() - t1 > settings.detect_budget:
                raise DetectorUnavailable(f"still detecting after {settings.detect_budget:g} s")
            for span in detector.detect(page.text):
                key = (page.number, span.text)
                if key in seen:
                    continue  # the same text on the same page is one finding: redaction removes every occurrence
                seen.add(key)
                findings.append(Finding(id=len(findings), page=page.number, label=span.label, text=span.text))
        DETECTION_SECONDS.labels(detector.name).observe(time.monotonic() - t1)
        step.set_attributes({"detector": detector.name, "findings": len(findings)})
    per_page = Counter(f.page for f in findings)
    for page in pages:
        FINDINGS_PER_PAGE.labels(detector.name).observe(per_page[page.number])
    DOCUMENTS.labels(detector.name).inc()
    seconds = round(time.monotonic() - t0, 3)
    if settings.db_path:
        with tracer.start_as_current_span("usage.record"):   # one write to SQLite, which waits for the disk
            try:
                store.record(settings.db_path, detector.name, len(findings))
            except Exception:  # counting must never cost the user their result; the log says what went wrong
                logger.exception("could not record usage")
    logger.info("detect", pages=len(pages), findings=len(findings), detector=detector.name, seconds=seconds)
    return DetectResponse(detector=detector.name, pages=len(pages), findings=findings, seconds=seconds)


@app.exception_handler(DetectorUnavailable)
def detector_unavailable(request: Request, exc: DetectorUnavailable) -> JSONResponse:
    """The detector service did not answer, even after trying again: say so (the page shows this detail)."""
    logger.error("detector unavailable", problem=str(exc))
    return JSONResponse({"detail": "the detector is not answering. Nothing was kept. Try again in a minute."}, 503)


@app.post("/api/redact", dependencies=[Depends(rate_limit)])
def redact_pdf(file: Annotated[UploadFile, File()], remove: Annotated[str, Form()],
               unchecked: Annotated[int, Form(ge=0)] = 0) -> Response:
    """Remove the findings the user kept checked. `unchecked` is how many they unchecked as false alarms (a count)."""
    data = read_upload(file)
    try:
        items = [ToRemove.model_validate(x) for x in json.loads(remove)]
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "`remove` must be a JSON list of {page, text}") from exc
    pairs = [(i.page, i.text) for i in items]
    with tracer.start_as_current_span("pdf.redact") as step:
        step.set_attribute("items", len(pairs))
        try:
            out = redact(data, pairs, settings.max_pages)
        except NotAPdf as exc:
            raise refused(415, "not_pdf", exc) from exc
        except TooManyPages as exc:
            raise refused(422, "too_many_pages", exc) from exc
        still_there = leaked(out, pairs)
    if still_there:  # never hand back a file we promised was clean
        logger.error("redaction left items in place", items=len(still_there))
        raise HTTPException(500, "redaction did not remove every selected item; nothing was returned")
    REVIEWED.labels("removed").inc(len(pairs))
    REVIEWED.labels("unchecked").inc(unchecked)
    logger.info("redact", items=len(pairs), unchecked=unchecked, bytes_in=len(data), bytes_out=len(out))
    return Response(out, media_type="application/pdf", headers=download_headers(file.filename))


@app.get("/api/stats")
def usage_stats() -> dict:
    """How many documents have been checked and how many items found. Numbers only, never content."""
    if not settings.db_path:
        return {"counting": False}
    return {"counting": True, **store.stats(settings.db_path)}


# For whoever runs the service: every day's counts, the schema, and the backups the migrations made. Left out of
# the API docs, but that alone hides nothing (anyone who guesses the address would get an answer), so every route
# here asks for the key first.
admin_key = APIKeyHeader(name="X-Admin-Key", auto_error=False)   # auto_error=False: we choose the status code


def require_admin(key: Annotated[str | None, Depends(admin_key)]) -> None:
    expected = settings.admin_api_key.get_secret_value()
    if not expected:   # no key configured: the routes are off, and there is nothing to guess
        raise HTTPException(404, "Not Found")
    # compare_digest takes as long for a near miss as for a wild guess, so timing gives away nothing about the key.
    if key is None or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(401, "a valid X-Admin-Key header is required")


admin = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)], include_in_schema=False)


@admin.get("/stats")
def admin_stats() -> dict:
    if not settings.db_path:
        return {"counting": False}
    backups = Path(settings.db_path).parent / "backups"
    return {"counting": True, "schema_version": store.schema_version(settings.db_path),
            "schema_required": store.SCHEMA_REQUIRED, "days": store.daily(settings.db_path),
            "backups": sorted(p.name for p in backups.glob("*.db"))}


app.include_router(admin)
telemetry.setup(app, "needtoknow-api", settings.log_level)   # last, so its request log and metrics see every request
