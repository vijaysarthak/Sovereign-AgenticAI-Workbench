"""Unit tests for harness/verify.py and citation safety checks (Step 6b).

Verifies:
1. Pydantic validation rejects short quotes (e.g. "2.", "3.", "5.").
2. Quotes with fewer than 5 words are rejected.
3. verify.check() confirms quotes appear verbatim in claimed doc_id AND page.
4. A quote existing in a DIFFERENT page of the same document is rejected.
5. Exact verbatim substring on matching doc_id and page passes cleanly.
"""

import pytest
from pydantic import ValidationError
from contracts import Citation, Label, Passage, Tier
from harness.verify import check as verify_check


def test_numbered_list_marker_rejected():
    """Rule: Never derive citations by parsing prose. Reconstruct markers like '2.' are rejected."""
    with pytest.raises(ValidationError, match="at least 20 characters"):
        Citation(doc_id="doc-01", page=1, quote="2.")


def test_fewer_than_five_words_rejected():
    """A bare document title or short phrase (< 5 words) is rejected even if >= 20 characters."""
    # 21 characters, but only 3 words
    with pytest.raises(ValidationError, match="at least 5 words"):
        Citation(doc_id="doc-01", page=1, quote="Refinery Safety Report")


def test_quote_on_wrong_page_rejected():
    """A quote that exists in page 2 of a document, but is cited as page 1, is rejected."""
    p1 = Passage(
        doc_id="sop-101",
        page=1,
        text="Introduction to crude distillation unit operating parameters and daily throughput logs.",
        label=Label(tier=Tier.INTERNAL),
    )
    p2 = Passage(
        doc_id="sop-101",
        page=2,
        text="Emergency shutdown valve 201-XV-01 must be actuated immediately upon high pressure alarm.",
        label=Label(tier=Tier.INTERNAL),
    )

    # Citation claims the quote is on page 1, but it is actually on page 2
    cit = Citation(
        doc_id="sop-101",
        page=1,
        quote="Emergency shutdown valve 201-XV-01 must be actuated immediately upon high pressure alarm.",
    )

    failure = verify_check([cit], [p1, p2])
    assert failure is not None
    assert "was NOT found verbatim in doc_id='sop-101' page 1" in failure


def test_valid_exact_citation_passes():
    """Verbatim quote matching exact doc_id and page passes verification cleanly."""
    quote_text = "Emergency shutdown valve 201-XV-01 must be actuated immediately upon high pressure alarm."
    p2 = Passage(
        doc_id="sop-101",
        page=2,
        text=f"Section 4.1: {quote_text} Follow with nitrogen purge.",
        label=Label(tier=Tier.INTERNAL),
    )

    cit = Citation(doc_id="sop-101", page=2, quote=quote_text)
    assert verify_check([cit], [p2]) is None
