"""Cryptographically hash-chained SQLite audit ledger.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. Append-only ledger recording all security-critical operations (access evaluations,
   clearance modifications, queries, and abstentions).
2. Each row's SHA-256 hash covers its own canonical fields PLUS the previous row's hash.
   Editing any row breaks every subsequent hash in the chain.
3. Row 1's prev_hash is exactly 64 zeros ("0" * 64).
4. Canonical JSON serialization (sorted keys, compact separators) ensures hash determinism.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Optional
from contracts import LedgerEntry

GENESIS_PREV_HASH = "0" * 64


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Create or connect to the SQLite database and ensure WAL mode."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ledger (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def init_ledger_table(db_path: str) -> None:
    """Initialize the ledger SQLite table if not exists."""
    conn = get_db_connection(db_path)
    conn.close()


def json_canonical_default(obj: Any) -> Any:
    """Canonical serializer for non-standard JSON types (sets, enums, Pydantic)."""
    if isinstance(obj, (set, frozenset)):
        return sorted([json_canonical_default(x) for x in obj], key=lambda x: str(x))
    if hasattr(obj, "value"):
        return obj.value
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return str(obj)


def compute_payload_hash(
    timestamp: str,
    actor: str,
    action: str,
    details: dict[str, Any],
    prev_hash: str,
) -> str:
    """Compute deterministic SHA-256 hash over canonical JSON serialization."""
    payload = {
        "action": action,
        "actor": actor,
        "details": details,
        "prev_hash": prev_hash,
        "timestamp": timestamp,
    }
    canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=json_canonical_default)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def log(
    db_path: str,
    actor: str,
    action: str,
    details: dict[str, Any],
    timestamp: Optional[str] = None,
) -> LedgerEntry:
    """Append a new tamper-evident record to the audit ledger."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT row_id, hash FROM ledger ORDER BY row_id DESC LIMIT 1;")
            latest_row = cursor.fetchone()

            if latest_row is None:
                prev_hash = GENESIS_PREV_HASH
            else:
                prev_hash = latest_row["hash"]

            current_hash = compute_payload_hash(
                timestamp=timestamp,
                actor=actor,
                action=action,
                details=details,
                prev_hash=prev_hash,
            )

            details_json = json.dumps(details, sort_keys=True, default=json_canonical_default)
            cursor.execute(
                """
                INSERT INTO ledger (timestamp, actor, action, details, prev_hash, hash)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (timestamp, actor, action, details_json, prev_hash, current_hash),
            )
            row_id = cursor.lastrowid

            return LedgerEntry(
                row_id=row_id,
                timestamp=timestamp,
                actor=actor,
                action=action,
                details=details,
                prev_hash=prev_hash,
                hash=current_hash,
            )
    finally:
        conn.close()


def head(db_path: str) -> Optional[LedgerEntry]:
    """Retrieve the most recent entry in the ledger."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ledger ORDER BY row_id DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return None
        return LedgerEntry(
            row_id=row["row_id"],
            timestamp=row["timestamp"],
            actor=row["actor"],
            action=row["action"],
            details=json.loads(row["details"]),
            prev_hash=row["prev_hash"],
            hash=row["hash"],
        )
    finally:
        conn.close()


def read(db_path: str, limit: int = 50) -> list[LedgerEntry]:
    """Read the most recent ledger entries in descending order."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ledger ORDER BY row_id DESC LIMIT ?;", (limit,))
        rows = cursor.fetchall()
        entries = []
        for r in rows:
            entries.append(
                LedgerEntry(
                    row_id=r["row_id"],
                    timestamp=r["timestamp"],
                    actor=r["actor"],
                    action=r["action"],
                    details=json.loads(r["details"]),
                    prev_hash=r["prev_hash"],
                    hash=r["hash"],
                )
            )
        return entries
    finally:
        conn.close()


def verify(db_path: str) -> tuple[bool, Optional[int]]:
    """Cryptographically verify the entire ledger chain.

    Checks:
    1. Row 1 prev_hash is exactly 64 zeros.
    2. Every subsequent row's prev_hash exactly equals the preceding row's stored hash.
    3. Every row's stored hash exactly matches the recomputed canonical SHA-256.

    Returns:
        (True, None) if the entire chain is valid.
        (False, broken_row_id) if any corruption, alteration, or deletion is detected.
    """
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ledger ORDER BY row_id ASC;")
        rows = cursor.fetchall()

        if not rows:
            return True, None

        expected_prev_hash = GENESIS_PREV_HASH

        for row in rows:
            row_id = row["row_id"]
            timestamp = row["timestamp"]
            actor = row["actor"]
            action = row["action"]
            details = json.loads(row["details"])
            prev_hash = row["prev_hash"]
            stored_hash = row["hash"]

            # 1. Chain continuity check
            if prev_hash != expected_prev_hash:
                return False, row_id

            # 2. Content integrity check
            recomputed_hash = compute_payload_hash(
                timestamp=timestamp,
                actor=actor,
                action=action,
                details=details,
                prev_hash=prev_hash,
            )
            if recomputed_hash != stored_hash:
                return False, row_id

            expected_prev_hash = stored_hash

        return True, None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DEMO ONLY: Tampering Simulation
# WARNING: MUST NEVER BE IMPORTED BY api/ OR ANY PRODUCTION SERVICE
# ---------------------------------------------------------------------------

def tamper(db_path: str, row_id: int, new_action: str, new_details: Optional[dict[str, Any]] = None) -> None:
    """DEMO ONLY: Deliberately modify an existing ledger entry to demonstrate chain failure.

    This function simulates an unauthorized attacker modifying SQLite data directly.
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            if new_details is not None:
                cursor.execute(
                    "UPDATE ledger SET action = ?, details = ? WHERE row_id = ?;",
                    (new_action, json.dumps(new_details, sort_keys=True), row_id),
                )
            else:
                cursor.execute(
                    "UPDATE ledger SET action = ? WHERE row_id = ?;",
                    (new_action, row_id),
                )
    finally:
        conn.close()
