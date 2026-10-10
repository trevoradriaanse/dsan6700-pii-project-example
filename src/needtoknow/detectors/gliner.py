"""GLiNER: a small transformer that finds entities of any type you name, here the benchmark's personal-information types."""

from gliner import GLiNER

from needtoknow.detectors.base import Span, merge

# What we ask the model to find, mapped to the benchmark's labels.
PROMPTS = {
    "person": "private_person",
    "email": "private_email",
    "phone number": "private_phone",
    "address": "private_address",
    "url": "private_url",
    "date": "private_date",
    "date of birth": "private_date",
    "social security number": "account_number",
    "bank account number": "account_number",
    "credit card number": "account_number",
    "account number": "account_number",
    "tax identification number": "account_number",
    "password": "secret",
}

WINDOW = 1200  # characters per call: the model reads about 384 tokens at a time
OVERLAP = 200


class GlinerDetector:
    name = "gliner"

    def __init__(self, model: str = "urchade/gliner_multi_pii-v1", threshold: float = 0.5) -> None:
        self.model = GLiNER.from_pretrained(model)  # loaded once, when the service starts
        self.threshold = threshold

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        start = 0
        while start < len(text):
            chunk = text[start:start + WINDOW]
            for e in self.model.predict_entities(chunk, list(PROMPTS), threshold=self.threshold):
                s, t = start + e["start"], start + e["end"]
                spans.append(Span(s, t, PROMPTS[e["label"]], text[s:t], self.name))
            if start + WINDOW >= len(text):
                break
            start += WINDOW - OVERLAP
        return merge(spans)
