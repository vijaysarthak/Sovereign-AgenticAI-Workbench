"""Agent Protocol and contract definition.

CRITICAL SECURITY ARCHITECTURE:
The Agent Protocol takes NO principal, NO grade, and NO compartments.
An agent NEVER learns who is asking — it only ever receives passages that
have already been filtered through the deterministic two-axis security gate.
That architectural absence is the fundamental security argument.
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable
from contracts import Draft, Passage


@runtime_checkable
class Agent(Protocol):
    """Protocol for drafting agents."""

    def draft(
        self,
        question: str,
        passages: Sequence[Passage],
        feedback: Optional[str] = None,
        recent_context: str = "",
    ) -> Draft:
        """Propose a synthesized draft answer and structured citations based solely on allowed passages.

        `recent_context`, if given, is a short summary of the last 1-2 prior
        turns for THIS SAME person -- for interpreting casual follow-up
        phrasing only. It is never a citable source: every citation must
        still be a verbatim substring of `passages`, exactly as before.
        """
        ...
