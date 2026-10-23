# Need to Know

Find the personal information in a PDF, choose what to remove, and download a copy with it truly removed (not just
covered by a black box).

A worked example for DSAN 6700 (Machine Learning Application Deployment): a small project carried from proposal to a
deployed skeleton. See `docs/PROPOSAL.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md` and `docs/USER_BRIEF.md`.
Inspired by Catherine Nelson's docscrubber (https://docscrubber.app) and measured on her benchmark, pdf-pii-bench
(https://github.com/callixdev/pdf-pii-bench, CC BY 4.0).

**Use synthetic documents only.** Nothing you upload is stored, but this is a demonstration.

## Run it

```bash
uv sync --extra dev                                  # the regex baseline needs nothing more
cp .env.example .env
uv run uvicorn needtoknow.api.main:app --reload      # http://localhost:8000, API docs at /docs
uv run pytest
```

With Docker, on a Jetstream2 instance:

```bash
cp .env.example .env
docker compose up -d --build                        # http://<instance address>:8000
DETECTOR_EXTRA=gliner docker compose up -d --build  # the model-based detector (image 3.5 GB vs 555 MB); set NTK_DETECTOR=regex+gliner in .env
```

## Use the API

```bash
curl -F file=@lease.pdf http://localhost:8000/api/detect
curl -F file=@lease.pdf -F 'remove=[{"page":0,"text":"(512) 555-0180"}]' http://localhost:8000/api/redact -o lease-redacted.pdf
```

## Measure it

```bash
git clone https://github.com/callixdev/pdf-pii-bench eval/pdf-pii-bench
uv run needtoknow-eval --detector regex             # writes eval/mine/regex.json and prints scores
cd eval/pdf-pii-bench && uv run python -m src.score_predictions ../mine/regex.json   # the benchmark's own scorer
```

| Detector | Recall | Precision | 50 documents, CPU |
|---|---|---|---|
| regex (baseline) | 0.623 | 0.930 | 0.1 s |
| presidio | 0.702 | 0.460 | 12 s |
| gliner | 0.708 | 0.573 | 115 s (m3.medium) |
| **regex + gliner** | **0.900** | **0.619** | 120 s (m3.medium) |
| openai/privacy-filter (published by the benchmark) | 0.671 | 0.963 | about 25 min |
| docscrubber pipeline (published) | 0.912 | 0.774 | in the browser |

Character-level redaction scores, as the benchmark computes them.

## Deploy and roll back

Every push to `main` that passes the tests is built once by CI and pushed to `ghcr.io/trevoradriaanse/needtoknow`,
tagged by commit (`sha-1a2b3c4`). Pushing a tag such as `v0.6.0` gives that tested image a version name. On the
instance, `scripts/deploy.sh v0.6.0` runs any database migrations and deploys it, and the same command with the
previous version rolls back. deploy.sh writes the digest of the image it pulled into `.env`, so a tag moved
later can't change what runs. See [CHANGELOG.md](CHANGELOG.md) for what each release changes.
