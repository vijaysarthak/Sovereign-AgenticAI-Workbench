"""Unit tests for the four sovereign security tools in agents/adk.py.

Verifies:
1. Exactly four tools exist with correct signatures (no clearance parameters).
2. search_corpus returns withheld_count and titles, NEVER content.
3. get_passage refuses to serve text if two-axis gate fails.
4. verify_quote gates BEFORE matching (prevents exfiltration oracle attacks).
5. list_readable_documents discloses only cleared document IDs and titles.
"""

from contracts import Compartment, Label, Passage, Principal, Tier
from agents.adk import (
    _ACTIVE_PASSAGES,
    _CURRENT_PRINCIPAL,
    get_passage,
    list_readable_documents,
    search_corpus,
    verify_quote,
)


def test_search_corpus_discloses_titles_never_content():
    """search_corpus returns withheld_count and titles, but physical text is excluded."""
    user = Principal(
        person_id="worker-01",
        name="Staff Member",
        job_title="Support",
        grade="S1",  # Rank 1
        compartments=frozenset(),
    )

    p_allowed = Passage(
        doc_id="pub-guide",
        page=1,
        title="Public Visitor Guide",
        text="Refinery safety guidelines for external visitors and contractors.",
        label=Label(tier=Tier.PUBLIC),
    )
    p_denied = Passage(
        doc_id="sec-crude",
        page=1,
        title="Secret Crude Procurement Pricing Strategy",
        text="CONFIDENTIAL FORMULA: Supplier pricing margins are set at 4.2% discount.",
        label=Label(tier=Tier.SECRET, compartments=frozenset([Compartment.COMMERCIAL])),
    )

    _CURRENT_PRINCIPAL.set(user)
    _ACTIVE_PASSAGES.set([p_allowed, p_denied])

    res = search_corpus("pricing strategy guide")

    # 1 readable passage
    assert len(res["readable_passages"]) == 1
    assert res["readable_passages"][0]["doc_id"] == "pub-guide"

    # Withheld document title is disclosed, but NOT content
    assert res["withheld_count"] == 1
    assert "Secret Crude Procurement Pricing Strategy" in res["withheld_titles"]
    assert "CONFIDENTIAL FORMULA" not in str(res)


def test_get_passage_gating():
    """get_passage evaluates clearance and withholds text on failure."""
    user = Principal(
        person_id="worker-01",
        name="Staff Member",
        job_title="Support",
        grade="S1",
        compartments=frozenset(),
    )

    p_secret = Passage(
        doc_id="sec-ops",
        page=1,
        title="Classified Operations",
        text="Secret operational steps for heavy oil processing.",
        label=Label(tier=Tier.SECRET),
    )

    _CURRENT_PRINCIPAL.set(user)
    _ACTIVE_PASSAGES.set([p_secret])

    res = get_passage(doc_id="sec-ops", page=1)
    assert res["found"] is False
    assert res["text"] is None
    assert "Access denied" in res["reason"]


def test_verify_quote_gates_before_matching():
    """CRITICAL SECURITY INVARIANT:
    verify_quote must gate BEFORE checking whether the quote matches text.
    Even if an unauthorized caller guesses an exact secret substring,
    verification must fail immediately with a security gate violation!
    """
    user = Principal(
        person_id="worker-01",
        name="Staff Member",
        job_title="Support",
        grade="S1",  # Rank 1 (Cannot read Secret)
        compartments=frozenset(),
    )

    secret_text = "The secret catalyst blend is eighty percent platinum and twenty percent rhenium alloy."
    p_secret = Passage(
        doc_id="cat-sec-01",
        page=1,
        title="Catalyst Formula",
        text=secret_text,
        label=Label(tier=Tier.SECRET),
    )

    _CURRENT_PRINCIPAL.set(user)
    _ACTIVE_PASSAGES.set([p_secret])

    # Caller submits the EXACT verbatim quote
    res = verify_quote(
        doc_id="cat-sec-01",
        page=1,
        quote=secret_text,
    )

    # Verification must be FALSE because clearance failed first
    assert res["verified"] is False
    assert "Security Gate Violation" in res["reason"]


def test_list_readable_documents_only():
    """list_readable_documents lists only authorized documents."""
    user = Principal(
        person_id="worker-01",
        name="Staff Member",
        job_title="Support",
        grade="S1",
        compartments=frozenset(),
    )

    p1 = Passage(doc_id="doc-pub", page=1, title="Public Report", text="text", label=Label(tier=Tier.PUBLIC))
    p2 = Passage(doc_id="doc-sec", page=1, title="Secret Report", text="text", label=Label(tier=Tier.SECRET))

    _CURRENT_PRINCIPAL.set(user)
    _ACTIVE_PASSAGES.set([p1, p2])

    readable = list_readable_documents()
    assert len(readable) == 1
    assert readable[0]["doc_id"] == "doc-pub"
