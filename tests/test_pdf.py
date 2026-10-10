import pymupdf
import pytest

from needtoknow.pdf import NotAPdf, NoTextLayer, extract_pages, leaked, redact


def test_redaction_removes_the_text_not_just_covers_it(sample_pdf):
    items = [(0, "123-45-6789"), (0, "maria.delgado@example.com")]
    out = redact(sample_pdf, items)
    text = pymupdf.open(stream=out, filetype="pdf")[0].get_text()
    assert "123-45-6789" not in text and "maria.delgado@example.com" not in text
    assert "LEASE AGREEMENT" in text  # everything else is still there
    assert leaked(out, items) == []


def test_not_a_pdf():
    with pytest.raises(NotAPdf):
        extract_pages(b"hello, I am a Word document", max_pages=10)


def test_no_text_layer():
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(NoTextLayer):
        extract_pages(doc.tobytes(), max_pages=10)
