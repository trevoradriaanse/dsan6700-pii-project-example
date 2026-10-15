import pymupdf
import pytest

SAMPLE = [
    "LEASE AGREEMENT",
    "Tenant: Maria Delgado, phone (202) 555-0143, email maria.delgado@example.com",
    "Premises: 1450 Oak Street, Apt 3B, Arlington, VA 22201",
    "SSN: 123-45-6789   Bank account: 004417829931   Lease start: 03/01/2026",
]


def make_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((50, 72 + 18 * i), line, fontsize=10)
    return doc.tobytes()


@pytest.fixture
def sample_pdf() -> bytes:
    return make_pdf(SAMPLE)


@pytest.fixture
def counting(tmp_path, monkeypatch):
    """Turn the usage counts on, in a fresh database brought up to date by the migrations."""
    from needtoknow import migrate
    from needtoknow.config import settings

    path = str(tmp_path / "needtoknow.db")
    monkeypatch.setattr(settings, "db_path", path)
    migrate.up(path)
    return path
