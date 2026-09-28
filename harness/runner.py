"""Bounded verification loop and execution harness.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. The retry loop is a plain Python for loop whose exit condition is
   deterministic verification.
2. Abstention: If nothing readable matched, DO NOT CALL THE MODEL AT ALL.
   A model with no sources writes fluent hallucinations.
3. Citation verification is pure Python string matching:
   - Check structured output schema.
   - Exact verbatim substring in claimed doc_id and page.
   - If verification fails, retry with the specific failure fed back into the prompt.
4. After hard cap (max_retries), ABSTAIN. Never return an unverified answer.
5. Classification inheritance: An answer inherits the highest tier and union of
   all compartments of EVERY passage placed into the prompt (not just cited ones).
6. Every query outcome (answered or abstained) writes to the hash-chained ledger.
"""

from __future__ import annotations

import os
from typing import Callable, Optional, Sequence
from contracts import (
    AskRequest,
    AskResponse,
    Citation,
    Denial,
    Label,
    Passage,
    Principal,
    Tier,
)
from agents.base import Agent
from harness.code_runner import run_code_query
from harness.retrieve import retrieve
from harness.verify import check as verify_check
from ingest.ephemeral import EphemeralUpload
from trust.conversations import append_turn, conversation_owner, create_conversation, get_recent_context
from trust.labels import can_read, inherit_label
from trust.ledger import log as ledger_log
from trust.reports import save_report_data

DEFAULT_MAX_RETRIES = 3

# Without this, a small model told only "citation N failed" tends to re-guess
# a different wording of the same shaky quote on every retry. Dropping it is
# always an acceptable fix, since verification still applies in full to
# whatever citations remain.
_CITATION_RETRY_HINT = (
    "If you cannot reproduce a quote character-for-character from the exact page header it appeared "
    "under, REMOVE that citation instead of guessing again -- keep only the 1-2 quotes you are certain "
    "are exact, and limit the answer to what those quotes support."
)


def _build_capability_facts(corpus: Sequence[Passage], principal: Principal) -> tuple[str, list[str], list[str]]:
    """Ground-truth facts about this assistant's real behavior and the
    caller's real document access -- the ONLY material either the templated
    fallback or the LLM polish step (draft_capability_answer) may draw on.

    Meta-questions about the assistant itself (e.g. "what can you do", "how
    did you answer that so fast") have no grounding passage anywhere -- no
    document describes the assistant's own capabilities -- so these facts
    come from real corpus/clearance data and real pipeline behavior, never
    from the drafting model guessing.
    """
    seen: dict[str, Passage] = {}
    for p in corpus:
        seen.setdefault(p.doc_id, p)

    readable: list[str] = []
    locked: list[str] = []
    for doc_id, p in seen.items():
        title = p.title or doc_id
        tier = p.label.tier.value
        if can_read(principal, p.label):
            readable.append(f"- **{title}** (`{doc_id}`, {tier})")
        else:
            locked.append(f"- {title} (`{doc_id}`, {tier} — requires additional clearance)")

    facts_lines = [
        "- This assistant answers questions about MRPL's internal documents only, and every "
        "content claim it makes must cite a verbatim passage from a document the caller is "
        "cleared to read.",
        "- It cannot hold a general conversation, perform tasks outside the document corpus, or "
        "answer from memory without a citation.",
        "- Every incoming message is first classified as one of: a real document question, a "
        "meta-question about the assistant/system itself, or small talk/filler with no "
        "information need.",
        "- Meta-questions about the assistant (like this one) skip document retrieval and the "
        "citation-verification loop entirely -- that's the ENTIRE reason they return faster than "
        "a real document question, which must search the corpus, draft an answer, and verify "
        "every citation before responding.",
        f"- Readable documents for this caller ({len(readable)}):",
    ]
    facts_lines.extend(f"  {line}" for line in (readable or ["  (none)"]))
    if locked:
        facts_lines.append(f"- Documents that exist but this caller cannot read ({len(locked)}):")
        facts_lines.extend(f"  {line}" for line in locked)

    return "\n".join(facts_lines), readable, locked


def _build_capability_fallback_answer(readable: list[str], locked: list[str]) -> str:
    """Plain templated capability answer, used when the LLM polish step
    (draft_capability_answer) is unavailable or fails."""
    lines = [
        "## What I Can Do",
        "I answer questions about MRPL's internal documents, grounding every claim in a "
        "verbatim, machine-verified citation from a passage you're cleared to read. I don't "
        "hold a conversation, perform tasks outside the document corpus, or answer from memory "
        "without a citation.",
        "",
        "## Documents You Can Currently Read",
    ]
    if readable:
        lines.extend(readable)
    else:
        lines.append("None of the documents in the corpus are currently readable under your active clearance.")

    if locked:
        lines.append("")
        lines.append("## Documents That Exist But You Cannot Read")
        lines.extend(locked)

    lines.append("")
    lines.append(
        "Ask me something specific about one of the readable documents above, or about safety "
        "procedures, RTI disclosures, or compliance records."
    )
    return "\n".join(lines)


def run_query(
    request: AskRequest,
    corpus: Sequence[Passage],
    principal: Principal,
    agent: Agent,
    db_path: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    emit: Optional[Callable[[dict], None]] = None,
) -> AskResponse:
    """Execute the complete SEVERANCE query lifecycle.

    1. Retrieve and two-axis gate candidates (discarding denied text).
    2. Check for immediate abstention (if 0 readable passages, model is NOT called).
    3. Execute bounded drafting and citation verification loop.
    4. Compute classification inheritance over all prompt passages.
    5. Append tamper-evident audit record to SQLite ledger.

    `emit`, if given, is called with a small dict at each REAL stage boundary
    (not a simulated/timed guess) -- e.g. {"stage": "drafting", "status":
    "start", "attempt": 2}. This is what api/routes/ask.py's streaming
    endpoint uses to give the UI a live log that reflects actual backend
    progress instead of a client-side animation. Optional and side-effect-only:
    omitting it (the default) changes nothing about this function's behavior,
    so every existing caller (including the test suite) is unaffected.
    """
    def _emit(event: dict) -> None:
        if emit is not None:
            emit(event)

    question = request.question.strip()

    # Resolve (or start) a persisted conversation for this query. A supplied
    # conversation_id that doesn't exist or isn't owned by this principal is
    # never reused -- silently starting a fresh one instead avoids leaking
    # whether some other user's conversation_id exists at all.
    conversation_id = request.conversation_id
    if conversation_id and conversation_owner(db_path, conversation_id) != principal.person_id:
        conversation_id = None
    if not conversation_id:
        conversation_id = create_conversation(db_path, principal.person_id, question)

    # Short conversation memory: only the last 1-2 turns of THIS conversation
    # (see trust/conversations.py), used purely to interpret casual follow-up
    # phrasing ("what can I do here THEN", referring to what was just
    # discussed). Never a source of facts or citations -- every citation
    # still has to verify against freshly retrieved passages exactly as
    # before. Kept deliberately short: more turns means more prompt text the
    # local model re-reads on every call, and this pipeline is already
    # latency-sensitive.
    recent_context = get_recent_context(db_path, conversation_id)

    # Step 0: Intent routing gate (optional -- only agents that implement it,
    # currently RealLlmAgent, get this check; MockAgent is unaffected).
    # Lexical retrieval scores term overlap, not intent: rambling or filler text
    # that happens to contain a real corpus keyword (e.g. "...this world is
    # full of gas leak") will legitimately match real passages and produce a
    # real, correctly-cited answer even though it wasn't a genuine question --
    # and a meta-question about the assistant itself ("what can you do",
    # "what files do you have access to") has no grounding passage anywhere,
    # so forcing it through RAG either abstains uselessly or invites invented
    # citations. This routes each of the three cases correctly BEFORE spending
    # a retrieval + drafting cycle on it.
    classify_intent = getattr(agent, "classify_intent", None)
    if classify_intent is not None:
        _emit({"stage": "intent", "status": "start"})
        try:
            category = classify_intent(question, recent_context)
        except Exception:
            category = "content"  # fail open
        _emit({
            "stage": "intent",
            "status": "done",
            "category": category,
            "model": getattr(agent, "last_intent_model", None),
            "fallback": getattr(agent, "last_intent_fallback", False),
        })

        if category == "other":
            answer = (
                "That doesn't read as a specific question. Please ask something concrete about "
                "MRPL's documents, safety procedures, or compliance records, and I'll search the "
                "corpus for a grounded, citation-backed answer."
            )
            effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
            ledger_entry = ledger_log(
                db_path=db_path,
                actor=principal.person_id,
                action="ASK_ABSTAINED",
                details={"question": question, "reason": "not_a_genuine_question"},
            )
            response = AskResponse(
                status="abstained",
                answer=answer,
                citations=[],
                denials=[],
                effective_label=effective_label,
                ledger_row_id=ledger_entry.row_id,
                conversation_id=conversation_id,
            )
            append_turn(db_path, conversation_id, question, response)
            return response

        if category == "code":
            # Model auto-selection: routed to a DIFFERENT local model and a
            # completely different execution path (harness/code_runner.py)
            # than a document question -- no retrieval, no two-axis gate, no
            # citation verification, since there is no corpus passage
            # involved. See code_runner.py's module docstring.
            return run_code_query(
                question=question,
                principal=principal,
                agent=agent,
                db_path=db_path,
                emit=emit,
                conversation_id=conversation_id,
            )

        if category == "capability":
            _emit({"stage": "capability", "status": "start"})
            facts, readable, locked = _build_capability_facts(corpus, principal)
            answer = None
            draft_capability = getattr(agent, "draft_capability_answer", None)
            if draft_capability is not None:
                try:
                    # NOT passed recent_context: tested and found unsafe -- the
                    # local model would restate/extend prior turns' document
                    # content here, and this path has NO citation verification
                    # (see agents/real.py's draft_capability_answer docstring).
                    answer = draft_capability(question, facts)
                except Exception:
                    answer = None
            if not answer:
                answer = _build_capability_fallback_answer(readable, locked)
            _emit({"stage": "capability", "status": "done", "model": getattr(agent, "last_model_used", None)})
            effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
            ledger_entry = ledger_log(
                db_path=db_path,
                actor=principal.person_id,
                action="ASK_ANSWERED",
                details={
                    "question": question,
                    "category": "capability",
                    "answer_preview": answer[:100],
                },
            )
            response = AskResponse(
                status="answered",
                answer=answer,
                citations=[],
                denials=[],
                effective_label=effective_label,
                ledger_row_id=ledger_entry.row_id,
                conversation_id=conversation_id,
                model_used=getattr(agent, "last_model_used", None),
            )
            save_report_data(
                db_path=db_path,
                ledger_row_id=ledger_entry.row_id,
                person_id=principal.person_id,
                question=question,
                response=response,
            )
            append_turn(db_path, conversation_id, question, response)
            return response

    # Step 1: Two-pass retrieval and gating
    retrieval_mode = os.getenv("SEVERANCE_RETRIEVAL_MODE", "lexical")
    _emit({"stage": "retrieval", "status": "start", "mode": retrieval_mode})
    allowed_passages, denials = retrieve(
        query=question,
        corpus=corpus,
        principal=principal,
        top_k=request.top_k,
        use_semantic=retrieval_mode == "semantic",
    )
    _emit({
        "stage": "retrieval",
        "status": "done",
        "passages_found": len(allowed_passages),
        "denials_found": len(denials),
    })

    # Step 2: Immediate Abstention Check
    if not allowed_passages:
        if denials:
            withheld_docs = ", ".join(f"'{d.doc_id}'" for d in denials)
            answer = (
                f"Access denied: The requested information requires clearance for {withheld_docs}, "
                "which is withheld under the two-axis security gate. No readable passages matched your query."
            )
        else:
            answer = "No relevant documents found matching your query."

        effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
        ledger_entry = ledger_log(
            db_path=db_path,
            actor=principal.person_id,
            action="ASK_ABSTAINED",
            details={
                "question": question,
                "reason": "zero_readable_passages",
                "denials": [d.model_dump() for d in denials],
            },
        )
        response = AskResponse(
            status="abstained",
            answer=answer,
            citations=[],
            denials=denials,
            effective_label=effective_label,
            ledger_row_id=ledger_entry.row_id,
            conversation_id=conversation_id,
        )
        append_turn(db_path, conversation_id, question, response)
        return response

    # Step 3: Bounded Drafting & Verification Loop
    feedback: Optional[str] = None
    successful_draft = None

    for attempt in range(1, max_retries + 1):
        _emit({"stage": "drafting", "status": "start", "attempt": attempt, "max_attempts": max_retries})
        try:
            draft = agent.draft(
                question=question,
                passages=allowed_passages,
                feedback=feedback,
                recent_context=recent_context,
            )
        except Exception as exc:
            # Infrastructure failure (e.g. both LLM backends unreachable): treat
            # like a failed verification attempt so the loop can retry, and so
            # exhaustion falls through to a clean ABSTAIN instead of a raw 500.
            _emit({"stage": "drafting", "status": "error", "attempt": attempt, "message": str(exc)})
            feedback = f"Attempt {attempt} failed: drafting agent raised an error ({exc})."
            continue
        _emit({"stage": "drafting", "status": "done", "attempt": attempt, "citations_claimed": len(draft.citations), "model": getattr(agent, "last_model_used", None)})

        # Pure Python string verification
        _emit({"stage": "verification", "status": "start", "attempt": attempt})
        failure = verify_check(draft.citations, allowed_passages)
        if failure is None:
            # Verification passed completely
            _emit({"stage": "verification", "status": "pass", "attempt": attempt})
            successful_draft = draft
            break

        _emit({"stage": "verification", "status": "fail", "attempt": attempt, "reason": failure})
        # Feed the precise failure reason back into the next attempt
        avail_str = ", ".join(f"doc_id='{p.doc_id}' page {p.page}" for p in allowed_passages)
        feedback = (
            f"Attempt {attempt} verification failed: {failure}. Note: The ONLY readable passages in context are "
            f"[{avail_str}]. Ensure all quotes are exact verbatim substrings and page numbers match these exactly. "
            f"{_CITATION_RETRY_HINT}"
        )

    # Step 4: Outcome Resolution & Classification Inheritance
    if successful_draft is not None:
        # Verified Answer: inherit classification from ALL passages placed into prompt
        effective_label = inherit_label([p.label for p in allowed_passages])
        ledger_entry = ledger_log(
            db_path=db_path,
            actor=principal.person_id,
            action="ASK_ANSWERED",
            details={
                "question": question,
                "citations_count": len(successful_draft.citations),
                "denials_count": len(denials),
                "effective_tier": effective_label.tier.value,
                "effective_compartments": [c.value for c in effective_label.compartments],
                "answer_preview": successful_draft.answer[:100],
            },
        )
        response = AskResponse(
            status="answered",
            answer=successful_draft.answer,
            citations=successful_draft.citations,
            denials=denials,
            effective_label=effective_label,
            ledger_row_id=ledger_entry.row_id,
            conversation_id=conversation_id,
            model_used=getattr(agent, "last_model_used", None),
        )
        # Persist the FULL answer/citations/denials for report regeneration.
        # The ledger entry above only carries a truncated preview (it's readable
        # by every authenticated user as a transparency log); this store is only
        # ever read back through the ownership-checked /report/{id} endpoint.
        save_report_data(
            db_path=db_path,
            ledger_row_id=ledger_entry.row_id,
            person_id=principal.person_id,
            question=question,
            response=response,
        )
        append_turn(db_path, conversation_id, question, response)
        return response
    else:
        # Retries exhausted: ABSTAIN. Never return an unverified answer.
        answer = (
            f"Response withheld: The drafting model was unable to provide citations that could be "
            f"verbatim verified against source passages ({feedback})."
        )
        effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
        ledger_entry = ledger_log(
            db_path=db_path,
            actor=principal.person_id,
            action="ASK_ABSTAINED",
            details={
                "question": question,
                "reason": "verification_retries_exhausted",
                "final_feedback": feedback,
                "denials_count": len(denials),
            },
        )
        response = AskResponse(
            status="abstained",
            answer=answer,
            citations=[],
            denials=denials,
            effective_label=effective_label,
            ledger_row_id=ledger_entry.row_id,
            conversation_id=conversation_id,
            model_used=getattr(agent, "last_model_used", None),
        )
        append_turn(db_path, conversation_id, question, response)
        return response


def run_ephemeral_query(
    question: str,
    upload: EphemeralUpload,
    principal: Principal,
    agent: Agent,
    db_path: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    emit: Optional[Callable[[dict], None]] = None,
    conversation_id: Optional[str] = None,
) -> AskResponse:
    """Answer a question about an ephemeral, session-scoped user upload (an
    image, or a .pptx with mixed text/image content) -- NEVER governed corpus
    content, so NO two-axis clearance gate applies here. This is the user's
    own file, analyzed like a personal document assistant, not corpus data.

    Text content (if any) goes through the SAME drafting + citation
    verification loop as governed-corpus answers in run_query() above --
    every text claim must still be a verbatim substring of the uploaded text.
    Image content (if any) goes to the vision model and is reported in a
    CLEARLY SEPARATE section labeled as an AI description, not a verified
    citation -- there is no verbatim-substring check possible for an image
    the way there is for text, so it must never be presented with the same
    confidence as a citation-verified finding.
    """
    def _emit(event: dict) -> None:
        if emit is not None:
            emit(event)

    if conversation_id and conversation_owner(db_path, conversation_id) != principal.person_id:
        conversation_id = None
    if not conversation_id:
        conversation_id = create_conversation(db_path, principal.person_id, question)

    answer_sections: list[str] = []
    visual_sections: list[str] = []
    text_citations: list[Citation] = []

    # The upload was already split into text pages/slides and images when it was
    # received (ingest/ephemeral.py); report that as the extraction step.
    _emit({
        "stage": "extraction",
        "status": "done",
        "filename": upload.filename,
        "text_chunks": len(upload.text_chunks),
        "images": len(upload.images),
    })

    # --- Image channel: vision model, explicitly and visibly unverified ---
    # Runs BEFORE the text channel so live progress only moves forward (the text
    # channel ends in citation verification). Section order in the final answer
    # is unchanged: visual_sections are appended after the text findings below.
    analyze_image = getattr(agent, "analyze_image", None)
    if upload.images and analyze_image is not None:
        observations: list[str] = []
        for image in upload.images:
            _emit({"stage": "vision", "status": "start", "label": image.label})
            try:
                description = analyze_image(question, image.base64_data)
                _emit({"stage": "vision", "status": "done", "label": image.label,
                       "model": getattr(agent, "last_model_used", None)})
            except Exception as exc:
                description = f"(Vision analysis failed: {exc})"
                _emit({"stage": "vision", "status": "error", "label": image.label, "message": str(exc)})
            observations.append(f"**{image.label}:** {description}")

        visual_sections.append(
            "## Visual Observations (AI-Described — Not Verbatim-Verified)\n\n"
            "The following are the vision model's own descriptions of the image content. Unlike the text "
            "findings above, these cannot be checked against an exact source string and should be treated "
            "as an aid, not a verified fact.\n\n" + "\n\n".join(observations)
        )
    elif upload.images and analyze_image is None:
        visual_sections.append(
            "## Visual Observations\n\nThis upload contains images, but the active agent backend does not "
            "support image analysis."
        )

    # --- Text channel: identical citation-verification discipline as governed content ---
    if upload.text_chunks:
        passages = [
            Passage(
                doc_id=f"upload:{upload.filename}",
                page=idx + 1,
                title=chunk.label,
                text=chunk.text,
                label=Label(tier=Tier.PUBLIC, compartments=frozenset()),
            )
            for idx, chunk in enumerate(upload.text_chunks)
        ]

        feedback: Optional[str] = None
        successful_draft = None
        for attempt in range(1, max_retries + 1):
            _emit({"stage": "drafting", "status": "start", "attempt": attempt, "max_attempts": max_retries})
            try:
                draft = agent.draft(question=question, passages=passages, feedback=feedback)
            except Exception as exc:
                _emit({"stage": "drafting", "status": "error", "attempt": attempt, "message": str(exc)})
                feedback = f"Attempt {attempt} failed: drafting agent raised an error ({exc})."
                continue
            _emit({"stage": "drafting", "status": "done", "attempt": attempt, "citations_claimed": len(draft.citations), "model": getattr(agent, "last_model_used", None)})

            _emit({"stage": "verification", "status": "start", "attempt": attempt})
            failure = verify_check(draft.citations, passages)
            if failure is None:
                _emit({"stage": "verification", "status": "pass", "attempt": attempt})
                successful_draft = draft
                break
            _emit({"stage": "verification", "status": "fail", "attempt": attempt, "reason": failure})
            avail_str = ", ".join(f"doc_id='{p.doc_id}' page {p.page}" for p in passages)
            feedback = (
                f"Attempt {attempt} verification failed: {failure}. Note: The ONLY readable passages in "
                f"context are [{avail_str}]. Ensure all quotes are exact verbatim substrings and page "
                f"numbers match these exactly. {_CITATION_RETRY_HINT}"
            )

        if successful_draft is not None:
            answer_sections.append("## Document Text Findings (Verbatim Verified)\n\n" + successful_draft.answer)
            text_citations = successful_draft.citations
        else:
            answer_sections.append(
                "## Document Text Findings\n\nThe drafting model could not produce citations that verified "
                "verbatim against the uploaded text, so no text-based finding is reported."
            )

    answer_sections.extend(visual_sections)

    answer = "\n\n".join(answer_sections) if answer_sections else "The uploaded file contained no analyzable text or images."

    effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
    ledger_entry = ledger_log(
        db_path=db_path,
        actor=principal.person_id,
        action="ASK_ANSWERED",
        details={
            "question": question,
            "category": "ephemeral_upload",
            "filename": upload.filename,
            "text_chunks": len(upload.text_chunks),
            "images": len(upload.images),
            "answer_preview": answer[:100],
        },
    )
    response = AskResponse(
        status="answered",
        answer=answer,
        citations=text_citations,
        denials=[],
        effective_label=effective_label,
        ledger_row_id=ledger_entry.row_id,
        conversation_id=conversation_id,
        model_used=getattr(agent, "last_model_used", None),
    )
    save_report_data(
        db_path=db_path,
        ledger_row_id=ledger_entry.row_id,
        person_id=principal.person_id,
        question=question,
        response=response,
    )
    append_turn(db_path, conversation_id, question, response)
    return response
