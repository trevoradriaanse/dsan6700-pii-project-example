# From architecture to tasks

How the architecture became the first week of work. Each line was a GitHub issue; each issue got a branch and a pull
request that a teammate reviewed. The first milestone is a **walking skeleton**: the thinnest version that works from
end to end, so every later task improves something that already runs.

## Milestone 1: walking skeleton (everything connected, nothing good yet)
1. Project setup: `pyproject.toml`, uv, ruff, pytest, CI on pushes to `main` and on pull requests.
2. Settings: a `Settings` class read from the environment (`NTK_DETECTOR`, upload limits).
3. PDF in, text out: read every page's text; refuse a file that is not a PDF or has no text.
4. A detector interface (`detect(text) -> spans`) and the dumbest detector that fits it.
5. Redaction that removes the text, with a test that re-reads the output to prove it.
6. The API: `/api/detect`, `/api/redact`, `/health`, `/ready`, with schemas.
7. The page: upload, review, download.
8. Docker and Compose; deploy on Jetstream2; only the app's port open.

## Milestone 2: measure
9. Run the baseline on pdf-pii-bench with the benchmark's own scorer; record recall and precision by type.
10. Error analysis: what does it miss, and in which kinds of documents?

## Milestone 3: first users (Homework 3)
11. Write the user brief; open the testing window; answer every issue.

## Milestone 4: iterate
12. Try better detectors behind the same interface; pick one by the numbers and by what users said.
13. Ship it by changing a setting, and measure again.
