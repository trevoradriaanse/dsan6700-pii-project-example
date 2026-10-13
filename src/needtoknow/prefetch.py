"""One-off task: download the configured detector's model weights into the cache volume before a deploy.

Run it the Twelve-Factor way, in the same image and settings as the app, then let the container go away:
    docker compose run --rm app python -m needtoknow.prefetch
The regex detector has no weights, so this is instant; GLiNER downloads once (about 1 GB) and every later start reuses it.
"""

import time

from needtoknow.config import settings
from needtoknow.detectors import build_detector


def main() -> None:
    t0 = time.monotonic()
    detector = build_detector(settings.detector, gliner_model=settings.gliner_model,
                              gliner_threshold=settings.gliner_threshold)
    print(f"{detector.name}: ready in {time.monotonic() - t0:.1f} s (weights, if any, are now in the cache volume)")


if __name__ == "__main__":
    main()
