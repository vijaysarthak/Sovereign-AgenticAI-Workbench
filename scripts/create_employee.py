"""CLI utility to provision a regular (non-admin) employee account directly
against the local database, without going through the running API.

Useful for bootstrapping compartment sponsor accounts (cvo-001, safety-001,
legal-001, comm-001, tech-001 -- see config/compartments.json) and for
creating demo/test principals, without needing a browser session or an
admin API call.

Usage:
  python scripts/create_employee.py --id safety-001 --name "Head of Safety" \
      --job-title "Head of Safety" --grade C --password "SafetyPass123!"
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.users import create_user
from trust.ledger import log as ledger_log


def main():
    parser = argparse.ArgumentParser(description="Provision an employee account directly in the database.")
    parser.add_argument("--id", required=True, help="New employee person_id (e.g. safety-001)")
    parser.add_argument("--name", required=True, help="Full name")
    parser.add_argument("--job-title", required=True, help="Job title / designation")
    parser.add_argument("--grade", required=True, help="MRPL grade (e.g. A, B, C, S1, JM2)")
    parser.add_argument("--password", required=True, help="Initial password you choose")
    parser.add_argument("--admin", action="store_true", help="Grant admin privileges (default: off)")
    parser.add_argument("--db-path", default=None, help="Database path override")

    args = parser.parse_args()
    db_path = args.db_path or os.getenv("SEVERANCE_DB_PATH", "severance.db")

    try:
        user, _ = create_user(
            db_path=db_path,
            actor_id="manual_provision_script",
            person_id=args.id,
            name=args.name,
            job_title=args.job_title,
            grade=args.grade,
            is_admin=args.admin,
            password=args.password,
            must_change_password=True,
        )
        ledger_log(
            db_path=db_path,
            actor="manual_provision_script",
            action="MANUAL_EMPLOYEE_PROVISIONED",
            details={"person_id": args.id, "grade": args.grade, "is_admin": args.admin},
        )
        print(f"SUCCESS: '{args.id}' created (grade={user['grade']}, admin={user['is_admin']}).")
        print(f"Login with person_id='{args.id}' and the password you supplied.")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()