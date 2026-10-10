"""Measure a detector on pdf-pii-bench (Catherine Nelson, CC BY 4.0, https://github.com/callixdev/pdf-pii-bench).

    uv run needtoknow-eval --bench eval/pdf-pii-bench --detector regex

Writes eval/predictions/<detector>.json in the benchmark's format, so its own scorer can check our numbers:
    cd eval/pdf-pii-bench && uv run python -m src.score_predictions ../predictions/regex.json
and prints the character-level ("redaction") recall and precision, by label and by document category, plus the
spans we missed most often: the start of error analysis.
"""

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from needtoknow.config import settings
from needtoknow.detectors import build_detector


def char_sets(spans, skip_space=True):
    """Character offsets covered by spans. Whitespace never counts: a space leaks nothing."""
    covered = set()
    for sp in spans:
        covered.update(sp["start"] + i for i, ch in enumerate(sp["text"]) if not (skip_space and ch.isspace()))
    return covered


def evaluate(bench: Path, detector_name: str, out_dir: Path) -> dict:
    texts = json.loads((bench / "data/text_data.json").read_text())
    truth = json.loads((bench / "data/ground_truth.json").read_text())
    detector = build_detector(detector_name, gliner_model=settings.gliner_model, gliner_threshold=settings.gliner_threshold)

    t0 = time.monotonic()
    predictions = {doc: [s.as_dict() for s in detector.detect(d["text"])] for doc, d in texts.items()}
    seconds = time.monotonic() - t0
    for spans in predictions.values():
        for s in spans:
            s.pop("source", None)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{detector_name}.json").write_text(json.dumps(predictions, indent=1))

    # Character-level redaction scores, the way a leak is felt, scored as the benchmark scores them: only an
    # individual's details count; an organization's or agency's details are neutral (no credit, no penalty).
    by_label = defaultdict(lambda: [0, 0])      # label -> [covered chars, true chars]
    by_category = defaultdict(lambda: [0, 0])
    tp = fp_chars = 0
    missed = Counter()
    for doc, gold_all in truth.items():
        gold = [g for g in gold_all if g.get("subject", "person") == "person"]
        neutral = {i for g in gold_all if g.get("subject", "person") != "person" for i in range(g["start"], g["end"])}
        predicted = char_sets(predictions[doc]) - neutral
        true_chars = char_sets(gold)
        tp += len(predicted & true_chars)
        fp_chars += len(predicted - true_chars)
        category = texts[doc].get("category", "?")
        for g in gold:
            chars = char_sets([g])
            hit = len(chars & predicted)
            by_label[g["label"]][0] += hit
            by_label[g["label"]][1] += len(chars)
            by_category[category][0] += hit
            by_category[category][1] += len(chars)
            if hit < len(chars) / 2:
                missed[(g["label"], g["text"])] += 1
    total_true = sum(v[1] for v in by_label.values())
    result = {
        "detector": detector_name,
        "seconds": round(seconds, 1),
        "recall": round(tp / total_true, 3),
        "precision": round(tp / (tp + fp_chars), 3) if tp + fp_chars else 0.0,
        "recall_by_label": {k: round(v[0] / v[1], 3) for k, v in sorted(by_label.items())},
        "recall_by_category": {k: round(v[0] / v[1], 3) for k, v in sorted(by_category.items())},
        "most_missed": [f"{label}: {text}" for (label, text), _ in missed.most_common(15)],
    }
    (out_dir / f"{detector_name}.scores.json").write_text(json.dumps(result, indent=1))
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bench", type=Path, default=Path("eval/pdf-pii-bench"))
    p.add_argument("--detector", default=settings.detector)
    p.add_argument("--out", type=Path, default=Path("eval/predictions"))
    r = evaluate(p.parse_args().bench, p.parse_args().detector, p.parse_args().out)
    print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
