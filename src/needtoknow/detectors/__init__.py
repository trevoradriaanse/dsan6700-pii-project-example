"""Detectors find personal information in text. The one in use is chosen by the NTK_DETECTOR setting."""

from needtoknow.detectors.base import LABELS, Detector, Span, merge
from needtoknow.detectors.regex import RegexDetector


class UnionDetector:
    """Run several detectors and keep everything any of them found."""

    def __init__(self, *detectors: Detector) -> None:
        self.detectors = detectors
        self.name = "+".join(d.name for d in detectors)

    def detect(self, text: str) -> list[Span]:
        return merge([s for d in self.detectors for s in d.detect(text)])


def build_detector(name: str, **kwargs) -> Detector:
    """Build the detector named in settings. Heavy ones are imported only when asked for."""
    if name == "regex":
        return RegexDetector()
    if name == "presidio":
        from needtoknow.detectors.presidio import PresidioDetector

        return PresidioDetector()
    if name == "gliner":
        from needtoknow.detectors.gliner import GlinerDetector

        return GlinerDetector(kwargs.get("gliner_model", "urchade/gliner_multi_pii-v1"), kwargs.get("gliner_threshold", 0.5),
                              kwargs.get("gliner_revision"))
    if name == "regex+gliner":
        return UnionDetector(RegexDetector(), build_detector("gliner", **kwargs))
    raise ValueError(f"unknown detector {name!r}")


__all__ = ["LABELS", "Detector", "RegexDetector", "Span", "UnionDetector", "build_detector", "merge"]
