"""Audit ledger endpoints for transparency and cryptographic chain verification.

ZERO ACCESS DECISIONS INSIDE.
tamper() is strictly NOT imported here.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query
from contracts import LedgerEntry, Principal
from auth.deps import current_principal, get_db_path
from trust.ledger import read as ledger_read, verify as ledger_verify

router = APIRouter(prefix="/ledger", tags=["Audit Ledger"])


@router.get("", response_model=list[LedgerEntry])
def get_ledger_entries(
    limit: int = Query(default=50, ge=1, le=500),
    principal: Principal = Depends(current_principal),
):
    """Retrieve recent entries from the hash-chained audit ledger."""
    db_path = get_db_path()
    return ledger_read(db_path, limit=limit)


@router.get("/verify")
def verify_ledger_chain(
    principal: Principal = Depends(current_principal),
):
    """Cryptographically verify the entire SQLite ledger hash chain."""
    db_path = get_db_path()
    intact, broken_at = ledger_verify(db_path)
    entries = ledger_read(db_path, limit=100000)
    return {
        "intact": intact,
        "total_rows": len(entries),
        "broken_at_row_id": broken_at,
    }
