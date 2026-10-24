"""The GLiNER weights are downloaded by name, so we pin the exact commit, as uv.lock does for our packages."""

import re
import sys
import types

from needtoknow.config import Settings


def test_default_revision_is_a_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", Settings(_env_file=None).gliner_revision)


def test_detector_asks_for_that_revision(monkeypatch):
    asked = {}

    class FakeGLiNER:
        @staticmethod
        def from_pretrained(model, revision=None):
            asked.update(model=model, revision=revision)
            return object()

    monkeypatch.setitem(sys.modules, "gliner", types.SimpleNamespace(GLiNER=FakeGLiNER))
    monkeypatch.delitem(sys.modules, "needtoknow.detectors.gliner", raising=False)
    from needtoknow.detectors import build_detector

    build_detector("gliner", gliner_model="m", gliner_threshold=0.5, gliner_revision="abc123")
    assert asked == {"model": "m", "revision": "abc123"}
