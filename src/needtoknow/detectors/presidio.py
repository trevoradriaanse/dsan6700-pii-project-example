"""Presidio: Microsoft's open-source PII analyzer (regular expressions with checksums, plus spaCy for names and places)."""

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from needtoknow.detectors.base import Span, merge

# Presidio's entity names mapped to the benchmark's labels. Anything not listed is ignored.
TO_LABEL = {
    "PERSON": "private_person",
    "EMAIL_ADDRESS": "private_email",
    "PHONE_NUMBER": "private_phone",
    "LOCATION": "private_address",
    "URL": "private_url",
    "DATE_TIME": "private_date",
    "US_SSN": "account_number",
    "US_ITIN": "account_number",
    "US_BANK_NUMBER": "account_number",
    "CREDIT_CARD": "account_number",
    "IBAN_CODE": "account_number",
    "US_DRIVER_LICENSE": "account_number",
    "US_PASSPORT": "account_number",
}


class PresidioDetector:
    name = "presidio"

    def __init__(self, threshold: float = 0.35) -> None:
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]})
        self.engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        self.threshold = threshold

    def detect(self, text: str) -> list[Span]:
        results = self.engine.analyze(text=text, language="en", entities=list(TO_LABEL), score_threshold=self.threshold)
        return merge([Span(r.start, r.end, TO_LABEL[r.entity_type], text[r.start:r.end], self.name) for r in results])
