"""Deterministic canned agent for air-gapped testing and deterministic verification loops.

Requires no external LLM dependencies, runs offline instantly, and generates
verifiably exact substrings from provided passages.
Supports fail_first=True to test the retry loop deterministically.
"""

from __future__ import annotations

from typing import Optional, Sequence
from contracts import Citation, Draft, Passage


class MockAgent:
    """Mock implementation of the Agent protocol."""

    def __init__(
        self,
        fail_first: bool = False,
        fail_always: bool = False,
        custom_answer: Optional[str] = None,
    ):
        self.fail_first = fail_first
        self.fail_always = fail_always
        self.custom_answer = custom_answer
        self.calls = 0
        self.last_model_used = "mock-agent"

    def draft(
        self,
        question: str,
        passages: Sequence[Passage],
        feedback: Optional[str] = None,
        recent_context: str = "",
    ) -> Draft:
        """Generate a draft answer quoting real substrings of the provided passages."""
        self.calls += 1

        if not passages:
            return Draft(
                answer="No relevant readable documents are available to answer your question.",
                citations=[],
            )

        target_passage = passages[0]

        # Deterministic simulation of failure on attempt 1 (for testing retry harness)
        if (self.fail_first and self.calls == 1) or self.fail_always:
            return Draft(
                answer="Draft with deliberately fabricated citation for retry testing.",
                citations=[
                    Citation(
                        doc_id=target_passage.doc_id,
                        page=target_passage.page,
                        quote="This is a completely fabricated quote that does not appear in text",
                    )
                ],
            )

        # Extract an exact verbatim substring from the passage text
        # Must be >= 20 characters and >= 5 words
        text = target_passage.text.strip()
        if len(text) < 25 or len(text.split()) < 5:
            quote = text if len(text) >= 20 and len(text.split()) >= 5 else "The refinery operation adheres to all standard regulatory requirements."
        elif len(text) <= 250:
            quote = text
        else:
            end_idx = min(250, len(text))
            space_idx = text.rfind(" ", 25, end_idx)
            quote = text[:space_idx].strip() if space_idx != -1 else text[:end_idx].strip()

        ans = self.custom_answer or f"According to {target_passage.doc_id} (page {target_passage.page}), {quote}"
        return Draft(
            answer=ans,
            citations=[
                Citation(
                    doc_id=target_passage.doc_id,
                    page=target_passage.page,
                    quote=quote,
                )
            ],
        )
