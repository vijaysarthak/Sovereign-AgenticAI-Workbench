"""Persistent per-person conversation history: titles + question/answer turns.

Unlike the audit ledger (append-only, hash-chained, readable by every
authenticated user as a shared transparency log) and report_data (full-
fidelity answer storage keyed by ledger row, read back only through the
ownership-checked /report/{id} endpoint), this table exists purely so a
person can see and resume their OWN past conversations across logins -- a UI
convenience, like Claude's chat history sidebar. Every read and write here is
scoped to person_id; nothing here is shared between users, and every read
re-checks ownership before returning anything.

This also supplies the short "recent turns" context fed into intent
classification and drafting (see harness/runner.py) -- now correctly scoped
per-conversation instead of a global per-person window, and durable instead
of in-memory.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Optional
from contracts import AskResponse
from trust.ledger import get_db_connection

MAX_TITLE_CHARS = 60
DEFAULT_CONTEXT_TURNS = max(0, int(os.getenv("CONVERSATION_MEMORY_TURNS", "2")))


def init_conversations_table(db_path: str) -> None:
    """Idempotent: safe to call before every operation, matching trust/reports.py's pattern."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_turns_conv "
                "ON conversation_turns(conversation_id, turn_index);"
            )
    finally:
        conn.close()


def _title_from_question(question: str) -> str:
    q = " ".join(question.strip().split())
    if len(q) <= MAX_TITLE_CHARS:
        return q
    return q[:MAX_TITLE_CHARS].rstrip() + "..."


def create_conversation(db_path: str, person_id: str, first_question: str) -> str:
    """Start a new conversation, titled from its first question, and return its id."""
    init_conversations_table(db_path)
    conversation_id = uuid.uuid4().hex
    now = time.time()
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO conversations (conversation_id, person_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?);",
                (conversation_id, person_id, _title_from_question(first_question), now, now),
            )
    finally:
        conn.close()
    return conversation_id


def conversation_owner(db_path: str, conversation_id: str) -> Optional[str]:
    """Return the owning person_id, or None if the conversation doesn't exist."""
    init_conversations_table(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT person_id FROM conversations WHERE conversation_id = ?;", (conversation_id,))
        row = cursor.fetchone()
        return row["person_id"] if row else None
    finally:
        conn.close()


def append_turn(db_path: str, conversation_id: str, question: str, response: AskResponse) -> None:
    """Append one Q&A turn and bump the conversation's updated_at (for sort order)."""
    init_conversations_table(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM conversation_turns WHERE conversation_id = ?;",
                (conversation_id,),
            )
            turn_index = cursor.fetchone()[0]
            now = time.time()
            conn.execute(
                """
                INSERT INTO conversation_turns
                    (conversation_id, turn_index, question, answer, status, response_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    conversation_id,
                    turn_index,
                    question,
                    response.answer,
                    response.status,
                    response.model_dump_json(),
                    now,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?;",
                (now, conversation_id),
            )
    finally:
        conn.close()


def list_conversations(db_path: str, person_id: str) -> list[dict[str, Any]]:
    """List this person's conversations, most recently updated first."""
    init_conversations_table(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT c.conversation_id, c.title, c.created_at, c.updated_at, "
            "COUNT(t.id) AS turn_count "
            "FROM conversations c "
            "LEFT JOIN conversation_turns t ON t.conversation_id = c.conversation_id "
            "WHERE c.person_id = ? "
            "GROUP BY c.conversation_id "
            "ORDER BY c.updated_at DESC;",
            (person_id,),
        )
        return [
            {
                "conversation_id": r["conversation_id"],
                "title": r["title"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "turn_count": r["turn_count"],
            }
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_conversation(db_path: str, conversation_id: str, person_id: str) -> Optional[dict[str, Any]]:
    """Full turn history for this conversation, or None if it doesn't exist or isn't owned by person_id."""
    owner = conversation_owner(db_path, conversation_id)
    if owner is None or owner != person_id:
        return None
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT title, created_at, updated_at FROM conversations WHERE conversation_id = ?;",
            (conversation_id,),
        )
        meta = cursor.fetchone()
        cursor.execute(
            "SELECT question, response_json FROM conversation_turns "
            "WHERE conversation_id = ? ORDER BY turn_index ASC;",
            (conversation_id,),
        )
        turns = [
            {"question": r["question"], "response": json.loads(r["response_json"])}
            for r in cursor.fetchall()
        ]
        return {
            "conversation_id": conversation_id,
            "title": meta["title"],
            "created_at": meta["created_at"],
            "updated_at": meta["updated_at"],
            "turns": turns,
        }
    finally:
        conn.close()


def rename_conversation(db_path: str, conversation_id: str, person_id: str, title: str) -> bool:
    """Returns False without effect if the conversation doesn't exist or isn't owned by person_id."""
    owner = conversation_owner(db_path, conversation_id)
    if owner is None or owner != person_id:
        return False
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE conversations SET title = ? WHERE conversation_id = ?;",
                (title.strip()[:MAX_TITLE_CHARS] or "Untitled", conversation_id),
            )
    finally:
        conn.close()
    return True


def delete_conversation(db_path: str, conversation_id: str, person_id: str) -> bool:
    """Returns False without effect if the conversation doesn't exist or isn't owned by person_id."""
    owner = conversation_owner(db_path, conversation_id)
    if owner is None or owner != person_id:
        return False
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM conversation_turns WHERE conversation_id = ?;", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE conversation_id = ?;", (conversation_id,))
    finally:
        conn.close()
    return True


def get_recent_context(db_path: str, conversation_id: Optional[str], max_turns: int = DEFAULT_CONTEXT_TURNS) -> str:
    """Compact text block of the last `max_turns` turns for THIS conversation,
    for intent classification / drafting prompts. Context only -- never a
    citation source; every citation still has to verify against freshly
    retrieved passages regardless of what's here. Kept short deliberately:
    more turns means more prompt text the local model re-reads every call.
    """
    if max_turns <= 0 or not conversation_id:
        return ""
    init_conversations_table(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT question, answer FROM conversation_turns WHERE conversation_id = ? "
            "ORDER BY turn_index DESC LIMIT ?;",
            (conversation_id, max_turns),
        )
        rows = list(reversed(cursor.fetchall()))
    finally:
        conn.close()
    if not rows:
        return ""
    lines = []
    for r in rows:
        preview = " ".join(r["answer"].strip().split())
        if len(preview) > 220:
            preview = preview[:220].rstrip() + "..."
        lines.append(f"Q: {r['question']}\nA: {preview}")
    return "\n\n".join(lines)
