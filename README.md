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

## Put a front door on it (HTTPS)

[Caddy](https://caddyserver.com) answers at the instance's name, gets the HTTPS certificate for it on its own, and
passes each request to the app ([Caddyfile](Caddyfile)). Add these lines to `.env` on the instance, then start it
once with `docker compose up -d`; later deploys restart only the app.

```
COMPOSE_PROFILES=proxy
NTK_DOMAIN=your-instance.your-project.projects.jetstream-cloud.org
APP_BIND=127.0.0.1        # the app's own port answers only this machine now
FORWARDED_ALLOW_IPS=*     # read who is calling from the header Caddy adds; safe because Caddy is the only way in
```

## Watch it run: logs, metrics and traces

Every log line is one JSON object on stdout, written with [loguru](https://loguru.readthedocs.io). The lines of one
request share a `request_id` (also sent back in the `X-Request-ID` header) and a `trace_id`, so one upload can be
followed through its lines: `docker compose logs app | grep <request_id>`. `/metrics` has the requests, errors and
durations of each route for [Prometheus](https://prometheus.io), plus our own counts: documents checked, findings
per page, uploads refused by reason, and the findings users unchecked. None of them holds a document's text, its
name, or the caller's address (see [telemetry.py](src/needtoknow/telemetry.py)).

To see them in Grafana, add these lines to `.env` and start the stack again with `docker compose up -d`:

```
COMPOSE_PROFILES=observability          # proxy,observability with Caddy
OTEL_EXPORTER_OTLP_ENDPOINT=http://lgtm:4318
```

The `lgtm` service is [grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm): Grafana, Prometheus, Loki
(logs), Tempo (traces) and an OpenTelemetry collector in one container, made for development and demonstrations,
not production. Grafana answers on port 3000 of the instance only: forward it with VS Code's Ports panel (or
`ssh -L 3000:localhost:3000 ...`) and open http://localhost:3000. The **Need to Know** dashboard shows the four golden
signals (traffic, errors, latency, saturation) and the model's findings; two alerts fire when uploads fail or the API
stops answering. Anyone who can open this Grafana is an administrator, so never publish its port.

Load-test it with [Locust](https://locust.io), from Locust's own image, so nothing needs installing:

```bash
docker run --rm --network host -v "$PWD/scripts:/mnt/locust" locustio/locust:2.47.0 \
  -f /mnt/locust/locustfile.py --host http://localhost:8000 --headless --only-summary
```

It adds users step by step and prints one line per step: uploads a second, and the average, p50, p95 and p99 times.
`-e STEPS=1,2,4 -e STEP_SECONDS=60` changes the steps. Every Locust user comes from one machine, so set
`NTK_RATE_LIMIT_PER_MINUTE=0` while you measure capacity.

## Back up the counts, and restore them

The usage counts are the only thing Need to Know keeps that can't be rebuilt from Git and the registry (the
documents never are). `scripts/backup.sh` takes a consistent copy while the app keeps running and saves it in
`backups/` on the instance; copy it somewhere else too, since a copy on the instance is lost with the instance.
`scripts/restore.sh` puts the newest copy back (or the one you name; counts recorded after it are lost), and
`scripts/smoke.sh <port>` checks the app afterwards. A backup we have never restored is only a hope: try a restore
now and then, on another machine if you can. Keep a copy of `.env` somewhere safe too: it is not in Git.
