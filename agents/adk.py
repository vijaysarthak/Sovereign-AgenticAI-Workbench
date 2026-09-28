"""Google ADK LlmAgent adapter and sovereign document security tools.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. Five tools total:
   - search_corpus, get_passage, verify_quote, list_readable_documents --
     the original four, used together only on the document Q&A path
     (AdkAgent.draft), which is clearance-gated corpus content.
   - execute_code -- used standalone on the code-request path
     (AdkAgent.draft_code), which carries no corpus passages and no
     clearance gate at all (see harness/code_runner.py). It is never
     combined with the document tools in the same agent run, so a
     document-answering call can never also execute arbitrary code.
2. NO tool takes a grade, tier, or compartment as a parameter.
   Each reads the principal from execution context and evaluates can_read() internally.
   The model has zero vocabulary for clearance, preventing prompt injection bypasses.
3. Two critical subtleties:
   - search_corpus returns withheld_count and withheld doc TITLES, never content.
   - verify_quote MUST gate BEFORE matching. If it checked the quote first,
     a model could guess sentences and use found-true/false as a side-channel
     to extract restricted content.
4. Tool docstrings are the API sent to the model — real descriptions with Args blocks.
5. All ADK-specific code lives inside this adapter, satisfying the Agent Protocol.
   Lazy import allows SEVERANCE to run offline anywhere without google-adk installed.
"""

from __future__ import annotations

import contextvars
from pathlib import Path
from typing import Any, Optional, Sequence
from contracts import Citation, CodeAnswer, Draft, Label, Passage, Principal
from agents.sandbox import run_python
from harness.retrieve import score_passage, tokenize
from trust.labels import can_read

# Context variable holding the active authenticated principal during tool execution
_CURRENT_PRINCIPAL: contextvars.ContextVar[Optional[Principal]] = contextvars.ContextVar(
    "current_principal", default=None
)

# Context variable holding the active corpus passages during tool execution
_ACTIVE_PASSAGES: contextvars.ContextVar[Sequence[Passage]] = contextvars.ContextVar(
    "active_passages", default=()
)


def get_current_principal() -> Principal:
    """Retrieve principal from execution context. Fails closed if missing."""
    p = _CURRENT_PRINCIPAL.get()
    if p is None:
        raise PermissionError("Security context missing: No active principal set.")
    return p


# ---------------------------------------------------------------------------
# The Four Gated Tools Handed to the Model
# ---------------------------------------------------------------------------

def search_corpus(query: str, top_k: int = 5) -> dict[str, Any]:
    """Search for relevant documents in the MRPL corpus matching a query.

    Evaluates two-axis security clearance internally. If restricted materials
    match the query, their titles are noted but their contents are completely
    excluded from the returned results.

    Args:
        query: Natural language search string or technical keywords.
        top_k: Maximum number of readable passages to return (default 5).

    Returns:
        dict containing:
          - 'readable_passages': list of readable passage objects with doc_id, page, title, and text.
          - 'withheld_count': number of relevant documents withheld due to clearance restrictions.
          - 'withheld_titles': list of withheld document titles (without content).
    """
    principal = get_current_principal()
    corpus = _ACTIVE_PASSAGES.get()

    query_tokens = tokenize(query)
    scored = []
    for p in corpus:
        p_tokens = tokenize(p.text) + tokenize(p.title)
        score = score_passage(query_tokens, p_tokens)
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)

    readable: list[dict[str, Any]] = []
    withheld_titles: set[str] = set()

    for _, p in scored:
        if can_read(principal, p.label):
            if len(readable) < top_k:
                readable.append({
                    "doc_id": p.doc_id,
                    "page": p.page,
                    "title": p.title,
                    "text": p.text,
                })
        else:
            # Note title only, text is physically excluded
            withheld_titles.add(p.title or p.doc_id)

    return {
        "readable_passages": readable,
        "withheld_count": len(withheld_titles),
        "withheld_titles": sorted(list(withheld_titles)),
    }


def get_passage(doc_id: str, page: int) -> dict[str, Any]:
    """Retrieve the full text of a specific document page from the corpus.

    Access is gated by two-axis security rules before retrieval.

    Args:
        doc_id: Unique identifier of the document (e.g. 'mrpl-hse-sop-101').
        page: 1-based page number within the document.

    Returns:
        dict containing:
          - 'found': boolean indicating if page exists and is accessible.
          - 'text': text content if accessible, None if withheld.
          - 'reason': explanation if access is denied.
    """
    principal = get_current_principal()
    corpus = _ACTIVE_PASSAGES.get()

    for p in corpus:
        if p.doc_id == doc_id and p.page == page:
            # Evaluates two-axis security gate
            if can_read(principal, p.label):
                return {
                    "found": True,
                    "doc_id": doc_id,
                    "page": page,
                    "title": p.title,
                    "text": p.text,
                }
            else:
                return {
                    "found": False,
                    "doc_id": doc_id,
                    "page": page,
                    "reason": "Access denied: Two-axis clearance required for this document is not held.",
                    "text": None,
                }

    return {
        "found": False,
        "doc_id": doc_id,
        "page": page,
        "reason": f"Document '{doc_id}' page {page} not found in corpus.",
        "text": None,
    }


def verify_quote(doc_id: str, page: int, quote: str) -> dict[str, Any]:
    """Pre-verify that a proposed citation quote appears verbatim in a document page.

    CRITICAL SECURITY INVARIANT:
    This tool gates access BEFORE checking whether the quote matches text.
    Checking the quote first would allow unauthorized actors to guess secret
    strings and use the verification boolean as an exfiltration oracle.

    Args:
        doc_id: Unique identifier of the document.
        page: 1-based page number.
        quote: Proposed verbatim excerpt to verify (minimum 20 characters, minimum 5 words).

    Returns:
        dict containing:
          - 'verified': boolean true if quote exists verbatim in authorized passage.
          - 'reason': detailed failure reason if verification fails.
    """
    principal = get_current_principal()
    corpus = _ACTIVE_PASSAGES.get()

    # Step 1: Locate passage and evaluate clearance FIRST
    target_passage = None
    for p in corpus:
        if p.doc_id == doc_id and p.page == page:
            target_passage = p
            break

    if target_passage is None:
        return {
            "verified": False,
            "reason": f"Passage '{doc_id}' page {page} does not exist in corpus.",
        }

    # TWO-AXIS GATE EVALUATION OCCURS BEFORE SUBSTRING MATCHING
    if not can_read(principal, target_passage.label):
        return {
            "verified": False,
            "reason": "Security Gate Violation: You do not hold clearance to verify quotes against this document.",
        }

    # Step 2: Validate quote structural requirements
    cleaned_quote = quote.strip()
    if len(cleaned_quote) < 20:
        return {
            "verified": False,
            "reason": f"Quote too short ({len(cleaned_quote)} characters; minimum 20 characters required).",
        }

    words = cleaned_quote.split()
    if len(words) < 5:
        return {
            "verified": False,
            "reason": f"Quote contains only {len(words)} words; minimum 5 substantive words required.",
        }

    # Step 3: Exact verbatim match against authorized text
    cleaned_quote = quote.strip()
    norm_quote = " ".join(cleaned_quote.split())
    norm_text = " ".join(target_passage.text.split())
    if cleaned_quote in target_passage.text or norm_quote in norm_text:
        return {
            "verified": True,
            "doc_id": doc_id,
            "page": page,
            "reason": "Exact verbatim substring confirmed.",
        }
    else:
        return {
            "verified": False,
            "reason": f"Quote '{cleaned_quote[:40]}...' was not found verbatim in page text.",
        }


def list_readable_documents() -> list[dict[str, str]]:
    """List all documents in the MRPL corpus that the current user has clearance to read.

    Does not disclose titles of restricted or secret documents for which
    the caller lacks clearance.

    Returns:
        list of dicts with 'doc_id' and 'title'.
    """
    principal = get_current_principal()
    corpus = _ACTIVE_PASSAGES.get()

    seen_docs: dict[str, str] = {}
    for p in corpus:
        if p.doc_id not in seen_docs:
            if can_read(principal, p.label):
                seen_docs[p.doc_id] = p.title or p.doc_id

    return [{"doc_id": doc_id, "title": title} for doc_id, title in seen_docs.items()]


def execute_code(code: str) -> dict[str, Any]:
    """Execute a self-contained Python script in an isolated sandbox and
    report the REAL outcome. This tool takes no principal/clearance
    parameter and is never combined with the document tools above -- it is
    only ever offered to the model on the separate code-request path
    (AdkAgent.draft_code), which carries no corpus content to protect.

    Args:
        code: Complete, self-contained Python 3 source code to execute.
              Standard library only; no network access; no input().

    Returns:
        dict containing 'stdout', 'stderr', 'exit_code', and 'timed_out',
        taken directly from the actual subprocess run -- never inferred.
    """
    result = run_python(code)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_seconds": result.duration_seconds,
    }


# ---------------------------------------------------------------------------
# AdkAgent Implementation Adapter
# ---------------------------------------------------------------------------

class AdkAgent:
    """Google ADK LlmAgent adapter satisfying the Agent Protocol."""

    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.model_name = model_name

    def draft(
        self,
        question: str,
        passages: Sequence[Passage],
        feedback: Optional[str] = None,
    ) -> Draft:
        """Execute a single agentic drafting step using Google ADK."""
        try:
            # Lazy import inside method so system runs anywhere without google-adk installed
            from google.adk.agents import LlmAgent  # type: ignore
        except ImportError:
            raise ImportError(
                "google-adk package is not installed. To use the ADK backend, install "
                "google-adk or switch to AGENT_BACKEND=mock in your .env file."
            )

        # Set execution context for tools
        token_passages = _ACTIVE_PASSAGES.set(passages)

        try:
            tools = [
                search_corpus,
                get_passage,
                verify_quote,
                list_readable_documents,
            ]

            system_instruction = (
                "You are SEVERANCE, the sovereign document intelligence agent for MRPL.\n"
                "CRITICAL RULES:\n"
                "1. Answer the question using ONLY the provided readable passages.\n"
                "2. Every citation MUST be an exact verbatim quote copied from a passage.\n"
                "3. You MUST call `verify_quote` before committing any citation.\n"
                "4. If feedback from a previous failed verification is provided, strictly resolve the error.\n"
                "5. Citations must contain at least 20 characters and at least 5 words."
            )

            prompt = f"User Inquiry: {question}\n\n"
            if feedback:
                prompt += f"PREVIOUS ATTEMPT FEEDBACK:\n{feedback}\n\n"

            prompt += "Available Readable Passages:\n"
            for p in passages:
                prompt += f"\n--- Document: {p.doc_id} | Page: {p.page} ---\n{p.text}\n"

            agent = LlmAgent(
                model=self.model_name,
                system_instruction=system_instruction,
                tools=tools,
                output_schema=Draft,
            )

            result = agent.run(prompt)
            if isinstance(result, Draft):
                return result

            # Parse or extract Draft if returned as string/dict
            if isinstance(result, dict):
                return Draft.model_validate(result)
            return Draft(answer=str(result), citations=[])
        finally:
            _ACTIVE_PASSAGES.reset(token_passages)

    def draft_code(self, question: str, feedback: Optional[str] = None) -> CodeAnswer:
        """Agentic coding step: the model may call execute_code itself to
        try candidate code before returning, but harness/code_runner.py
        still independently re-runs the FINAL returned code through
        agents/sandbox.py and is the sole authority on whether it succeeded
        -- an agent claiming "I tested it and it works" is never taken on
        faith, exactly like a claimed citation is never taken on faith.
        """
        try:
            from google.adk.agents import LlmAgent  # type: ignore
        except ImportError:
            raise ImportError(
                "google-adk package is not installed. To use the ADK backend, install "
                "google-adk or switch to AGENT_BACKEND=mock in your .env file."
            )

        system_instruction = (
            "You write short, self-contained Python 3 scripts (standard library only, no "
            "network access, no input()) that solve the user's request. You may call "
            "execute_code to test a candidate script before finalizing your answer. Respond "
            "with a final 'code' (the complete script) and 'explanation' (one or two sentences)."
        )
        prompt = f"Request: {question}\n"
        if feedback:
            prompt += f"\nPREVIOUS ATTEMPT FAILED WHEN RUN:\n{feedback}\nFix the script.\n"

        agent = LlmAgent(
            model=self.model_name,
            system_instruction=system_instruction,
            tools=[execute_code],
            output_schema=CodeAnswer,
        )
        result = agent.run(prompt)
        if isinstance(result, CodeAnswer):
            return result
        if isinstance(result, dict):
            return CodeAnswer.model_validate(result)
        return CodeAnswer(code=str(result), explanation="")
