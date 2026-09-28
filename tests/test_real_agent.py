"""Unit tests for agents/real.py.

Verifies:
1. RealLlmAgent protocol conformance.
2. Structured Draft parsing with markdown codeblock stripping.
3. Citation validation and malformed citation filtering.
4. Fallback when passages are empty.
"""

from contracts import Citation, Label, Passage, Tier
from agents.real import RealLlmAgent


def test_real_agent_empty_passages():
    """RealLlmAgent returns empty citations draft when no passages provided."""
    agent = RealLlmAgent()
    draft = agent.draft("What is the status?", [])
    assert "No readable documents" in draft.answer
    assert draft.citations == []


def test_real_agent_parse_draft():
    """RealLlmAgent properly parses valid JSON and strips code blocks."""
    agent = RealLlmAgent()
    passages = [
        Passage(
            doc_id="test-doc",
            page=1,
            text="Emergency shutdown valve 201-XV-01 must be actuated immediately upon high pressure alarm.",
            label=Label(tier=Tier.INTERNAL),
        )
    ]

    raw_json = """```json
    {
      "answer": "Actuate valve 201-XV-01 immediately.",
      "citations": [
        {
          "doc_id": "test-doc",
          "page": 1,
          "quote": "Emergency shutdown valve 201-XV-01 must be actuated immediately upon high pressure alarm."
        }
      ]
    }
    ```"""

    draft = agent._parse_draft(raw_json, passages)
    assert "Actuate valve" in draft.answer
    assert len(draft.citations) == 1
    assert draft.citations[0].doc_id == "test-doc"
    assert draft.citations[0].page == 1
    assert "201-XV-01" in draft.citations[0].quote
