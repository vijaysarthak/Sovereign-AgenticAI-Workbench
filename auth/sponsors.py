"""Compartment ownership, sponsor authority, and delegation engine.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. Two paths to a compartment:
   - Compartment Sponsors own compartments and decide who may enter them
     (grant_compartment / revoke_compartment below).
   - An active System Administrator may assign ANY compartment set to another
     user through the explicit admin path (admin_set_compartments below).
     The admin cannot use the sponsor path, and cannot assign to themselves.
2. Ownership is declared in config/compartments.json, checked in and signed off once.
3. Outside the admin path, only a compartment's sponsor (or authorized delegate) may grant/revoke it.
4. Owning one compartment gives ZERO authority over other compartments.
5. NOBODY can grant compartments to themselves.
6. Every grant/revoke action writes an immutable audit ledger entry.
7. Startup check: If config/compartments.json names a sponsor whose account does not exist,
   fail loudly with a specific error identifying the missing sponsor.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional
from contracts import Compartment
from trust.ledger import get_db_connection, log as ledger_log

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "compartments.json"


def load_compartment_config(config_path: Optional[str | Path] = None) -> dict[str, dict[str, str]]:
    """Load and parse the declarative compartment sponsor configuration."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Compartment configuration file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate that every declared compartment is a valid Compartment enum
    validated = {}
    for comp_name, info in data.items():
        comp_enum = Compartment(comp_name)
        validated[comp_enum.value] = info
    return validated


def init_grants_tables(db_path: str) -> None:
    """Initialize compartment audit and delegation tables."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compartment_grants (
                    grant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compartment TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compartment_delegates (
                    compartment TEXT NOT NULL,
                    delegate_id TEXT NOT NULL,
                    assigned_by TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    PRIMARY KEY (compartment, delegate_id)
                );
                """
            )
    finally:
        conn.close()


def verify_sponsors(db_path: str, config_path: Optional[str | Path] = None) -> None:
    """Validate that every declared sponsor account exists in the user store.

    CRITICAL RULE: If config/compartments.json names a sponsor whose account does
    not exist, FAIL LOUDLY AT STARTUP.
    """
    from auth.users import init_users_table
    init_users_table(db_path)
    config = load_compartment_config(config_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        for comp_name, info in config.items():
            sponsor_id = info.get("sponsor")
            if not sponsor_id:
                raise RuntimeError(
                    f"Configuration error: Compartment '{comp_name}' has no sponsor ID specified."
                )

            cursor.execute(
                "SELECT person_id, is_active FROM users WHERE person_id = ?;",
                (sponsor_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError(
                    f"FATAL STARTUP CHECK FAILED: Compartment '{comp_name}' declares sponsor '{sponsor_id}' "
                    f"({info.get('description', 'No description')}), but that account DOES NOT EXIST in the user store. "
                    "Accounts must be provisioned by an administrator before compartment sponsorship can activate."
                )
            if not bool(row["is_active"]):
                raise RuntimeError(
                    f"FATAL STARTUP CHECK FAILED: Sponsor '{sponsor_id}' for compartment '{comp_name}' "
                    "is DEACTIVATED. A deactivated account cannot sponsor compartments."
                )
    finally:
        conn.close()


def is_sponsor_or_delegate(
    db_path: str,
    actor_id: str,
    compartment: Compartment,
    config_path: Optional[str | Path] = None,
) -> bool:
    """Check whether actor_id is the primary sponsor or an authorized delegate of compartment."""
    config = load_compartment_config(config_path)
    comp_val = compartment.value
    comp_info = config.get(comp_val)
    if not comp_info:
        return False

    # 1. Primary sponsor check
    if comp_info.get("sponsor") == actor_id:
        return True

    # 2. Delegate check
    init_grants_tables(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM compartment_delegates WHERE compartment = ? AND delegate_id = ?;",
            (comp_val, actor_id),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def get_sponsored_compartments(
    db_path: str,
    actor_id: str,
    config_path: Optional[str | Path] = None,
) -> list[Compartment]:
    """Return all compartments that actor_id has authority to grant/revoke."""
    config = load_compartment_config(config_path)
    sponsored: set[Compartment] = set()

    for comp_val, info in config.items():
        if info.get("sponsor") == actor_id:
            sponsored.add(Compartment(comp_val))

    init_grants_tables(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT compartment FROM compartment_delegates WHERE delegate_id = ?;",
            (actor_id,),
        )
        for row in cursor.fetchall():
            try:
                sponsored.add(Compartment(row["compartment"]))
            except ValueError:
                pass
    finally:
        conn.close()

    return sorted(list(sponsored), key=lambda c: c.value)


def grant_compartment(
    db_path: str,
    actor_id: str,
    target_id: str,
    compartment: Compartment,
    config_path: Optional[str | Path] = None,
) -> None:
    """Grant a compartment clearance to an employee.

    Enforces all non-negotiable sponsor rules:
    - Actor cannot grant to themselves.
    - Actor must sponsor this specific compartment.
    - Appends to immutable audit ledger.
    """
    if actor_id == target_id:
        raise PermissionError(
            "Self-grant violation blocked: A sponsor cannot grant compartments to themselves. "
            "A different authorized officer is required."
        )

    if not is_sponsor_or_delegate(db_path, actor_id, compartment, config_path):
        raise PermissionError(
            f"Unauthorized: Actor '{actor_id}' does not sponsor compartment '{compartment.value}'. "
            "Compartments may only be granted by their designated sponsor."
        )

    init_grants_tables(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT compartments FROM users WHERE person_id = ? AND is_active = 1;", (target_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Active target employee '{target_id}' not found.")

            current_comps = set(json.loads(row["compartments"]))
            current_comps.add(compartment.value)

            cursor.execute(
                "UPDATE users SET compartments = ? WHERE person_id = ?;",
                (json.dumps(sorted(list(current_comps))), target_id),
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO compartment_grants (compartment, actor_id, target_id, action, timestamp)
                VALUES (?, ?, ?, 'GRANT', ?);
                """,
                (compartment.value, actor_id, target_id, now_iso),
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="GRANT_COMPARTMENT",
        details={
            "subject": target_id,
            "compartment": compartment.value,
        },
    )


def revoke_compartment(
    db_path: str,
    actor_id: str,
    target_id: str,
    compartment: Compartment,
    config_path: Optional[str | Path] = None,
) -> None:
    """Revoke a compartment clearance from an employee."""
    if actor_id == target_id:
        raise PermissionError("Self-modification violation blocked: Cannot revoke compartments from yourself.")

    if not is_sponsor_or_delegate(db_path, actor_id, compartment, config_path):
        raise PermissionError(
            f"Unauthorized: Actor '{actor_id}' does not sponsor compartment '{compartment.value}'."
        )

    init_grants_tables(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT compartments FROM users WHERE person_id = ? AND is_active = 1;", (target_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Active target employee '{target_id}' not found.")

            current_comps = set(json.loads(row["compartments"]))
            current_comps.discard(compartment.value)

            cursor.execute(
                "UPDATE users SET compartments = ? WHERE person_id = ?;",
                (json.dumps(sorted(list(current_comps))), target_id),
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO compartment_grants (compartment, actor_id, target_id, action, timestamp)
                VALUES (?, ?, ?, 'REVOKE', ?);
                """,
                (compartment.value, actor_id, target_id, now_iso),
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="REVOKE_COMPARTMENT",
        details={
            "subject": target_id,
            "compartment": compartment.value,
        },
    )


def delegate_sponsor(
    db_path: str,
    actor_id: str,
    delegate_id: str,
    compartment: Compartment,
    config_path: Optional[str | Path] = None,
) -> None:
    """Delegate granting rights for actor's owned compartment to another officer."""
    if actor_id == delegate_id:
        raise PermissionError("Cannot delegate to yourself.")

    config = load_compartment_config(config_path)
    comp_info = config.get(compartment.value)
    if not comp_info or comp_info.get("sponsor") != actor_id:
        raise PermissionError(
            f"Only the primary sponsor ('{comp_info.get('sponsor')}') of '{compartment.value}' may delegate authority."
        )

    init_grants_tables(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compartment_delegates (compartment, delegate_id, assigned_by, timestamp)
                VALUES (?, ?, ?, ?);
                """,
                (compartment.value, delegate_id, actor_id, now_iso),
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="DELEGATE_COMPARTMENT",
        details={
            "delegate": delegate_id,
            "compartment": compartment.value,
        },
    )


def admin_set_compartments(
    db_path: str,
    actor_id: str,
    target_id: str,
    compartments: list[Compartment],
) -> dict[str, list[str]]:
    """Replace a user's full compartment set via the System Administrator path.

    Enforces:
    - Actor must be an ACTIVE administrator, re-checked here from the user
      store rather than trusted from the caller.
    - Nobody can assign compartments to themselves, the admin included.
    - Target must be an existing, active account.
    - Every added/removed compartment is recorded in compartment_grants and
      in one immutable ledger entry.

    Returns {"compartments": [...final set...], "added": [...], "removed": [...]}.
    """
    if actor_id == target_id:
        raise PermissionError(
            "Self-assignment violation blocked: An administrator cannot assign compartments to themselves."
        )

    requested = sorted({Compartment(c).value for c in compartments})

    init_grants_tables(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_admin, is_active FROM users WHERE person_id = ?;", (actor_id,))
            actor = cursor.fetchone()
            if not actor or not actor["is_admin"] or not actor["is_active"]:
                raise PermissionError(
                    f"Unauthorized: '{actor_id}' is not an active System Administrator."
                )

            cursor.execute("SELECT compartments FROM users WHERE person_id = ? AND is_active = 1;", (target_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Active target employee '{target_id}' not found.")

            current = set(json.loads(row["compartments"]))
            added = sorted(set(requested) - current)
            removed = sorted(current - set(requested))
            if not added and not removed:
                return {"compartments": requested, "added": [], "removed": []}

            cursor.execute(
                "UPDATE users SET compartments = ? WHERE person_id = ?;",
                (json.dumps(requested), target_id),
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.executemany(
                """
                INSERT INTO compartment_grants (compartment, actor_id, target_id, action, timestamp)
                VALUES (?, ?, ?, ?, ?);
                """,
                [(c, actor_id, target_id, "ADMIN_GRANT", now_iso) for c in added]
                + [(c, actor_id, target_id, "ADMIN_REVOKE", now_iso) for c in removed],
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="ADMIN_SET_COMPARTMENTS",
        details={
            "subject": target_id,
            "added": added,
            "removed": removed,
            "compartments": requested,
        },
    )
    return {"compartments": requested, "added": added, "removed": removed}
