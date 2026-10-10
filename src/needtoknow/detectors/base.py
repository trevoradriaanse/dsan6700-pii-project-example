"""What every detector returns: spans of text, with a label, by character offset."""

from dataclasses import asdict, dataclass
from typing import Protocol

# The labels follow pdf-pii-bench (and openai/privacy-filter), so our scores compare with published ones.
LABELS = (
    "private_person",
    "private_email",
    "private_phone",
    "private_address",
    "private_url",
    "private_date",
    "account_number",
    "secret",
)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str
    text: str
    source: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class Detector(Protocol):
    name: str

    def detect(self, text: str) -> list[Span]: ...


def merge(spans: list[Span]) -> list[Span]:
    """Sort spans and drop any span that sits entirely inside a longer one."""
    spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    kept: list[Span] = []
    for s in spans:
        if kept and s.start >= kept[-1].start and s.end <= kept[-1].end:
            continue
        kept.append(s)
    return kept
