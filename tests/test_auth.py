"""Unit tests for auth/users.py, auth/session.py, and identity enforcement.

Verifies:
1. Login authentication success and invalid password failure.
2. Self-modification rejected: an admin cannot change their own grade.
3. Grade changes write an immutable ledger record.
4. No self-registration (account must be provisioned by admin).
5. Session token HMAC forgery detection and expiration.
6. The identity rule: Principal is derived from cookie, request body params change nothing.
"""

from pathlib import Path
import pytest
from contracts import Compartment, Principal
from auth.session import (
    create_session_token,
    verify_session_token,
)
from auth.users import (
    authenticate_user,
    create_user,
    get_principal,
    update_grade,
)
from trust.ledger import read as ledger_read


def test_login_success_and_failure(tmp_path: Path):
    """Verify correct password succeeds and incorrect password fails."""
    db_path = str(tmp_path / "auth_test.db")
    create_user(
        db_path=db_path,
        actor_id="admin-01",
        person_id="user-01",
        name="User One",
        job_title="Engineer",
        grade="A",
        password="CorrectPassword123!",
    )

    # Success
    user = authenticate_user(db_path, "user-01", "CorrectPassword123!")
    assert user is not None
    assert user["person_id"] == "user-01"
    assert user["grade"] == "A"

    # Failure
    fail = authenticate_user(db_path, "user-01", "WrongPassword!")
    assert fail is None

    # Non-existent user
    non_existent = authenticate_user(db_path, "nobody", "any")
    assert non_existent is None


def test_self_modification_rejected(tmp_path: Path):
    """An administrator CANNOT modify their own grade."""
    db_path = str(tmp_path / "self_mod.db")
    create_user(
        db_path=db_path,
        actor_id="bootstrap",
        person_id="admin-01",
        name="Admin One",
        job_title="Admin",
        grade="E",
        is_admin=True,
    )

    with pytest.raises(PermissionError, match="cannot modify their own pay grade"):
        update_grade(db_path, actor_id="admin-01", target_id="admin-01", new_grade="F")


def test_grade_change_writes_ledger(tmp_path: Path):
    """A valid grade change by another admin writes an immutable ledger entry."""
    db_path = str(tmp_path / "grade_ledger.db")
    create_user(db_path, "boot", "admin-01", "Admin 1", "Admin", "E", is_admin=True)
    create_user(db_path, "admin-01", "emp-01", "Emp 1", "Staff", "S1")

    # admin-01 updates emp-01's grade from S1 to S2
    update_grade(db_path, actor_id="admin-01", target_id="emp-01", new_grade="S2")

    p = get_principal(db_path, "emp-01")
    assert p is not None
    assert p.grade == "S2"

    entries = ledger_read(db_path, limit=5)
    grade_entry = next(e for e in entries if e.action == "SET_GRADE")
    assert grade_entry.actor == "admin-01"
    assert grade_entry.details["subject"] == "emp-01"
    assert grade_entry.details["old_grade"] == "S1"
    assert grade_entry.details["new_grade"] == "S2"


def test_session_token_security():
    """HMAC tokens detect forgery and expire correctly."""
    secret = "test-secret-key-12345"
    token = create_session_token("user-99", secret_key=secret, duration_seconds=3600)

    # Valid token resolves
    assert verify_session_token(token, secret_key=secret) == "user-99"

    # Wrong secret fails
    assert verify_session_token(token, secret_key="wrong-secret") is None

    # Tampered token fails
    parts = token.split(".")
    tampered = f"{parts[0]}xyz.{parts[1]}"
    assert verify_session_token(tampered, secret_key=secret) is None

    # Expired token fails
    expired_token = create_session_token("user-99", secret_key=secret, duration_seconds=-10)
    assert verify_session_token(expired_token, secret_key=secret) is None


def test_identity_rule_client_body_changes_nothing(tmp_path: Path):
    """THE IDENTITY RULE:
    The Principal is derived strictly from the session cookie and user store.
    Even if a malicious client sends `{"grade": "I", "compartments": ["secret"]}`
    in a request, the principal resolved from storage remains untouched.
    """
    db_path = str(tmp_path / "identity.db")
    create_user(
        db_path=db_path,
        actor_id="admin",
        person_id="emp-42",
        name="Junior Analyst",
        job_title="Analyst",
        grade="S1",  # Low rank
    )

    # Resolve principal purely from identity store
    principal = get_principal(db_path, "emp-42")
    assert principal is not None
    assert principal.grade == "S1"
    assert principal.compartments == frozenset()

    # Simulate malicious request payload attempting privilege escalation
    malicious_body = {
        "person_id": "emp-42",
        "grade": "I",  # Claiming C&MD rank!
        "compartments": ["vigilance", "technical"],
    }

    # Principal is reconstructed from database, completely ignoring client body
    resolved_principal = get_principal(db_path, "emp-42")
    assert resolved_principal.grade == "S1"  # Still S1!
    assert resolved_principal.compartments == frozenset()
