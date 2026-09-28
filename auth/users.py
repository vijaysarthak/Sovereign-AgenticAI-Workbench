"""User store, scrypt password hashing, and account provisioning.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. Nobody self-registers. Accounts are provisioned exclusively by administrators.
2. Admins set pay grades, and may assign compartments to OTHER users only
   through auth/sponsors.py's admin_set_compartments.
3. Nobody can modify their own grade, compartments, or admin status.
4. Passwords hashed using hashlib.scrypt with a per-user random salt.
5. Deactivation is a boolean flag, preserving audit ledger referential integrity.
6. Every account modification writes an immutable ledger entry.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from typing import Any, Optional
from contracts import Compartment, Principal, UserSummary, VALID_MRPL_GRADES
from trust.ledger import get_db_connection, log as ledger_log


def init_users_table(db_path: str) -> None:
    """Initialize the users table in SQLite if it does not exist."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    person_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    job_title TEXT NOT NULL,
                    grade TEXT NOT NULL,
                    compartments TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
    finally:
        conn.close()


def hash_password(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    """Hash password using hashlib.scrypt with standard security parameters."""
    if salt_hex is None:
        salt_bytes = os.urandom(16)
        salt_hex = salt_bytes.hex()
    else:
        salt_bytes = bytes.fromhex(salt_hex)

    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_bytes,
        n=16384,
        r=8,
        p=1,
    )
    return derived.hex(), salt_hex


def verify_password(password: str, salt_hex: str, stored_hash_hex: str) -> bool:
    """Verify password against scrypt hash in constant time."""
    computed_hash_hex, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(computed_hash_hex, stored_hash_hex)


def create_user(
    db_path: str,
    actor_id: str,
    person_id: str,
    name: str,
    job_title: str,
    grade: str,
    is_admin: bool = False,
    password: Optional[str] = None,
    must_change_password: bool = True,
) -> tuple[dict[str, Any], str]:
    """Provision a new employee record.

    Admins can set the initial pay grade.
    Compartments are never set here; see auth/sponsors.py.
    Returns (user_record, cleartext_temporary_password).
    """
    init_users_table(db_path)
    grade_upper = grade.strip().upper()
    if grade_upper not in VALID_MRPL_GRADES:
        raise ValueError(f"Invalid MRPL grade '{grade}'.")

    if not password:
        temp_password = f"temp-{secrets.token_hex(6)}"
    else:
        temp_password = password

    pwd_hash, salt = hash_password(temp_password)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT person_id FROM users WHERE person_id = ?;", (person_id,))
            if cursor.fetchone() is not None:
                raise ValueError(f"User with person_id '{person_id}' already exists.")

            cursor.execute(
                """
                INSERT INTO users (
                    person_id, name, job_title, grade, compartments,
                    password_hash, salt, is_admin, is_active,
                    must_change_password, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?);
                """,
                (
                    person_id,
                    name,
                    job_title,
                    grade_upper,
                    json.dumps([]),
                    pwd_hash,
                    salt,
                    1 if is_admin else 0,
                    1 if must_change_password else 0,
                    actor_id,
                    now_iso,
                ),
            )
    finally:
        conn.close()

    # Log to immutable audit ledger
    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="CREATE_USER",
        details={
            "subject": person_id,
            "name": name,
            "grade": grade_upper,
            "is_admin": is_admin,
        },
    )

    user_record = {
        "person_id": person_id,
        "name": name,
        "job_title": job_title,
        "grade": grade_upper,
        "compartments": [],
        "is_admin": is_admin,
        "is_active": True,
        "must_change_password": must_change_password,
    }
    return user_record, temp_password


def update_grade(
    db_path: str,
    actor_id: str,
    target_id: str,
    new_grade: str,
) -> None:
    """Update an employee's MRPL pay grade.

    CRITICAL RULE: Nobody can modify their own grade. An admin attempting to change
    their own grade is blocked in code.
    """
    if actor_id == target_id:
        raise PermissionError("Self-modification blocked: An administrator cannot modify their own pay grade.")

    grade_upper = new_grade.strip().upper()
    if grade_upper not in VALID_MRPL_GRADES:
        raise ValueError(f"Invalid MRPL grade '{new_grade}'.")

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT grade FROM users WHERE person_id = ? AND is_active = 1;", (target_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Active user with person_id '{target_id}' not found.")

            old_grade = row["grade"]
            cursor.execute(
                "UPDATE users SET grade = ? WHERE person_id = ?;",
                (grade_upper, target_id),
            )
    finally:
        conn.close()

    # Log to ledger
    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="SET_GRADE",
        details={
            "subject": target_id,
            "old_grade": old_grade,
            "new_grade": grade_upper,
        },
    )


def deactivate_user(
    db_path: str,
    actor_id: str,
    target_id: str,
) -> None:
    """Deactivate an employee account.

    CRITICAL RULE: Nobody can deactivate their own account.
    Deactivation sets is_active=0 (never delete), preserving ledger references.
    """
    if actor_id == target_id:
        raise PermissionError("Self-modification blocked: Cannot deactivate your own account.")

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = 0 WHERE person_id = ?;", (target_id,))
            if cursor.rowcount == 0:
                raise ValueError(f"User with person_id '{target_id}' not found.")
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="DEACTIVATE_USER",
        details={"subject": target_id},
    )


def reactivate_user(
    db_path: str,
    actor_id: str,
    target_id: str,
) -> None:
    """Reactivate a previously deactivated employee account."""
    if actor_id == target_id:
        raise PermissionError("Self-modification blocked: Cannot reactivate your own account.")

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_active = 1 WHERE person_id = ?;", (target_id,))
            if cursor.rowcount == 0:
                raise ValueError(f"User with person_id '{target_id}' not found.")
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="REACTIVATE_USER",
        details={"subject": target_id},
    )


def change_password(
    db_path: str,
    person_id: str,
    old_password: str,
    new_password: str,
) -> None:
    """Change user password, verifying current credentials first."""
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters.")

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT salt, password_hash FROM users WHERE person_id = ?;", (person_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"User '{person_id}' not found.")

            if not verify_password(old_password, row["salt"], row["password_hash"]):
                raise ValueError("Incorrect current password.")

            new_hash, new_salt = hash_password(new_password)
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = ?, must_change_password = 0
                WHERE person_id = ?;
                """,
                (new_hash, new_salt, person_id),
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=person_id,
        action="CHANGE_PASSWORD",
        details={"subject": person_id},
    )


def reset_password(
    db_path: str,
    actor_id: str,
    target_id: str,
) -> str:
    """Administrator-initiated password reset. Issues a new temporary password
    and forces a change on next login.

    CRITICAL RULE: Nobody can reset their own password this way — an admin who
    forgets their own password must use the normal change-password flow, which
    requires the current password.
    """
    if actor_id == target_id:
        raise PermissionError("Self-modification blocked: An administrator cannot reset their own password.")

    temp_password = f"temp-{secrets.token_hex(6)}"
    pwd_hash, salt = hash_password(temp_password)

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT person_id FROM users WHERE person_id = ? AND is_active = 1;", (target_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Active user with person_id '{target_id}' not found.")

            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = ?, must_change_password = 1
                WHERE person_id = ?;
                """,
                (pwd_hash, salt, target_id),
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="RESET_PASSWORD",
        details={"subject": target_id},
    )

    return temp_password


def authenticate_user(
    db_path: str,
    person_id: str,
    password: str,
) -> Optional[dict[str, Any]]:
    """Authenticate a user by person_id and password. Returns user dict or None."""
    init_users_table(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE person_id = ? AND is_active = 1;", (person_id,))
        row = cursor.fetchone()
        if not row:
            return None

        if not verify_password(password, row["salt"], row["password_hash"]):
            return None

        return {
            "person_id": row["person_id"],
            "name": row["name"],
            "job_title": row["job_title"],
            "grade": row["grade"],
            "compartments": json.loads(row["compartments"]),
            "is_admin": bool(row["is_admin"]),
            "is_active": bool(row["is_active"]),
            "must_change_password": bool(row["must_change_password"]),
        }
    finally:
        conn.close()


def get_principal(db_path: str, person_id: str) -> Optional[Principal]:
    """Resolve an authenticated Principal from the user store."""
    init_users_table(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE person_id = ? AND is_active = 1;", (person_id,))
        row = cursor.fetchone()
        if not row:
            return None

        raw_compartments = json.loads(row["compartments"])
        parsed_compartments = frozenset(Compartment(c) for c in raw_compartments)

        return Principal(
            person_id=row["person_id"],
            name=row["name"],
            job_title=row["job_title"],
            grade=row["grade"],
            compartments=parsed_compartments,
            is_admin=bool(row["is_admin"]),
        )
    finally:
        conn.close()


def list_users(db_path: str) -> list[UserSummary]:
    """List all accounts for the administrative console."""
    init_users_table(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY person_id ASC;")
        rows = cursor.fetchall()
        summaries = []
        for r in rows:
            comps = [Compartment(c) for c in json.loads(r["compartments"])]
            summaries.append(
                UserSummary(
                    person_id=r["person_id"],
                    name=r["name"],
                    job_title=r["job_title"],
                    grade=r["grade"],
                    compartments=comps,
                    is_admin=bool(r["is_admin"]),
                    is_active=bool(r["is_active"]),
                    must_change_password=bool(r["must_change_password"]),
                )
            )
        return summaries
    finally:
        conn.close()
