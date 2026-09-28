"""Ask and report delivery endpoints.

ZERO ACCESS DECISIONS INSIDE.
Identity is derived strictly from the signed cookie.
Gating is performed by harness/runner.py calling trust/labels.py.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path
from typing import Literal, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from contracts import (
    AskRequest,
    AskResponse,
    Principal,
)
from agents.mock import MockAgent
from auth.deps import current_principal, get_db_path
from deliver.approval_note import build_approval_note_docx, get_approval_note_filename
from deliver.docx import build_report, get_report_filename
from deliver.pptx import build_report_pptx, get_report_pptx_filename
from deliver.xlsx import build_report_xlsx, get_report_xlsx_filename
from harness.approval_note import generate_approval_note
from harness.runner import run_ephemeral_query, run_query
from ingest.ephemeral import discard_upload, get_upload, parse_upload
from ingest.pdf import load_corpus
from trust.reports import get_report_data

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB

router = APIRouter(tags=["Document Workbench"])

MANIFEST_PATH = Path(__file__).parent.parent.parent / "corpus" / "manifest.json"
DOCS_DIR = Path(__file__).parent.parent.parent / "corpus" / "documents"

# Global cached corpus with dynamic mtime invalidation
_CORPUS_CACHE = None
_CORPUS_LAST_CHECK = 0.0


def get_corpus(force_reload: bool = False):
    """Load (and cache) the governed corpus. Reloads only when forced, when
    nothing is cached yet, or when a PDF under DOCS_DIR has changed -- NOT
    on every call, which the previous version of this function did by
    mistake (an unconditional load_corpus() call before the cache check
    even ran, making the cache below it dead code).
    """
    global _CORPUS_CACHE, _CORPUS_LAST_CHECK
    import time

    enable_ocr = os.getenv("SEVERANCE_ENABLE_OCR", "false").lower() == "true"

    current_mtime = 0.0
    if DOCS_DIR.exists():
        pdf_mtimes = [p.stat().st_mtime for p in DOCS_DIR.glob("*.pdf")]
        current_mtime = max(pdf_mtimes + [DOCS_DIR.stat().st_mtime, 0.0])

    if _CORPUS_CACHE is None or force_reload or current_mtime > _CORPUS_LAST_CHECK:
        _CORPUS_CACHE = load_corpus(MANIFEST_PATH, DOCS_DIR, enable_ocr=enable_ocr)
        _CORPUS_LAST_CHECK = max(current_mtime, time.time())
    return _CORPUS_CACHE


def get_agent():
    """Resolve drafting agent backend based on configuration."""
    backend = os.getenv("AGENT_BACKEND", "ollama").lower()
    if backend in ["ollama", "real"]:
        from agents.real import RealLlmAgent
        return RealLlmAgent()
    elif backend == "adk":
        try:
            from agents.adk import AdkAgent
            return AdkAgent()
        except ImportError:
            print("[WARN] Google ADK not installed; falling back to MockAgent.")
            return MockAgent()
    return MockAgent()


@router.post("/ask/upload")
async def upload_ephemeral_file(
    file: UploadFile = File(...),
    principal: Principal = Depends(current_principal),
):
    """Upload an ad-hoc file (image or .pptx) scoped to THIS conversation only.

    Never written to corpus/manifest.json, never assigned a compartment or
    tier, never subject to the two-axis clearance gate -- this is the
    caller's own content, held in memory for the life of the server process
    and scoped to their person_id (see ingest/ephemeral.py). Pass the
    returned upload_id in a subsequent /ask or /ask/stream call to analyze it.
    """
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({len(content)} bytes, max {MAX_UPLOAD_BYTES}).",
        )
    try:
        upload = parse_upload(filename=file.filename or "upload", content=content, person_id=principal.person_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return {
        "upload_id": upload.upload_id,
        "filename": upload.filename,
        "text_chunks": len(upload.text_chunks),
        "images": len(upload.images),
    }


@router.delete("/ask/upload/{upload_id}")
def remove_ephemeral_file(
    upload_id: str,
    principal: Principal = Depends(current_principal),
):
    """Explicitly discard an ephemeral upload (e.g. user removes the attachment)."""
    discard_upload(upload_id, principal.person_id)
    return {"status": "discarded", "upload_id": upload_id}


class ApprovalNoteRequest(BaseModel):
    """Request payload for POST /ask/approval-note."""
    upload_id: str = Field(description="ID of a previously uploaded report, from POST /ask/upload")
    conversation_id: Optional[str] = Field(default=None)


@router.post("/ask/approval-note", response_model=AskResponse)
def ask_approval_note(
    payload: ApprovalNoteRequest,
    principal: Principal = Depends(current_principal),
):
    """Named-example agentic task: read a scanned/uploaded inspection report
    and draft an approval note (see harness/approval_note.py). The returned
    AskResponse.approval_note field is populated; download it as a formatted
    Word document via GET /report/{ledger_row_id}/approval-note.
    """
    db_path = get_db_path()
    agent = get_agent()

    upload = get_upload(payload.upload_id, principal.person_id)
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found or expired. Please attach the file again.",
        )
    return generate_approval_note(
        upload=upload,
        principal=principal,
        agent=agent,
        db_path=db_path,
        conversation_id=payload.conversation_id,
    )


@router.post("/ask/approval-note/stream")
def ask_approval_note_stream(
    payload: ApprovalNoteRequest,
    principal: Principal = Depends(current_principal),
):
    """Same as POST /ask/approval-note, but streams real pipeline events
    (drafting, verification, vision analysis, synthesis) as newline-
    delimited JSON, exactly like POST /ask/stream."""
    db_path = get_db_path()
    agent = get_agent()

    upload = get_upload(payload.upload_id, principal.person_id)
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found or expired. Please attach the file again.",
        )

    event_queue: "queue.Queue" = queue.Queue()

    def emit(event: dict) -> None:
        event_queue.put(event)

    def worker() -> None:
        try:
            response = generate_approval_note(
                upload=upload,
                principal=principal,
                agent=agent,
                db_path=db_path,
                emit=emit,
                conversation_id=payload.conversation_id,
            )
            event_queue.put({"stage": "final", "response": json.loads(response.model_dump_json())})
        except Exception as exc:
            event_queue.put({"stage": "error", "message": str(exc)})
        finally:
            event_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = event_queue.get()
            if item is None:
                return
            yield json.dumps(item) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    principal: Principal = Depends(current_principal),
):
    """Primary workbench query endpoint.

    If payload.upload_id is set, the question is answered from that ephemeral
    upload's content instead of the governed corpus (see run_ephemeral_query).
    """
    db_path = get_db_path()
    agent = get_agent()

    if payload.upload_id:
        upload = get_upload(payload.upload_id, principal.person_id)
        if upload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload not found or expired. Please attach the file again.",
            )
        return run_ephemeral_query(
            question=payload.question.strip(),
            upload=upload,
            principal=principal,
            agent=agent,
            db_path=db_path,
            conversation_id=payload.conversation_id,
        )

    corpus = get_corpus()
    response = run_query(
        request=payload,
        corpus=corpus,
        principal=principal,
        agent=agent,
        db_path=db_path,
    )
    return response


@router.post("/ask/stream")
def ask_question_stream(
    payload: AskRequest,
    principal: Principal = Depends(current_principal),
):
    """Same query as POST /ask, but streams REAL backend pipeline events as
    newline-delimited JSON while they actually happen -- intent classification,
    retrieval, each drafting attempt, each citation verification pass/fail --
    instead of the client guessing at progress with a timed animation.

    run_query() is synchronous (it makes real blocking HTTP calls to the local
    Ollama server), so it runs on a background thread that pushes events
    into a queue as they occur; this generator just relays the queue to the
    client as it fills. The final line is always
    {"stage": "final", "response": <the same AskResponse POST /ask returns>}.
    """
    db_path = get_db_path()
    agent = get_agent()

    upload = None
    if payload.upload_id:
        upload = get_upload(payload.upload_id, principal.person_id)
        if upload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload not found or expired. Please attach the file again.",
            )

    event_queue: "queue.Queue" = queue.Queue()

    def emit(event: dict) -> None:
        event_queue.put(event)

    def worker() -> None:
        try:
            if upload is not None:
                response = run_ephemeral_query(
                    question=payload.question.strip(),
                    upload=upload,
                    principal=principal,
                    agent=agent,
                    db_path=db_path,
                    emit=emit,
                    conversation_id=payload.conversation_id,
                )
            else:
                response = run_query(
                    request=payload,
                    corpus=get_corpus(),
                    principal=principal,
                    agent=agent,
                    db_path=db_path,
                    emit=emit,
                )
            event_queue.put({"stage": "final", "response": json.loads(response.model_dump_json())})
        except Exception as exc:
            event_queue.put({"stage": "error", "message": str(exc)})
        finally:
            event_queue.put(None)  # sentinel: no more events

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = event_queue.get()
            if item is None:
                return
            yield json.dumps(item) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/report/{ledger_row_id}")
def download_report(
    ledger_row_id: int,
    format: Literal["docx", "pptx", "xlsx"] = "docx",
    principal: Principal = Depends(current_principal),
):
    """Download a deliverable report for an answered query with 3-way
    classification stamping, in the requested format (docx default, or
    pptx/xlsx -- see deliver/pptx.py and deliver/xlsx.py).

    Only the employee who asked the original question (or an administrator) may
    download it. The full answer/citations/denials come from trust/reports.py,
    NOT from the audit ledger — the ledger is readable by every authenticated
    user as a transparency log, so it only ever stores a truncated preview.
    """
    db_path = get_db_path()

    report = get_report_data(db_path, ledger_row_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report data found for this ledger row. It may predate report storage, or the query was not answered.",
        )

    if report["person_id"] != principal.person_id and not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only download reports for your own queries.",
        )

    ask_response = AskResponse.model_validate(report["response"])

    if format == "pptx":
        content_bytes = build_report_pptx(ask_response, question=report["question"])
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        filename = get_report_pptx_filename(ask_response)
    elif format == "xlsx":
        content_bytes = build_report_xlsx(ask_response, question=report["question"])
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = get_report_xlsx_filename(ask_response)
    else:
        content_bytes = build_report(ask_response, question=report["question"])
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = get_report_filename(ask_response)

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report/{ledger_row_id}/approval-note")
def download_approval_note(
    ledger_row_id: int,
    principal: Principal = Depends(current_principal),
):
    """Download the formal Word approval note for a query answered via
    POST /ask/approval-note (see deliver/approval_note.py). Separate from
    GET /report/{id} because the approval-note layout (title/summary/
    findings/recommendation/sign-off) is a different document shape than
    the generic Q&A synthesis report, not just a different format of the
    same content.
    """
    db_path = get_db_path()

    report = get_report_data(db_path, ledger_row_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report data found for this ledger row.")
    if report["person_id"] != principal.person_id and not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You may only download reports for your own queries.")

    ask_response = AskResponse.model_validate(report["response"])
    if ask_response.approval_note is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This ledger row is not an approval-note response. Use GET /report/{id} instead.",
        )

    docx_bytes = build_approval_note_docx(ask_response)
    filename = get_approval_note_filename(ask_response)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
