"""Unit tests for harness/runner.py.

Verifies:
1. Immediate abstention when no readable passages matched (Agent NEVER called).
2. The retry loop: fail_first=True retries with feedback and succeeds on attempt 2.
3. Cap exceeded: fail_always=True exhausts retries and abstains (Never returns unverified answer).
4. Classification inheritance covers ALL prompt passages.
5. Every query writes a ledger record.
"""

from pathlib import Path
from contracts import (
    AskRequest,
    Compartment,
    Label,
    Passage,
    Principal,
    Tier,
)
from agents.mock import MockAgent
from harness.runner import run_query
from trust.ledger import read as ledger_read


def test_immediate_abstention_never_calls_agent(tmp_path: Path):
    """If nothing readable matched, the agent is NOT called at all."""
    db_path = str(tmp_path / "runner_abstain.db")

    user = Principal(
        person_id="worker-01",
        name="Worker",
        job_title="Support",
        grade="S1",  # Rank 1
        compartments=frozenset(),
    )

    # Secret passage about catalyst procurement
    p_secret = Passage(
        doc_id="cat-sec-01",
        page=1,
        title="Catalyst Secret Formulation",
        text="The exact platinum catalyst formulation and supplier contract terms.",
        label=Label(tier=Tier.SECRET, compartments=frozenset([Compartment.COMMERCIAL])),
    )

    agent = MockAgent()
    req = AskRequest(question="What is the catalyst formulation?", top_k=2)

    response = run_query(
        request=req,
        corpus=[p_secret],
        principal=user,
        agent=agent,
        db_path=db_path,
    )

    # 1. Agent was NEVER called
    assert agent.calls == 0

    # 2. Status is abstained
    assert response.status == "abstained"
    assert "cat-sec-01" in response.answer
    assert len(response.denials) == 1
    assert response.denials[0].doc_id == "cat-sec-01"

    # 3. Ledger entry written
    entries = ledger_read(db_path, limit=2)
    assert len(entries) == 1
    assert entries[0].action == "ASK_ABSTAINED"


def test_retry_loop_recovers_with_mock_agent(tmp_path: Path):
    """If attempt 1 fails citation verification, retry loop provides feedback and succeeds on attempt 2."""
    db_path = str(tmp_path / "runner_retry.db")

    user = Principal(
        person_id="eng-01",
        name="Engineer",
        job_title="Process",
        grade="A",
        compartments=frozenset([Compartment.HSE]),
    )

    p1 = Passage(
        doc_id="hse-sop-42",
        page=3,
        text="Hydrogen sulfide detectors must be calibrated every thirty days using standard calibration gas.",
        label=Label(tier=Tier.INTERNAL, compartments=frozenset([Compartment.HSE])),
    )

    # MockAgent with fail_first=True deliberately fabricates quote on attempt 1
    agent = MockAgent(fail_first=True)
    req = AskRequest(question="What is the calibration interval for H2S detectors?", top_k=1)

    response = run_query(
        request=req,
        corpus=[p1],
        principal=user,
        agent=agent,
        db_path=db_path,
        max_retries=3,
    )

    # Must have taken exactly 2 attempts
    assert agent.calls == 2
    assert response.status == "answered"
    assert len(response.citations) == 1
    assert "calibration gas" in response.citations[0].quote


def test_exhausted_retries_abstains(tmp_path: Path):
    """If an agent fails citations on every attempt, the runner abstains and never returns unverified text."""
    db_path = str(tmp_path / "runner_fail_always.db")

    user = Principal(
        person_id="eng-01",
        name="Engineer",
        job_title="Process",
        grade="A",
        compartments=frozenset(),
    )

    p1 = Passage(
        doc_id="doc-99",
        page=1,
        text="Daily water injection rates in the desalting unit are recorded at 50 cubic meters per hour.",
        label=Label(tier=Tier.INTERNAL),
    )

    agent = MockAgent(fail_always=True)
    req = AskRequest(question="What is the water injection rate?", top_k=1)

    response = run_query(
        request=req,
        corpus=[p1],
        principal=user,
        agent=agent,
        db_path=db_path,
        max_retries=3,
    )

    assert agent.calls == 3
    assert response.status == "abstained"
    assert "Verification failed" in response.answer or "Response withheld" in response.answer
    assert len(response.citations) == 0


def test_classification_inheritance_covers_all_prompt_passages(tmp_path: Path):
    """An answer inherits highest tier and union of ALL passages placed in the prompt."""
    db_path = str(tmp_path / "runner_inherit.db")

    user = Principal(
        person_id="exec-01",
        name="Executive",
        job_title="Senior Manager",
        grade="C",  # Rank 9 >= Confidential
        compartments=frozenset([Compartment.HSE, Compartment.TECHNICAL]),
    )

    # Passage 1: Internal, HSE
    p1 = Passage(
        doc_id="hse-doc",
        page=1,
        text="All site workers must wear certified safety boots and flame-retardant coveralls at all times.",
        label=Label(tier=Tier.INTERNAL, compartments=frozenset([Compartment.HSE])),
    )

    # Passage 2: Confidential, Technical (not cited directly by MockAgent, but placed in prompt)
    p2 = Passage(
        doc_id="tech-doc",
        page=2,
        text="Crude distillation unit preflash tower overhead condenser operating temperature curves.",
        label=Label(tier=Tier.CONFIDENTIAL, compartments=frozenset([Compartment.TECHNICAL])),
    )

    agent = MockAgent()
    req = AskRequest(question="What safety gear is required for distillation unit operations?", top_k=2)

    response = run_query(
        request=req,
        corpus=[p1, p2],
        principal=user,
        agent=agent,
        db_path=db_path,
    )

    assert response.status == "answered"
    # Highest tier is CONFIDENTIAL
    assert response.effective_label.tier == Tier.CONFIDENTIAL
    # Union of compartments: {HSE, TECHNICAL}
    assert response.effective_label.compartments == frozenset([Compartment.HSE, Compartment.TECHNICAL])
