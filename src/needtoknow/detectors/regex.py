"""The baseline: regular expressions for the kinds of personal information that have a fixed shape.

It cannot find names, and it only finds street addresses written in a common form. That is the point of a baseline:
it is quick to build, easy to explain, and tells us how much a model has to add.
"""

import re

from needtoknow.detectors.base import Span, merge

MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
STREET = r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Terrace|Ter|Parkway|Pkwy|Circle|Cir|Highway|Hwy)\b"

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private_email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("private_url", re.compile(r"\bhttps?://[^\s)>\]]+|\bwww\.[\w-]+(?:\.[\w-]+)+[^\s)>\]]*")),
    # Social Security and employer ID numbers, including masked forms such as XXX-XX-6741.
    ("account_number", re.compile(r"\b(?:\d{3}|[X*]{3})-(?:\d{2}|[X*]{2})-\d{4}\b")),
    ("account_number", re.compile(r"\b\d{2}-\d{7}\b")),
    # Card, bank and other long account numbers: 6 to 19 digits, optionally grouped, optionally masked.
    ("account_number", re.compile(r"(?<![\w.])(?:[X*]{2,}[- ]?)*\d{4,}(?:[- ]\d{2,}){0,4}(?![\w.])")),
    ("private_phone", re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]\d{4}(?!\d)")),
    ("private_date", re.compile(r"\b\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})\b")),
    ("private_date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("private_date", re.compile(rf"\b{MONTHS}\.? \d{{1,2}}(?:st|nd|rd|th)?,? \d{{4}}\b")),
    ("private_date", re.compile(rf"\b\d{{1,2}} {MONTHS}\.? \d{{4}}\b")),
    ("private_address", re.compile(
        rf"\b\d{{1,6}}(?: [A-Z0-9][\w.]*){{1,4}} {STREET}\.?(?:,? (?:Apt|Suite|Unit|#)\.? ?[\w-]+)?"
        rf"(?:,? [A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)*,? [A-Z]{{2}} \d{{5}}(?:-\d{{4}})?)?")),
]


class RegexDetector:
    name = "regex"

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for label, pattern in PATTERNS:
            for m in pattern.finditer(text):
                value = m.group(0)
                if label == "account_number" and sum(c.isdigit() for c in value) < 6 and "X" not in value and "*" not in value:
                    continue  # short numbers (amounts, years, zip codes) are not account numbers
                if label == "private_phone" and len(re.sub(r"\D", "", value)) not in (10, 11):
                    continue
                end = m.end()
                while label == "private_url" and value and value[-1] in ".,;:!?'\"":
                    value, end = value[:-1], end - 1  # a sentence's punctuation is not part of the address
                spans.append(Span(m.start(), end, label, value, self.name))
        return merge(spans)
