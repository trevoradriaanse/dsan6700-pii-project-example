"""Read text out of a PDF, and write a copy with chosen text removed (not covered: removed)."""

from dataclasses import dataclass

import pymupdf


class NotAPdf(ValueError):
    pass


class NoTextLayer(ValueError):
    pass


@dataclass
class Page:
    number: int  # 0-based
    text: str


def open_pdf(data: bytes) -> pymupdf.Document:
    if not data.startswith(b"%PDF"):
        raise NotAPdf("the file is not a PDF")
    try:
        return pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # a damaged file
        raise NotAPdf(f"the PDF could not be read: {exc}") from exc


def extract_pages(data: bytes, max_pages: int) -> list[Page]:
    doc = open_pdf(data)
    if doc.page_count > max_pages:
        raise ValueError(f"the PDF has {doc.page_count} pages; the limit is {max_pages}")
    pages = [Page(i, page.get_text()) for i, page in enumerate(doc)]
    if not any(p.text.strip() for p in pages):
        raise NoTextLayer("the PDF has no text layer (a scan?); scanned documents are not supported yet")
    return pages


def redact(data: bytes, items: list[tuple[int, str]]) -> bytes:
    """Remove every occurrence of each (page, text) pair and return the new PDF's bytes."""
    doc = open_pdf(data)
    for number, text in items:
        if not text.strip() or not 0 <= number < doc.page_count:
            continue
        page = doc[number]
        for rect in page.search_for(text):
            page.add_redact_annot(rect, fill=(0, 0, 0))
    for page in doc:
        page.apply_redactions()  # this is the step that deletes the text under each box
    return doc.tobytes(garbage=4, deflate=True)


def leaked(data: bytes, items: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Which of the items can still be found as text in the PDF? Used to check our own output."""
    doc = open_pdf(data)
    return [(n, t) for n, t in items if t.strip() and 0 <= n < doc.page_count and t in doc[n].get_text()]
