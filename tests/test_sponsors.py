"""Unit tests for auth/sponsors.py.

Verifies:
1. An admin CANNOT use the sponsor grant path (admins assign via admin_set_compartments).
6. The admin path: admin can set any compartments on another user, never on self,
   non-admins are rejected, and every change is ledgered.
2. A sponsor CANNOT grant a compartment they do not own.
3. Nobody can grant a compartment to themselves.
4. A valid sponsor grant succeeds and writes an immutable ledger entry.
5. Missing sponsor account declared in config fails loudly at startup.
"""

import json
from pathlib import Path
import pytest
from contracts import Compartment
from auth.sponsors import (
    admin_set_compartments,
    grant_compartment,
    revoke_compartment,
    verify_sponsors,
)
from auth.users import create_user, get_principal
from trust.ledger import read as ledger_read


@pytest.fixture
def test_setup(tmp_path: Path):
    """Set up a test database with an admin, two sponsors, and a regular user."""
    db_path = str(tmp_path / "sponsor_test.db")
    config_path = tmp_path / "test_compartments.json"

    # Config with CVO and Safety sponsors
    config_data = {
        "vigilance": {"sponsor": "cvo-001", "description": "Chief Vigilance Officer"},
        "hse": {"sponsor": "safety-001", "description": "Head of Safety"},
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    # Create users
    create_user(db_path, "boot", "admin-01", "Admin One", "HR Admin", "E", is_admin=True)
    create_user(db_path, "admin-01", "cvo-001", "CVO Officer", "CVO", "G")
    create_user(db_path, "admin-01", "safety-001", "Safety Chief", "Safety Head", "F")
    create_user(db_path, "admin-01", "emp-001", "Process Eng", "Engineer", "B")

    return db_path, config_path


def test_admin_cannot_grant_compartment(test_setup):
    """An administrator CANNOT use the sponsor grant path."""
    db_path, config_path = test_setup

    with pytest.raises(PermissionError, match="does not sponsor compartment"):
        grant_compartment(
            db_path=db_path,
            actor_id="admin-01",
            target_id="emp-001",
            compartment=Compartment.VIGILANCE,
            config_path=config_path,
        )


def test_sponsor_cannot_grant_unowned_compartment(test_setup):
    """A sponsor cannot grant a compartment belonging to another officer."""
    db_path, config_path = test_setup

    # Safety chief attempts to grant vigilance -> REJECTED
    with pytest.raises(PermissionError, match="does not sponsor compartment 'vigilance'"):
        grant_compartment(
            db_path=db_path,
            actor_id="safety-001",
            target_id="emp-001",
            compartment=Compartment.VIGILANCE,
            config_path=config_path,
        )


def test_self_grant_prohibited(test_setup):
    """A sponsor CANNOT grant a compartment to themselves."""
    db_path, config_path = test_setup

    with pytest.raises(PermissionError, match="Self-grant violation blocked"):
        grant_compartment(
            db_path=db_path,
            actor_id="cvo-001",
            target_id="cvo-001",
            compartment=Compartment.VIGILANCE,
            config_path=config_path,
        )


def test_valid_sponsor_grant_and_ledger(test_setup):
    """A valid grant by the designated sponsor updates clearances and writes to ledger."""
    db_path, config_path = test_setup

    grant_compartment(
        db_path=db_path,
        actor_id="cvo-001",
        target_id="emp-001",
        compartment=Compartment.VIGILANCE,
        config_path=config_path,
    )

    p = get_principal(db_path, "emp-001")
    assert p is not None
    assert Compartment.VIGILANCE in p.compartments

    # Verify ledger entry
    entries = ledger_read(db_path, limit=5)
    grant_entry = next(e for e in entries if e.action == "GRANT_COMPARTMENT")
    assert grant_entry.actor == "cvo-001"
    assert grant_entry.details["subject"] == "emp-001"
    assert grant_entry.details["compartment"] == "vigilance"


def test_missing_sponsor_fails_loudly_at_startup(tmp_path: Path):
    """If config/compartments.json names a sponsor who does not exist, fail loudly."""
    db_path = str(tmp_path / "startup_check.db")
    config_path = tmp_path / "bad_config.json"

    # Declare sponsor who has not been provisioned
    config_data = {
        "legal": {"sponsor": "legal-missing-001", "description": "Legal Advisor"}
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    # No users exist in db
    with pytest.raises(RuntimeError, match="FATAL STARTUP CHECK FAILED.*legal-missing-001"):
        verify_sponsors(db_path=db_path, config_path=config_path)


def test_admin_can_set_any_compartments_on_another_user(test_setup):
    """The System Administrator can assign and remove ANY compartment, with ledger entries."""
    db_path, _ = test_setup

    result = admin_set_compartments(
        db_path, "admin-01", "emp-001", [Compartment.VIGILANCE, Compartment.HSE, Compartment.LEGAL]
    )
    assert result["added"] == ["hse", "legal", "vigilance"]
    assert get_principal(db_path, "emp-001").compartments == frozenset(
        {Compartment.VIGILANCE, Compartment.HSE, Compartment.LEGAL}
    )

    result = admin_set_compartments(db_path, "admin-01", "emp-001", [Compartment.HSE])
    assert result == {"compartments": ["hse"], "added": [], "removed": ["legal", "vigilance"]}
    assert get_principal(db_path, "emp-001").compartments == frozenset({Compartment.HSE})

    entries = [e for e in ledger_read(db_path, limit=100) if e.action == "ADMIN_SET_COMPARTMENTS"]
    assert len(entries) == 2
    assert entries[0].details["subject"] == "emp-001"


def test_admin_cannot_set_own_compartments(test_setup):
    db_path, _ = test_setup
    with pytest.raises(PermissionError, match="cannot assign compartments to themselves"):
        admin_set_compartments(db_path, "admin-01", "admin-01", [Compartment.VIGILANCE])


def test_non_admin_cannot_use_admin_compartment_path(test_setup):
    """A sponsor (non-admin) cannot use the admin path, even for their own compartment."""
    db_path, _ = test_setup
    with pytest.raises(PermissionError, match="not an active System Administrator"):
        admin_set_compartments(db_path, "cvo-001", "emp-001", [Compartment.VIGILANCE])
    assert get_principal(db_path, "emp-001").compartments == frozenset()


def test_admin_set_compartments_unknown_target(test_setup):
    db_path, _ = test_setup
    with pytest.raises(ValueError, match="not found"):
        admin_set_compartments(db_path, "admin-01", "ghost-999", [Compartment.HSE])
