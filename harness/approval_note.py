"""Scanned inspection report -> approval note pipeline.

This is the PS's named example agentic task: "reading a scanned inspection
report, pulling out key findings, and drafting an approval note as a Word
file." It reuses the SAME provenance discipline as run_ephemeral_query in
harness/runner.py, split into two channels that are NEVER blended with
equal confidence:

1. Text-layer pages (ingest/ephemeral.py's per-page PDF split): findings
   here go through the identical drafting + harness/verify.py
   citation-verification loop as everything else in this system. A
   "verified finding" in the resulting ApprovalNote is a real Citation --
   an exact verbatim substring of the source page, machine-checked.
2. Scanned/no-text-layer pages: described by the vision model. These are
   NEVER citation-verified (there is no substring to check an image
   against) and are surfaced as `visual_observations`, kept visibly
   separate in both the ApprovalNote object and the rendered Word document
   (deliver/approval_note.py).

Like ephemeral uploads in general, this is the caller's OWN document, not
governed corpus content -- no two-axis clearance gate applies (see
ingest/ephemeral.py's module docstring for the same reasoning).
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional
from agents.base import Agent
from contracts import (
    ApprovalNote,
    AskResponse,
    Citation,
    Label,
    Passage,
    Tier,
)
from harness.verify import check as verify_check
from ingest.ephemeral import EphemeralUpload
from trust.conversations import append_turn, conversation_owner, create_conversation
from trust.ledger import log as ledger_log
from trust.reports import save_report_data

DEFAULT_MAX_RETRIES = 3


def _synthesize_note_fields(
    agent: Agent,
    findings_text: str,
    filename: str,
) -> tuple[str, str, str]:
    """Ask the drafting model to produce a title, summary, and recommendation
    from the (already-grounded) findings text. This is a polish/organization
    step, not a verification-critical one -- exactly like
    agents/real.py's draft_capability_answer, it only reorganizes facts that
    were already established (verified citations + labeled vision
    observations), it never introduces new factual claims of its own that
    would need separate verification. Falls back to a plain templated
    version on any failure so the pipeline never breaks on this step.
    """
    synthesize = getattr(agent, "_call_ollama", None)
    if synthesize is None:
        return (f"Approval Note: {filename}", findings_text[:300], "Refer to findings above for action.")

    system_prompt = (
        "You are drafting the header fields of a formal approval note for a refinery inspection "
        "report. Given the findings text below, produce a short title, a 2-4 sentence executive "
        "summary, and a one-paragraph recommendation for the approving authority. Use ONLY "
        "information present in the findings text -- do not invent facts, quantities, or "
        "locations not mentioned. Respond STRICTLY in valid JSON: "
        '{"title": "...", "summary": "...", "recommendation": "..."}'
    )
    user_prompt = f"Source file: {filename}\n\nFindings:\n{findings_text}\n\nRespond in JSON."
    try:
        raw = agent._call_ollama(system_prompt, user_prompt, temperature=0.1)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        parsed = json.loads(clean)
        return (
            str(parsed.get("title") or f"Approval Note: {filename}"),
            str(parsed.get("summary") or findings_text[:300]),
            str(parsed.get("recommendation") or "Refer to findings above for action."),
        )
    except Exception:
        return (f"Approval Note: {filename}", findings_text[:300], "Refer to findings above for action.")


def generate_approval_note(
    upload: EphemeralUpload,
    principal,
    agent: Agent,
    db_path: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    emit: Optional[Callable[[dict], None]] = None,
    conversation_id: Optional[str] = None,
) -> AskResponse:
    """Produce an AskResponse whose `approval_note` field is populated from
    the uploaded scanned/mixed report. `answer` still carries a plain-text
    rendering for the chat UI; the Word deliverable is built separately by
    deliver/approval_note.build_approval_note_docx from the same object.
    """
    def _emit(event: dict) -> None:
        if emit is not None:
            emit(event)

    question = f"Draft an approval note from the uploaded report '{upload.filename}'."

    if conversation_id and conversation_owner(db_path, conversation_id) != principal.person_id:
        conversation_id = None
    if not conversation_id:
        conversation_id = create_conversation(db_path, principal.person_id, question)

    verified_findings: list[Citation] = []
    findings_text_parts: list[str] = []

    _emit({
        "stage": "extraction",
        "status": "done",
        "filename": upload.filename,
        "text_chunks": len(upload.text_chunks),
        "images": len(upload.images),
    })

    # --- Channel 1: text-layer pages -> citation-verified findings extraction ---
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
        findings_question = (
            "Extract the key findings, defects, observations, and any recommended actions from "
            "this inspection report. List each finding as a separate point."
        )
        feedback: Optional[str] = None
        successful_draft = None
        for attempt in range(1, max_retries + 1):
            _emit({"stage": "approval_note_drafting", "status": "start", "attempt": attempt})
            try:
                draft = agent.draft(question=findings_question, passages=passages, feedback=feedback)
            except Exception as exc:
                _emit({"stage": "approval_note_drafting", "status": "error", "attempt": attempt, "message": str(exc)})
                feedback = f"Attempt {attempt} failed: drafting agent raised an error ({exc})."
                continue
            failure = verify_check(draft.citations, passages)
            if failure is None:
                _emit({"stage": "approval_note_drafting", "status": "pass", "attempt": attempt,
                       "model": getattr(agent, "last_model_used", None)})
                successful_draft = draft
                break
            _emit({"stage": "approval_note_drafting", "status": "fail", "attempt": attempt, "reason": failure,
                   "model": getattr(agent, "last_model_used", None)})
            feedback = (
                f"Attempt {attempt} verification failed: {failure}. If you cannot reproduce a quote "
                "character-for-character, REMOVE that citation instead of guessing again -- keep only "
                "quotes you are certain are exact."
            )

        if successful_draft is not None:
            findings_text_parts.append(successful_draft.answer)
            verified_findings = successful_draft.citations

    # --- Channel 2: scanned/no-text pages -> unverified vision observations ---
    visual_observations: list[str] = []
    analyze_image = getattr(agent, "analyze_image", None)
    if upload.images and analyze_image is not None:
        vision_question = (
            "This is a page from an inspection report with no machine-readable text. Describe "
            "any visible findings, defects, damage, gauge readings, or hazards shown."
        )
        for image in upload.images:
            _emit({"stage": "vision", "status": "start", "label": image.label})
            try:
                description = analyze_image(vision_question, image.base64_data)
                _emit({"stage": "vision", "status": "done", "label": image.label,
                       "model": getattr(agent, "last_model_used", None)})
            except Exception as exc:
                description = f"(Vision analysis failed: {exc})"
                _emit({"stage": "vision", "status": "error", "label": image.label, "message": str(exc)})
            visual_observations.append(f"{image.label}: {description}")
        findings_text_parts.append(
            "Unverified visual observations:\n" + "\n".join(visual_observations)
        )

    findings_text = "\n\n".join(findings_text_parts) or "No extractable findings were identified in this upload."

    _emit({"stage": "approval_note_synthesis", "status": "start"})
    title, summary, recommendation = _synthesize_note_fields(agent, findings_text, upload.filename)
    _emit({"stage": "approval_note_synthesis", "status": "done",
           "model": getattr(agent, "ollama_model", None) if hasattr(agent, "_call_ollama") else None})

    note = ApprovalNote(
        title=title,
        summary=summary,
        verified_findings=verified_findings,
        visual_observations=visual_observations,
        recommendation=recommendation,
        source_filename=upload.filename,
    )

    plain_answer_lines = [f"## {note.title}", "", note.summary, "", "### Findings"]
    for c in note.verified_findings:
        plain_answer_lines.append(f"- (verified, {c.doc_id} p.{c.page}) {c.quote}")
    for obs in note.visual_observations:
        plain_answer_lines.append(f"- (unverified, visual) {obs}")
    plain_answer_lines += ["", "### Recommendation", note.recommendation]
    answer = "\n".join(plain_answer_lines)

    effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
    ledger_entry = ledger_log(
        db_path=db_path,
        actor=principal.person_id,
        action="ASK_ANSWERED",
        details={
            "question": question,
            "category": "approval_note",
            "filename": upload.filename,
            "verified_findings": len(note.verified_findings),
            "visual_observations": len(note.visual_observations),
        },
    )
    response = AskResponse(
        status="answered",
        answer=answer,
        citations=note.verified_findings,
        denials=[],
        effective_label=effective_label,
        ledger_row_id=ledger_entry.row_id,
        conversation_id=conversation_id,
        approval_note=note,
        model_used=getattr(agent, "last_model_used", None),
    )
    save_report_data(db_path=db_path, ledger_row_id=ledger_entry.row_id,
                      person_id=principal.person_id, question=question, response=response)
    append_turn(db_path, conversation_id, question, response)
    return response
