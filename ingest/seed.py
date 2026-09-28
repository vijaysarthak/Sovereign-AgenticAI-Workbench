"""Bootstrap initialization service for initial administrative account.

Creates the initial admin account on first startup if no users exist.
"""

from __future__ import annotations

import os
from typing import Optional
from auth.users import create_user, get_db_connection, init_users_table
from trust.ledger import log as ledger_log


def seed_initial_admin(db_path: Optional[str] = None) -> bool:
    """Check if any users exist; if not, seed the initial administrator from environment variables."""
    actual_db = db_path or os.getenv("SEVERANCE_DB_PATH", "severance.db")
    init_users_table(actual_db)

    conn = get_db_connection(actual_db)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM users;")
        count = cursor.fetchone()["cnt"]
        if count > 0:
            return False  # Already seeded
    finally:
        conn.close()

    admin_id = os.getenv("SEVERANCE_ADMIN_ID", "admin-001")
    admin_password = os.getenv("SEVERANCE_ADMIN_PASSWORD", "InitialAdminPassword123!")

    create_user(
        db_path=actual_db,
        actor_id="system_bootstrap",
        person_id=admin_id,
        name="System Administrator",
        job_title="HR / Systems Administrator",
        grade="E",  # DGM rank
        is_admin=True,
        password=admin_password,
        must_change_password=True,
    )

    ledger_log(
        db_path=actual_db,
        actor="system_bootstrap",
        action="BOOTSTRAP_INITIAL_ADMIN",
        details={"admin_id": admin_id},
    )
    return True
