"""Read text out of a PDF, and write a copy with chosen text removed (not covered: removed)."""

from dataclasses import dataclass

import pymupdf


class NotAPdf(ValueError):
    pass


class NoTextLayer(ValueError):
    pass


class TooManyPages(ValueError):
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


def check_pages(doc: pymupdf.Document, max_pages: int) -> None:
    if doc.page_count > max_pages:
        raise TooManyPages(f"the PDF has {doc.page_count} pages; the limit is {max_pages}")


def extract_pages(data: bytes, max_pages: int) -> list[Page]:
    doc = open_pdf(data)
    check_pages(doc, max_pages)
    pages = [Page(i, page.get_text()) for i, page in enumerate(doc)]
    if not any(p.text.strip() for p in pages):
        raise NoTextLayer("the PDF has no text layer (a scan?); scanned documents are not supported yet")
    return pages


def redact(data: bytes, items: list[tuple[int, str]], max_pages: int = 30) -> bytes:
    """Remove every occurrence of each (page, text) pair and return the new PDF's bytes."""
    doc = open_pdf(data)
    check_pages(doc, max_pages)
    for number, text in items:
        if not text.strip() or not 0 <= number < doc.page_count:
            continue
        page = doc[number]
        for rect in page.search_for(text):
            page.add_redact_annot(rect, fill=(0, 0, 0))
    for page in doc:
        page.apply_redactions()  # this is the step that deletes the text under each box
    # The page is not the only place a name hides: the title and author fields often carry one too.
    doc.set_metadata({})
    doc.del_xml_metadata()
    return doc.tobytes(garbage=4, deflate=True)


def _norm(text: str) -> str:
    """Compare text the way a reader would: ignore case and line breaks."""
    return " ".join(text.split()).casefold()


def leaked(data: bytes, items: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Which of the items can still be found in the PDF, on its page or in its metadata? Used to check our output."""
    doc = open_pdf(data)
    meta = _norm(" ".join(v for v in doc.metadata.values() if v) + " " + (doc.get_xml_metadata() or ""))
    return [(n, t) for n, t in items
            if t.strip() and 0 <= n < doc.page_count and (_norm(t) in _norm(doc[n].get_text()) or _norm(t) in meta)]
