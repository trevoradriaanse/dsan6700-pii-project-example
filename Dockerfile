# Need to Know: one container, the API and the page it serves.
#
# Where things live (decided 2026-10-10, see docs/ARCHITECTURE.md):
#   the detector   in-process, chosen by NTK_DETECTOR; the regex baseline needs nothing extra, the model-based
#                  detectors are installed with an extra (DETECTOR_EXTRA build argument) and download their
#                  weights on first start into a mounted cache, so the image stays small
#   documents      nowhere: each request reads the PDF from memory and forgets it
#   configuration  the environment at run time (.env through Compose), never the image
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/home/app/.cache/huggingface

COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /usr/local/bin/uv

# A user with no special rights runs the service. The model cache directory must exist, owned by that user, before a
# volume is mounted on it: otherwise Docker creates it owned by root and the download fails with Permission denied.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /home/app/.cache/huggingface && chown -R app:app /home/app/.cache
WORKDIR /app

# Dependencies first, in their own layer: a code change does not reinstall them.
ARG DETECTOR_EXTRA=""
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project ${DETECTOR_EXTRA:+--extra $DETECTOR_EXTRA}

# Then the code, which changes often.
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev ${DETECTOR_EXTRA:+--extra $DETECTOR_EXTRA} && chown -R app:app /app

# Which commit this image was built from: CI passes it in, /ready reports it, and the label links the image to the repo.
ARG GIT_SHA=dev
ENV NTK_COMMIT=$GIT_SHA
LABEL org.opencontainers.image.revision=$GIT_SHA \
      org.opencontainers.image.source=https://github.com/trevoradriaanse/dsan6700-pii-project-example

USER app
EXPOSE 8000
# The image has no curl; Python can ask the health endpoint itself.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=4)"
CMD ["/app/.venv/bin/uvicorn", "needtoknow.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
