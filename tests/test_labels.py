"""Unit tests for trust/labels.py.

Verifies:
1. Two-axis access control (can_read).
2. Rank floor gating against MRPL grade structure.
3. Compartment containment gating.
4. The headline demo inversion: GM denied vigilance, AM allowed.
5. Fail-closed security on unrecognized inputs.
6. Deterministic denial reasons.
7. Classification inheritance (highest tier + union of compartments).
"""

import pytest
from contracts import Compartment, Label, Principal, Tier
from trust.labels import RANK, TIER_FLOOR, can_read, denial_reason, inherit_label


def test_mrpl_grade_ranking():
    """Verify that all MRPL officer and non-management grades map to ranked integers."""
    # Officers A through I must be strictly increasing
    officer_grades = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    for i in range(len(officer_grades) - 1):
        assert RANK[officer_grades[i]] < RANK[officer_grades[i + 1]]

    # All expected non-management grades exist
    for g in ["S1", "S2", "S3", "S4", "JM1", "JM2", "JM6", "TS1", "TS2", "TS6"]:
        assert g in RANK
        assert RANK[g] >= 1


def test_can_read_public_tier():
    """Public tier is readable by any valid employee regardless of compartments."""
    p_worker = Principal(
        person_id="worker-01",
        name="Staff Member",
        job_title="Support Staff",
        grade="S1",
        compartments=frozenset(),
    )
    lbl_public = Label(tier=Tier.PUBLIC, compartments=frozenset())
    assert can_read(p_worker, lbl_public) is True


def test_can_read_insufficient_rank():
    """A non-management staff member cannot read Confidential or Secret documents."""
    p_worker = Principal(
        person_id="worker-01",
        name="Staff Member",
        job_title="Support Staff",
        grade="S2",  # Rank 2
        compartments=frozenset(),
    )
    lbl_confidential = Label(tier=Tier.CONFIDENTIAL, compartments=frozenset())
    assert can_read(p_worker, lbl_confidential) is False

    reason = denial_reason(p_worker, lbl_confidential)
    assert "Insufficient rank" in reason
    assert "S2" in reason


def test_can_read_missing_compartment():
    """An executive with sufficient rank is denied if missing a required compartment."""
    p_exec = Principal(
        person_id="exec-01",
        name="Executive Officer",
        job_title="Executive",
        grade="A",  # Rank 7 >= Confidential floor 7
        compartments=frozenset([Compartment.HSE]),
    )
    lbl_legal = Label(tier=Tier.CONFIDENTIAL, compartments=frozenset([Compartment.LEGAL]))
    assert can_read(p_exec, lbl_legal) is False

    reason = denial_reason(p_exec, lbl_legal)
    assert "Missing required compartment(s): legal" in reason


def test_the_headline_inversion_demo():
    """THE HEADLINE DEMO:
    A General Manager (Grade F, outranking everyone) without the vigilance compartment
    is DENIED vigilance material.
    An Assistant Manager (Grade A) WITH the vigilance compartment is ALLOWED.
    High rank NEVER implies compartment access!
    """
    # 1. General Manager (Grade F, Rank 12)
    gm = Principal(
        person_id="gm-001",
        name="Sunil Nayak",
        job_title="General Manager (Refining)",
        grade="F",
        compartments=frozenset([Compartment.COMMERCIAL, Compartment.TECHNICAL]),
    )

    # 2. Assistant Manager (Grade A, Rank 7)
    am = Principal(
        person_id="am-001",
        name="Deepa Shenoy",
        job_title="Assistant Manager (Vigilance Cell)",
        grade="A",
        compartments=frozenset([Compartment.VIGILANCE]),
    )

    # 3. Confidential Vigilance Investigation Document
    vigilance_doc = Label(
        tier=Tier.CONFIDENTIAL,  # Requires Rank >= 7
        compartments=frozenset([Compartment.VIGILANCE]),
    )

    # The General Manager is DENIED
    assert can_read(gm, vigilance_doc) is False
    gm_reason = denial_reason(gm, vigilance_doc)
    assert "Missing required compartment(s): vigilance" in gm_reason
    assert "Insufficient rank" not in gm_reason  # GM has plenty of rank!

    # The Assistant Manager is ALLOWED
    assert can_read(am, vigilance_doc) is True


def test_fails_closed_on_invalid_data():
    """can_read fails closed (returns False) on any unexpected or invalid object."""
    p = Principal(
        person_id="test-01",
        name="Tester",
        job_title="QA",
        grade="A",
        compartments=frozenset(),
    )
    lbl = Label(tier=Tier.INTERNAL, compartments=frozenset())

    # None inputs
    assert can_read(None, lbl) is False  # type: ignore
    assert can_read(p, None) is False  # type: ignore

    # Non-principal or non-label types
    assert can_read("not a principal", lbl) is False  # type: ignore
    assert can_read(p, "not a label") is False  # type: ignore


def test_inherit_label():
    """Classification inheritance takes the highest tier and union of compartments."""
    # 1. Empty set defaults to Public with no compartments
    assert inherit_label([]) == Label(tier=Tier.PUBLIC, compartments=frozenset())

    # 2. Single label passes through
    lbl1 = Label(tier=Tier.INTERNAL, compartments=frozenset([Compartment.HSE]))
    assert inherit_label([lbl1]) == lbl1

    # 3. Multiple labels inherit highest tier and union of compartments
    lbl2 = Label(tier=Tier.SECRET, compartments=frozenset([Compartment.TECHNICAL]))
    lbl3 = Label(tier=Tier.CONFIDENTIAL, compartments=frozenset([Compartment.VIGILANCE, Compartment.HSE]))

    inherited = inherit_label([lbl1, lbl2, lbl3])
    # Highest tier is SECRET
    assert inherited.tier == Tier.SECRET
    # Union of compartments: {HSE, TECHNICAL, VIGILANCE}
    assert inherited.compartments == frozenset([
        Compartment.HSE,
        Compartment.TECHNICAL,
        Compartment.VIGILANCE,
    ])
