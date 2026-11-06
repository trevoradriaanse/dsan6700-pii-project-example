"""The detector on its own: a small service that takes text and returns the personal information found in it.

    NTK_DETECTOR=regex uvicorn needtoknow.detectors.service:app --port 8001

The API calls it when NTK_DETECTOR_URL is set (see remote.py). Like the API, it keeps nothing: the text arrives,
the spans go back, and both are forgotten. Its logs, metrics and traces hold counts, never the text.
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from needtoknow import __version__, telemetry
from needtoknow.config import settings
from needtoknow.detectors import build_detector


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.monotonic()
    app.state.detector = build_detector(settings.detector, gliner_model=settings.gliner_model,
                                        gliner_threshold=settings.gliner_threshold,
                                        gliner_revision=settings.gliner_revision)
    logger.info("detector ready", detector=app.state.detector.name, seconds=round(time.monotonic() - t0, 1))
    yield
    telemetry.flush()


app = FastAPI(title="Need to Know detector", version=__version__, lifespan=lifespan)


class Text(BaseModel):
    text: str = Field(max_length=1_000_000)   # one page of text; far more than a real page holds


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready(request: Request) -> dict:
    detector = getattr(request.app.state, "detector", None)
    if detector is None:
        raise HTTPException(503, "the detector is still loading")
    return {"status": "ready", "detector": detector.name, "version": __version__, "commit": settings.commit}


@app.post("/detect")
def detect(body: Text, request: Request) -> dict:
    detector = request.app.state.detector
    with telemetry.tracer.start_as_current_span(detector.name) as step:   # a span named for the model, counts only
        spans = detector.detect(body.text)
        step.set_attribute("found", len(spans))
    return {"detector": detector.name, "spans": [s.as_dict() for s in spans]}


telemetry.setup(app, "needtoknow-detector", settings.log_level)
