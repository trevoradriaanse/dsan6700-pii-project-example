"""The web service: one page to use it, and three endpoints behind the page.

Nothing a user sends is stored: each request reads the PDF from memory and forgets it. The browser keeps the file
between finding and redacting. Logs record counts and timings, never the text found.
"""

import json
import logging
import time
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from needtoknow import __version__
from needtoknow.config import settings
from needtoknow.detectors import build_detector
from needtoknow.pdf import NotAPdf, NoTextLayer, extract_pages, leaked, redact

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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    return files("needtoknow").joinpath("static/index.html").read_text()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready(request: Request) -> dict:
    detector = getattr(request.app.state, "detector", None)
    if detector is None:
        raise HTTPException(503, "the detector is still loading")
    return {"status": "ready", "detector": detector.name, "version": __version__}


@app.post("/api/detect", response_model=DetectResponse)
def detect(request: Request, file: Annotated[UploadFile, File()]) -> DetectResponse:
    t0 = time.monotonic()
    data = read_upload(file)
    try:
        pages = extract_pages(data, settings.max_pages)
    except NotAPdf as exc:
        raise HTTPException(415, str(exc)) from exc
    except (NoTextLayer, ValueError) as exc:
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
        out = redact(data, pairs)
    except NotAPdf as exc:
        raise HTTPException(415, str(exc)) from exc
    still_there = leaked(out, pairs)
    if still_there:  # never hand back a file we promised was clean
        log.error("redaction left %d items in place", len(still_there))
        raise HTTPException(500, "redaction did not remove every selected item; nothing was returned")
    log.info("redact items=%d bytes_in=%d bytes_out=%d", len(pairs), len(data), len(out))
    name = (file.filename or "document.pdf").rsplit(".", 1)[0] + "-redacted.pdf"
    return Response(out, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})
