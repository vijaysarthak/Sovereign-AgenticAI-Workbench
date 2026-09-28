"""CLI utility to create an administrator account gated by a bootstrap secret code.

Usage:
  python scripts/create_admin.py --code mrpl-sih-2026-bootstrap-key --id admin-002 --name "Second Admin" --grade E --password "Pass1234!"
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.users import create_user
from trust.ledger import log as ledger_log


def main():
    parser = argparse.ArgumentParser(description="Create an administrative account gated by bootstrap code.")
    parser.add_argument("--code", required=True, help="Bootstrap authorization code matching SEVERANCE_BOOTSTRAP_CODE")
    parser.add_argument("--id", required=True, help="New admin person_id")
    parser.add_argument("--name", required=True, help="Administrator full name")
    parser.add_argument("--job-title", default="Systems Administrator", help="Administrator job title")
    parser.add_argument("--grade", default="E", help="MRPL grade (default: E)")
    parser.add_argument("--password", required=True, help="Initial password")
    parser.add_argument("--db-path", default=None, help="Database path override")

    args = parser.parse_args()

    expected_code = os.getenv("SEVERANCE_BOOTSTRAP_CODE", "mrpl-sih-2026-bootstrap-key")
    if args.code != expected_code:
        print("ERROR: Invalid bootstrap code. Authorization denied.", file=sys.stderr)
        sys.exit(1)

    db_path = args.db_path or os.getenv("SEVERANCE_DB_PATH", "severance.db")

    try:
        user, _ = create_user(
            db_path=db_path,
            actor_id="bootstrap_script",
            person_id=args.id,
            name=args.name,
            job_title=args.job_title,
            grade=args.grade,
            is_admin=True,
            password=args.password,
            must_change_password=True,
        )
        ledger_log(
            db_path=db_path,
            actor="bootstrap_script",
            action="BOOTSTRAP_CLI_ADMIN_CREATED",
            details={"admin_id": args.id},
        )
        print(f"SUCCESS: Administrator account '{args.id}' successfully provisioned.")
    except Exception as exc:
        print(f"ERROR: Failed to create admin: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
