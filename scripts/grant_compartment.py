"""CLI utility to grant a compartment directly against the local database,
bypassing the running API/browser session -- enforces the exact same rules
as the live grant endpoint (auth/sponsors.py): the actor must be the
compartment's sponsor or an authorized delegate, and cannot grant to themselves.

Usage:
  python scripts/grant_compartment.py --actor cvo-001 --target emp-meera --compartment vigilance
  python scripts/grant_compartment.py --actor safety-001 --delegate-to admin-001 --compartment hse
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auth.sponsors import delegate_sponsor, grant_compartment, init_grants_tables
from contracts import Compartment


def main():
    parser = argparse.ArgumentParser(description="Grant a compartment, or delegate granting authority.")
    parser.add_argument("--actor", required=True, help="person_id performing the action (must be the sponsor/delegate)")
    parser.add_argument("--compartment", required=True, choices=[c.value for c in Compartment])
    parser.add_argument("--target", help="person_id to grant the compartment to")
    parser.add_argument("--delegate-to", help="person_id to delegate granting authority to, instead of granting directly")
    parser.add_argument("--db-path", default=None)

    args = parser.parse_args()
    db_path = args.db_path or os.getenv("SEVERANCE_DB_PATH", "severance.db")
    comp = Compartment(args.compartment)
    init_grants_tables(db_path)

    try:
        if args.delegate_to:
            delegate_sponsor(db_path, actor_id=args.actor, delegate_id=args.delegate_to, compartment=comp)
            print(f"SUCCESS: '{args.actor}' delegated '{comp.value}' granting authority to '{args.delegate_to}'.")
        elif args.target:
            grant_compartment(db_path, actor_id=args.actor, target_id=args.target, compartment=comp)
            print(f"SUCCESS: '{args.actor}' granted '{comp.value}' to '{args.target}'.")
        else:
            print("ERROR: specify either --target (to grant) or --delegate-to (to delegate).", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()