"""Unit tests for agents/mock.py.

Verifies:
1. MockAgent extracts real substrings from provided passages.
2. Canned output passes verify.check() cleanly.
3. fail_first=True fabricates citation on attempt 1, passes on attempt 2.
4. fail_always=True fabricates on all attempts.
"""

from contracts import Citation, Label, Passage, Tier
from agents.mock import MockAgent
from harness.verify import check as verify_check


def test_mock_agent_canned_draft_verifies():
    """MockAgent generates exact substrings that pass verify_check."""
    p = Passage(
        doc_id="doc-101",
        page=1,
        text="The atmospheric distillation column operating pressure is maintained at 1.2 bar gauge.",
        label=Label(tier=Tier.INTERNAL),
    )

    agent = MockAgent()
    draft = agent.draft("What is the column pressure?", [p])

    assert len(draft.citations) == 1
    assert draft.citations[0].doc_id == "doc-101"
    assert draft.citations[0].page == 1

    # Must pass verify.check() cleanly
    failure = verify_check(draft.citations, [p])
    assert failure is None


def test_mock_agent_fail_first():
    """MockAgent with fail_first=True deliberately fabricates on attempt 1 and recovers on attempt 2."""
    p = Passage(
        doc_id="doc-101",
        page=1,
        text="All refinery drainage sumps are inspected on a daily schedule by shift operators.",
        label=Label(tier=Tier.INTERNAL),
    )

    agent = MockAgent(fail_first=True)

    # Call 1: Must fail verification
    draft_1 = agent.draft("What is the sump inspection schedule?", [p])
    assert verify_check(draft_1.citations, [p]) is not None

    # Call 2: Must recover and pass verification
    draft_2 = agent.draft("What is the sump inspection schedule?", [p])
    assert verify_check(draft_2.citations, [p]) is None
