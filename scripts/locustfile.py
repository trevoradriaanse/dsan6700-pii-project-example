"""A load test: more and more users upload the sample lease to /api/detect, one step at a time.

    docker run --rm --network host -v "$PWD/scripts:/mnt/locust" locustio/locust:2.47.0 \
        -f /mnt/locust/locustfile.py --host http://localhost:8000 --headless --only-summary

Each user uploads again as soon as an answer arrives, with no pause, so this measures how many uploads a second the
app can take, not how people use it. Every user comes from this one machine, so the rate limit sees one client: set
NTK_RATE_LIMIT_PER_MINUTE=0 on the app to measure capacity, and leave it on to watch it refuse uploads (429).

At the end of each step it prints one line: the users, uploads a second, the average, p50, p95 and p99 times, and
how many uploads failed. STEPS (the users in each step) and STEP_SECONDS change the steps.
"""

import os
from pathlib import Path

from locust import HttpUser, LoadTestShape, constant, events, task

PDF = (Path(__file__).parent / "smoke-lease.pdf").read_bytes()
STEPS = [int(n) for n in os.environ.get("STEPS", "1,2,4,8,16,32").split(",")]
SECONDS = int(os.environ.get("STEP_SECONDS", "30"))

times, failed = [], [0]   # this step's response times in ms, and its failures


@events.request.add_listener
def record(response_time, exception, **kwargs):
    if exception is None:
        times.append(response_time)
    else:
        failed[0] += 1


def report(users: int) -> None:
    done = sorted(times)
    if done:
        at = lambda q: done[min(len(done) - 1, int(q * len(done)))]   # noqa: E731
        print(f"{users:3d} users  {len(done) / SECONDS:6.1f} uploads/s  average {sum(done) / len(done):5.0f} ms  "
              f"p50 {at(.5):5.0f} ms  p95 {at(.95):5.0f} ms  p99 {at(.99):5.0f} ms  failed {failed[0]}", flush=True)
    times.clear()
    failed[0] = 0


class Uploader(HttpUser):
    wait_time = constant(0)

    @task
    def detect(self):
        self.client.post("/api/detect", files={"file": ("lease.pdf", PDF, "application/pdf")})


class Steps(LoadTestShape):
    step = -1

    def tick(self):
        step = int(self.get_run_time() // SECONDS)
        if step != self.step:
            if self.step >= 0:
                report(STEPS[self.step])
            self.step = step
        return (STEPS[step], 50) if step < len(STEPS) else None   # (users, how many to start per second)
