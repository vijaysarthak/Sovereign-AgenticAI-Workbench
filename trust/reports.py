"""Full-fidelity report data store, keyed by audit ledger row ID.

The audit ledger (trust/ledger.py) is readable by every authenticated user as
a transparency log, so it deliberately stores only a truncated answer preview
per entry — never the full synthesized answer, citations, or denials, which
may be Confidential/Secret. This module stores that full data separately so
/report/{id} can regenerate a complete .docx without leaking it through the
shared ledger stream.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from contracts import AskResponse
from trust.ledger import get_db_connection


def init_reports_table(db_path: str) -> None:
    """Initialize the report_data table in SQLite if it does not exist."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS report_data (
                    ledger_row_id INTEGER PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    response_json TEXT NOT NULL
                );
                """
            )
    finally:
        conn.close()


def save_report_data(
    db_path: str,
    ledger_row_id: int,
    person_id: str,
    question: str,
    response: AskResponse,
) -> None:
    """Persist the full AskResponse for later report regeneration."""
    init_reports_table(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO report_data (ledger_row_id, person_id, question, response_json)
                VALUES (?, ?, ?, ?);
                """,
                (ledger_row_id, person_id, question, response.model_dump_json()),
            )
    finally:
        conn.close()


def get_report_data(db_path: str, ledger_row_id: int) -> Optional[dict[str, Any]]:
    """Retrieve the full stored AskResponse (as a dict) and its owning person_id."""
    init_reports_table(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT person_id, question, response_json FROM report_data WHERE ledger_row_id = ?;",
            (ledger_row_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "person_id": row["person_id"],
            "question": row["question"],
            "response": json.loads(row["response_json"]),
        }
    finally:
        conn.close()
