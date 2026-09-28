"""Bounded code drafting + sandboxed execution loop.

This is the code-execution analogue of harness/runner.py's citation
verification loop, following the exact same discipline:

1. The model PROPOSES code (agents/real.py's draft_code). It never runs it
   and never gets to claim it works.
2. Deterministic Python (agents/sandbox.py) actually executes it in an
   isolated subprocess and reports the real stdout/stderr/exit_code.
3. If execution fails (non-zero exit, exception, or timeout), the exact
   failure is fed back into the next drafting attempt, exactly like a
   failed citation-verification reason is fed back in harness/runner.py.
4. After max_retries, ABSTAIN. Never return code as "successful" that did
   not actually exit 0 in the sandbox.
5. Every outcome (answered or abstained) writes to the same hash-chained
   ledger as every other query type.

NO document retrieval, NO two-axis clearance gate, and NO citation
verification happen on this path -- a coding request carries no corpus
passages to be gated or cited, by definition. This mirrors the same
reasoning harness/runner.py already documents for ephemeral uploads: this
is the caller's own throwaway computation, not governed corpus content.
"""

from __future__ import annotations

from typing import Callable, Optional
from agents.base import Agent
from agents.sandbox import run_python
from contracts import AskResponse, Label, Tier
from trust.conversations import append_turn, conversation_owner, create_conversation
from trust.ledger import log as ledger_log
from trust.reports import save_report_data

DEFAULT_MAX_RETRIES = 3


def run_code_query(
    question: str,
    principal,
    agent: Agent,
    db_path: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    emit: Optional[Callable[[dict], None]] = None,
    conversation_id: Optional[str] = None,
) -> AskResponse:
    """Execute the complete code-request lifecycle: draft, sandbox-run,
    verify (by execution outcome), retry on failure, abstain on exhaustion.
    """
    def _emit(event: dict) -> None:
        if emit is not None:
            emit(event)

    draft_code = getattr(agent, "draft_code", None)
    if draft_code is None:
        # Active agent backend doesn't support code drafting (e.g. MockAgent
        # in a test context) -- abstain honestly rather than pretending.
        effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
        ledger_entry = ledger_log(
            db_path=db_path,
            actor=principal.person_id,
            action="ASK_ABSTAINED",
            details={"question": question, "reason": "code_backend_unavailable"},
        )
        if conversation_id and conversation_owner(db_path, conversation_id) != principal.person_id:
            conversation_id = None
        if not conversation_id:
            conversation_id = create_conversation(db_path, principal.person_id, question)
        response = AskResponse(
            status="abstained",
            answer="The active agent backend does not support sandboxed code execution.",
            citations=[],
            denials=[],
            effective_label=effective_label,
            ledger_row_id=ledger_entry.row_id,
            conversation_id=conversation_id,
        )
        append_turn(db_path, conversation_id, question, response)
        return response

    if conversation_id and conversation_owner(db_path, conversation_id) != principal.person_id:
        conversation_id = None
    if not conversation_id:
        conversation_id = create_conversation(db_path, principal.person_id, question)

    # Every earlier failure is fed back, not just the latest: with only the
    # most recent one, the model "forgets" earlier corrections (observed:
    # attempt 3 reverting to Java after attempt 2 was corrected for input()).
    failures: list[str] = []
    feedback: Optional[str] = None
    last_code: str = ""
    last_result = None

    for attempt in range(1, max_retries + 1):
        _emit({"stage": "code_drafting", "status": "start", "attempt": attempt, "max_attempts": max_retries})
        try:
            code_answer = draft_code(question, feedback=feedback)
        except Exception as exc:
            _emit({"stage": "code_drafting", "status": "error", "attempt": attempt, "message": str(exc)})
            failures.append(f"Attempt {attempt}: drafting agent raised an error ({exc}).")
            feedback = "\n\n".join(failures)
            continue
        _emit({"stage": "code_drafting", "status": "done", "attempt": attempt,
               "model": getattr(agent, "last_model_used", None)})

        last_code = code_answer.code
        _emit({"stage": "code_execution", "status": "start", "attempt": attempt})
        result = run_python(code_answer.code)
        last_result = result
        _emit({
            "stage": "code_execution",
            "status": "done",
            "attempt": attempt,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        })

        if result.exit_code == 0 and not result.timed_out:
            answer = (
                f"## Code\n\n```python\n{code_answer.code}\n```\n\n"
                f"{('**Explanation:** ' + code_answer.explanation) if code_answer.explanation else ''}\n\n"
                f"## Sandbox Output\n\n```\n{result.stdout or '(no output)'}\n```"
            )
            effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
            ledger_entry = ledger_log(
                db_path=db_path,
                actor=principal.person_id,
                action="ASK_ANSWERED",
                details={
                    "question": question,
                    "category": "code",
                    "attempt": attempt,
                    "exit_code": result.exit_code,
                    "duration_seconds": result.duration_seconds,
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
                code=code_answer.code,
                code_execution=result,
                model_used=getattr(agent, "last_model_used", None),
            )
            save_report_data(db_path=db_path, ledger_row_id=ledger_entry.row_id,
                              person_id=principal.person_id, question=question, response=response)
            append_turn(db_path, conversation_id, question, response)
            return response

        # Feed the REAL failure back for the next attempt -- never a guess.
        reason = "timed out" if result.timed_out else f"exited with code {result.exit_code}"
        failures.append(
            f"Attempt {attempt}: the script {reason}.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        feedback = "\n\n".join(failures)

    # Retries exhausted: ABSTAIN. Never claim code "works" that didn't exit 0.
    answer = (
        f"Response withheld: no candidate script executed successfully in the sandbox after "
        f"{max_retries} attempts. Last failure: {failures[-1] if failures else 'unknown'}"
    )
    effective_label = Label(tier=Tier.PUBLIC, compartments=frozenset())
    ledger_entry = ledger_log(
        db_path=db_path,
        actor=principal.person_id,
        action="ASK_ABSTAINED",
        details={"question": question, "reason": "code_execution_retries_exhausted"},
    )
    response = AskResponse(
        status="abstained",
        answer=answer,
        citations=[],
        denials=[],
        effective_label=effective_label,
        ledger_row_id=ledger_entry.row_id,
        conversation_id=conversation_id,
        code=last_code or None,
        code_execution=last_result,
        model_used=getattr(agent, "last_model_used", None),
    )
    append_turn(db_path, conversation_id, question, response)
    return response
