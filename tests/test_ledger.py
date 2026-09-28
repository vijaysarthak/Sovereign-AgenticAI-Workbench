"""Unit tests for trust/ledger.py.

Verifies:
1. Append-only logging to SQLite.
2. Row 1 prev_hash is 64 zeros.
3. Cryptographic hash chaining: row i prev_hash == row i-1 hash.
4. Canonical JSON serialization determinism.
5. verify() returns (True, None) for intact chain.
6. tamper() immediately causes verify() to return (False, broken_row_id).
7. read() and head() functionality.
"""

from pathlib import Path
from trust.ledger import (
    GENESIS_PREV_HASH,
    head,
    log,
    read,
    tamper,
    verify,
)


def test_genesis_entry(tmp_path: Path):
    """The very first entry in the ledger has prev_hash of 64 zeros and verifies cleanly."""
    db_path = str(tmp_path / "ledger_test.db")
    entry = log(
        db_path=db_path,
        actor="system_bootstrap",
        action="INIT",
        details={"version": "1.0.0"},
    )

    assert entry.row_id == 1
    assert entry.prev_hash == GENESIS_PREV_HASH
    assert len(entry.hash) == 64

    # Verify must pass
    intact, broken_id = verify(db_path)
    assert intact is True
    assert broken_id is None


def test_hash_chaining(tmp_path: Path):
    """Each subsequent row links cryptographically to the previous row's hash."""
    db_path = str(tmp_path / "ledger_chain.db")

    e1 = log(db_path, actor="admin-01", action="CREATE_USER", details={"user": "u1"})
    e2 = log(db_path, actor="admin-01", action="SET_GRADE", details={"user": "u1", "grade": "B"})
    e3 = log(db_path, actor="cvo-01", action="GRANT_COMPARTMENT", details={"user": "u1", "comp": "vigilance"})

    assert e1.prev_hash == GENESIS_PREV_HASH
    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash

    intact, broken_id = verify(db_path)
    assert intact is True
    assert broken_id is None

    # Test head and read
    latest = head(db_path)
    assert latest is not None
    assert latest.row_id == 3
    assert latest.action == "GRANT_COMPARTMENT"

    recent = read(db_path, limit=2)
    assert len(recent) == 2
    assert recent[0].row_id == 3
    assert recent[1].row_id == 2


def test_tampering_detection(tmp_path: Path):
    """Tampering with any row breaks the cryptographic chain at that exact row."""
    db_path = str(tmp_path / "ledger_tamper.db")

    log(db_path, actor="admin", action="ACT_1", details={"data": 1})
    log(db_path, actor="admin", action="ACT_2", details={"data": 2})
    log(db_path, actor="admin", action="ACT_3", details={"data": 3})

    intact, _ = verify(db_path)
    assert intact is True

    # Tamper with row 2 (e.g. modify the action or details directly in SQLite)
    tamper(db_path, row_id=2, new_action="UNAUTHORIZED_MODIFICATION")

    # verify() must catch this alteration immediately
    intact, broken_id = verify(db_path)
    assert intact is False
    assert broken_id == 2


def test_empty_ledger(tmp_path: Path):
    """An empty ledger verifies as intact with no broken rows."""
    db_path = str(tmp_path / "empty.db")
    intact, broken_id = verify(db_path)
    assert intact is True
    assert broken_id is None
    assert head(db_path) is None
    assert read(db_path) == []
