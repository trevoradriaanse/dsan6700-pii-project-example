"""The detector as a separate service, reached over HTTP (service.py is the other side).

RemoteDetector has the same detect(text) -> spans as the detectors that run in-process, so the API's loop does not
change when the detector moves. What changes is that every call can now fail, or hang, on the network.
"""

import logging
import random
import time

import httpx
from loguru import logger
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from needtoknow.detectors.base import Span
from needtoknow.telemetry import DETECTOR_RETRIES, request_id

RETRY_STATUSES = {502, 503, 504}   # the detector, or a proxy in front of it, is restarting, overloaded or stuck


class DetectorUnavailable(Exception):
    """The detector did not answer, even after trying again."""


def with_retries(send, tries: int = 3, first_wait: float = 0.5) -> httpx.Response:
    """Our one place for retries: at most `tries` calls in all, waiting 0.5 s, then 1 s, between them.

    Only what may work a moment later is tried again: a timeout, a failed connection, a 502, 503 or 504. A 4xx would
    get the same answer again. Each wait is multiplied by a random number between 0.5 and 1.5 (jitter), so callers
    that failed at the same moment don't all come back at the same moment.
    """
    for attempt in range(1, tries + 1):
        try:
            response = send()
            if response.status_code not in RETRY_STATUSES:
                return response.raise_for_status()   # anything else that failed is our bug: no retry
            problem = f"HTTP {response.status_code}"
        except httpx.TransportError as exc:          # a timeout, or the connection failed or broke
            problem = type(exc).__name__
        if attempt == tries:
            raise DetectorUnavailable(f"{problem} on all {tries} tries")
        wait = first_wait * 2 ** (attempt - 1) * random.uniform(0.5, 1.5)
        DETECTOR_RETRIES.labels(problem).inc()
        logger.warning("retrying the detector", problem=problem, attempt=attempt, wait_s=round(wait, 2))
        time.sleep(wait)


class RemoteDetector:
    def __init__(self, url: str, timeout: float) -> None:
        # A limit on every call: 2 s to connect, then `timeout` seconds for the answer.
        self.client = httpx.Client(base_url=url, timeout=httpx.Timeout(timeout, connect=2.0))
        HTTPXClientInstrumentor.instrument_client(self.client)   # each call carries the trace id (a traceparent header)
        logging.getLogger("httpx").setLevel(logging.WARNING)       # not a line per call: the trace shows each one
        try:   # the detector service says which detector it runs
            self.name = self.client.get("/ready").json()["detector"]
        except (httpx.HTTPError, KeyError, ValueError):
            self.name = "remote"

    def detect(self, text: str) -> list[Span]:
        response = with_retries(lambda: self.client.post("/detect", json={"text": text},
                                                         headers={"X-Request-ID": request_id.get()}))
        body = response.json()
        self.name = body["detector"]
        return [Span(**s) for s in body["spans"]]
