"""The web service: one page to use it, and three endpoints behind the page.

Nothing a user sends is stored: each request reads the PDF from memory and forgets it. The browser keeps the file
between finding and redacting. Logs and the usage counts record numbers, never the document or the text found.
"""

import hashlib
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from needtoknow import __version__, store
from needtoknow.config import settings
from needtoknow.detectors import build_detector
from needtoknow.pdf import NotAPdf, NoTextLayer, TooManyPages, extract_pages, leaked, redact

log = logging.getLogger("needtoknow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    t0 = time.monotonic()
    app.state.detector = build_detector(settings.detector, gliner_model=settings.gliner_model,
                                        gliner_threshold=settings.gliner_threshold)  # once, before the first request
    log.info("detector %s ready in %.1fs", app.state.detector.name, time.monotonic() - t0)
    yield


app = FastAPI(title="Need to Know", version=__version__, lifespan=lifespan,
              description="Find the personal information in a PDF, review it, and download a copy with it removed.")


@app.middleware("http")
async def refuse_large_bodies(request: Request, call_next):
    """Refuse an oversized upload before reading it: otherwise it is received in full, and spooled to /tmp."""
    limit = (settings.max_upload_mb + 1) * 1024 * 1024  # room for the form around the file
    if int(request.headers.get("content-length") or 0) > limit:
        return JSONResponse({"detail": f"the file is larger than {settings.max_upload_mb} MB"}, status_code=413)
    return await call_next(request)


def download_headers(filename: str | None) -> dict:
    """A safe file name for the download: plain ASCII as a fallback, the original (encoded) for browsers that can."""
    stem = (filename or "document.pdf").rsplit("/", 1)[-1].rsplit(".", 1)[0] + "-redacted.pdf"
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", stem)
    return {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(stem)}"}


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
        raise HTTPException(413, f"the file is larger than {settings.max_upload_mb} MB")
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
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"    # findings and redacted PDFs are private: never keep a copy
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


@app.get("/health")
def health() -> dict:
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


@app.post("/api/detect", response_model=DetectResponse)
def detect(request: Request, file: Annotated[UploadFile, File()]) -> DetectResponse:
    t0 = time.monotonic()
    data = read_upload(file)
    try:
        pages = extract_pages(data, settings.max_pages)
    except NotAPdf as exc:
        raise HTTPException(415, str(exc)) from exc
    except (NoTextLayer, TooManyPages) as exc:
        raise HTTPException(422, str(exc)) from exc
    detector = request.app.state.detector
    findings, seen = [], set()
    for page in pages:
        for span in detector.detect(page.text):
            key = (page.number, span.text)
            if key in seen:
                continue  # the same text on the same page is one finding: redaction removes every occurrence
            seen.add(key)
            findings.append(Finding(id=len(findings), page=page.number, label=span.label, text=span.text))
    seconds = round(time.monotonic() - t0, 3)
    if settings.db_path:
        try:
            store.record(settings.db_path, detector.name, len(findings))
        except Exception:  # counting must never cost the user their result; the log says what went wrong
            log.exception("could not record usage")
    log.info("detect pages=%d findings=%d detector=%s seconds=%.3f", len(pages), len(findings), detector.name, seconds)
    return DetectResponse(detector=detector.name, pages=len(pages), findings=findings, seconds=seconds)


@app.post("/api/redact")
def redact_pdf(file: Annotated[UploadFile, File()], remove: Annotated[str, Form()]) -> Response:
    data = read_upload(file)
    try:
        items = [ToRemove.model_validate(x) for x in json.loads(remove)]
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "`remove` must be a JSON list of {page, text}") from exc
    pairs = [(i.page, i.text) for i in items]
    try:
        out = redact(data, pairs, settings.max_pages)
    except NotAPdf as exc:
        raise HTTPException(415, str(exc)) from exc
    except TooManyPages as exc:
        raise HTTPException(422, str(exc)) from exc
    still_there = leaked(out, pairs)
    if still_there:  # never hand back a file we promised was clean
        log.error("redaction left %d items in place", len(still_there))
        raise HTTPException(500, "redaction did not remove every selected item; nothing was returned")
    log.info("redact items=%d bytes_in=%d bytes_out=%d", len(pairs), len(data), len(out))
    return Response(out, media_type="application/pdf", headers=download_headers(file.filename))


@app.get("/api/stats")
def usage_stats() -> dict:
    """How many documents have been checked and how many items found. Numbers only, never content."""
    if not settings.db_path:
        return {"counting": False}
    return {"counting": True, **store.stats(settings.db_path)}
