"""Unit tests for ingest/pdf.py and test fixtures.

Verifies:
1. Extraction of normal 2-page PDF into page-scoped passages.
2. Loud ScannedPdfError when encountering a PDF with 0 extractable text.
3. Mixed-page PDF gracefully retains text pages and skips blank ones.
4. load_corpus handles missing/empty directory gracefully.
"""

from pathlib import Path
import pytest
from contracts import Label, Tier
from ingest.pdf import (
    ScannedPdfError,
    load_corpus,
    pdf_to_page_texts,
    pdf_to_passages,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_normal_2page_extraction():
    """Extract page texts and passages from standard 2-page digital PDF."""
    pdf_path = FIXTURES_DIR / "normal_2page.pdf"
    assert pdf_path.exists()

    texts = pdf_to_page_texts(pdf_path)
    assert len(texts) == 2
    assert "page one text" in texts[0]
    assert "emergency shutdown instructions" in texts[1]

    passages = pdf_to_passages(
        pdf_path=pdf_path,
        doc_id="test-doc-01",
        label=Label(tier=Tier.INTERNAL),
        title="Test Document",
    )
    assert len(passages) == 2
    assert passages[0].page == 1
    assert passages[0].doc_id == "test-doc-01"
    assert passages[1].page == 2


def test_scanned_pdf_raises_loud_error():
    """A scanned or empty PDF with zero text must raise ScannedPdfError."""
    pdf_path = FIXTURES_DIR / "scanned_notext.pdf"
    assert pdf_path.exists()

    with pytest.raises(ScannedPdfError, match="SCANNED PDF ERROR.*scanned_notext.pdf"):
        pdf_to_page_texts(pdf_path)


def test_mixed_pages_skips_blank_page():
    """A document with mixed text and blank pages skips the blank page."""
    pdf_path = FIXTURES_DIR / "mixed_pages.pdf"
    assert pdf_path.exists()

    passages = pdf_to_passages(
        pdf_path=pdf_path,
        doc_id="mixed-doc",
        label=Label(tier=Tier.INTERNAL),
    )
    # Page 1 has text, page 2 is blank -> exactly 1 passage returned
    assert len(passages) == 1
    assert passages[0].page == 1
    assert "daily throughput logs" in passages[0].text


def test_load_corpus_empty_or_missing_dir(tmp_path: Path):
    """load_corpus handles missing or empty directories without crashing."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]", encoding="utf-8")

    empty_docs = tmp_path / "empty_docs"
    empty_docs.mkdir()

    # Empty dir
    res = load_corpus(manifest, empty_docs)
    assert res == []

    # Non-existent dir
    res2 = load_corpus(manifest, tmp_path / "non_existent")
    assert res2 == []

def test_ocr_fallback_recovers_text_from_image_only_pdf():
    """A PDF with no embedded text layer, but real text baked into the image,
    should be recovered via OCR when enable_ocr=True."""
    import pytest
    # OCR is an opt-in feature (SEVERANCE_ENABLE_OCR) backed by an optional,
    # heavyweight dependency that isn't in requirements.txt.
    pytest.importorskip("paddleocr")
    from ingest.pdf import pdf_to_page_texts
    pages = pdf_to_page_texts("tests/fixtures/scanned_real_text.pdf", enable_ocr=True)
    assert any("Assembly" in p or "Gate" in p for p in pages)

def test_ocr_disabled_by_default_still_raises():
    """Same file, default enable_ocr=False, must still raise loudly -- proves
    the new capability is opt-in and doesn't change existing behavior."""
    from ingest.pdf import pdf_to_page_texts, ScannedPdfError
    import pytest
    with pytest.raises(ScannedPdfError):
        pdf_to_page_texts("tests/fixtures/scanned_real_text.pdf")
