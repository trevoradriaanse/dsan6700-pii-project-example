"""How many uploads one client may send in a minute: a sliding window, counted in this process's memory.

Per process: two copies of the app (or two uvicorn workers) each count separately, so a client may get up to twice
the limit. That is enough to stop one user or one script from keeping the detector busy for everyone else. Real
protection against a flood of traffic sits in front of the app, at the edge (a proxy, a load balancer, a CDN),
before the requests reach us at all.
"""

import math
import threading
import time
from collections import deque

WINDOW = 60.0   # seconds


class SlidingWindow:
    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = {}
        self.lock = threading.Lock()   # the upload routes run in a thread pool, several at once
        self.swept = time.monotonic()

    def check(self, client: str, limit: int) -> int:
        """Count one request from this client. 0 if it may go ahead, else how many seconds until it may."""
        now = time.monotonic()
        with self.lock:
            if now - self.swept > WINDOW:   # forget clients with nothing in the window, so memory does not grow forever
                self.hits = {c: h for c, h in self.hits.items() if h and now - h[-1] < WINDOW}
                self.swept = now
            hits = self.hits.setdefault(client, deque())
            while hits and now - hits[0] >= WINDOW:
                hits.popleft()
            if len(hits) >= limit:   # refused requests are not counted: waiting, not retrying faster, is what helps
                return max(1, math.ceil(WINDOW - (now - hits[0])))
            hits.append(now)
            return 0

    def clear(self) -> None:
        with self.lock:
            self.hits.clear()


uploads = SlidingWindow()
