"""Unit tests for harness/retrieve.py.

Verifies:
1. Two-pass retrieval: scores everything first, then gates.
2. Denied passages have their text discarded at the gate.
3. Denial carries doc_id and reason, NEVER text.
4. top_k counts readable passages, not candidates (walks past denied matches).
5. Denials are collapsed per document ID, not per passage.
"""

from contracts import Compartment, Label, Passage, Principal, Tier
from harness.retrieve import retrieve


def test_two_pass_scoring_and_gating():
    """Restricted passages with higher relevance are scored first, then denied at the gate."""
    # User is an Executive with only HSE clearance
    user = Principal(
        person_id="eng-01",
        name="Process Engineer",
        job_title="Engineer",
        grade="A",
        compartments=frozenset([Compartment.HSE]),
    )

    # Passage 1: Highly relevant to "vigilance investigation", but restricted under VIGILANCE
    p1 = Passage(
        doc_id="vig-report-2025",
        page=1,
        title="Vigilance Inquiry Report",
        text="Formal vigilance investigation into contractor procurement irregularities at refinery site.",
        label=Label(tier=Tier.CONFIDENTIAL, compartments=frozenset([Compartment.VIGILANCE])),
    )

    # Passage 2: Moderate relevance, readable under HSE
    p2 = Passage(
        doc_id="hse-sop-101",
        page=1,
        title="HSE Incident Investigation",
        text="Standard procedure for reporting and investigation of safety incidents on site.",
        label=Label(tier=Tier.CONFIDENTIAL, compartments=frozenset([Compartment.HSE])),
    )

    corpus = [p1, p2]
    allowed, denials = retrieve(
        query="vigilance investigation report",
        corpus=corpus,
        principal=user,
        top_k=2,
    )

    # p1 is denied, p2 is allowed
    assert len(allowed) == 1
    assert allowed[0].doc_id == "hse-sop-101"

    # Denial recorded for p1
    assert len(denials) == 1
    assert denials[0].doc_id == "vig-report-2025"
    assert "Missing required compartment(s): vigilance" in denials[0].reason

    # CRITICAL: Denial carries NO text field
    assert not hasattr(denials[0], "text")


def test_top_k_counts_readable_passages():
    """top_k counts readable passages, continuing to walk past denied candidates."""
    user = Principal(
        person_id="worker-01",
        name="Worker",
        job_title="Staff",
        grade="S1",  # Rank 1 (Internal only)
        compartments=frozenset(),
    )

    # 3 Secret passages (denied), followed by 2 Internal passages (allowed)
    p_secret_1 = Passage(doc_id="sec-1", page=1, text="fire safety secret 1", label=Label(tier=Tier.SECRET))
    p_secret_2 = Passage(doc_id="sec-2", page=1, text="fire safety secret 2", label=Label(tier=Tier.SECRET))
    p_secret_3 = Passage(doc_id="sec-3", page=1, text="fire safety secret 3", label=Label(tier=Tier.SECRET))
    p_internal_1 = Passage(doc_id="int-1", page=1, text="fire safety internal 1", label=Label(tier=Tier.INTERNAL))
    p_internal_2 = Passage(doc_id="int-2", page=1, text="fire safety internal 2", label=Label(tier=Tier.INTERNAL))

    corpus = [p_secret_1, p_secret_2, p_secret_3, p_internal_1, p_internal_2]

    # Asking for top_k=2 readable passages
    allowed, denials = retrieve(
        query="fire safety",
        corpus=corpus,
        principal=user,
        top_k=2,
    )

    # Must walk past the 3 secret passages and gather the 2 readable ones
    assert len(allowed) == 2
    assert {p.doc_id for p in allowed} == {"int-1", "int-2"}
    assert len(denials) == 3


def test_collapse_denials_per_document():
    """Multiple withheld pages from the same document produce exactly ONE denial entry."""
    user = Principal(
        person_id="worker-01",
        name="Worker",
        job_title="Staff",
        grade="S1",
        compartments=frozenset(),
    )

    p1 = Passage(doc_id="sec-doc", page=1, text="refinery crude secret page 1", label=Label(tier=Tier.SECRET))
    p2 = Passage(doc_id="sec-doc", page=2, text="refinery crude secret page 2", label=Label(tier=Tier.SECRET))
    p3 = Passage(doc_id="sec-doc", page=3, text="refinery crude secret page 3", label=Label(tier=Tier.SECRET))

    allowed, denials = retrieve(
        query="refinery crude secret",
        corpus=[p1, p2, p3],
        principal=user,
        top_k=3,
    )

    assert len(allowed) == 0
    # Exactly one denial for sec-doc, not three!
    assert len(denials) == 1
    assert denials[0].doc_id == "sec-doc"
