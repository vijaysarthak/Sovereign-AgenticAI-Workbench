"""Deterministic two-axis access control and classification inheritance.

NON-NEGOTIABLE DESIGN PRINCIPLE:
Access decisions live in exactly this file and nowhere else.
The model proposes, the code disposes.

This module is 100% pure:
- No database
- No network
- No clock
- No randomness
- Fails closed on any unexpected, malformed, or missing input.
"""

from __future__ import annotations

from typing import Sequence
from contracts import Compartment, Label, Principal, Tier


# ---------------------------------------------------------------------------
# Axis 1: Hierarchical Rank Ladder (MRPL Grade Structure)
# ---------------------------------------------------------------------------
# Officers: Grade A through Grade I
# Non-Management: S1-S4 (Staff/Support), TS1-TS6 (Technical Staff), JM1-JM6 (Junior Mgmt)
RANK: dict[str, int] = {
    # Non-Management Staff & Support
    "S1": 1,
    "S2": 2,
    "S3": 3,
    "S4": 4,
    # Technical Staff
    "TS1": 1,
    "TS2": 2,
    "TS3": 3,
    "TS4": 4,
    "TS5": 5,
    "TS6": 6,
    # Junior Management
    "JM1": 4,
    "JM2": 5,
    "JM3": 6,
    "JM4": 6,
    "JM5": 6,
    "JM6": 6,
    # Management & Executive Officers
    "A": 7,    # Executive / Assistant Manager
    "B": 8,    # Manager
    "C": 9,    # Senior Manager
    "D": 10,   # Chief Manager
    "E": 11,   # Deputy General Manager (DGM)
    "F": 12,   # General Manager (GM)
    "G": 13,   # Group General Manager (GGM)
    "H": 14,   # Executive Director (ED)
    "I": 15,   # Director / C&MD
}

# Minimum hierarchical rank required to access each classification tier
TIER_FLOOR: dict[Tier, int] = {
    Tier.PUBLIC: 0,         # Accessible to all personnel
    Tier.INTERNAL: 1,       # Accessible to S1/TS1 and above (rank >= 1)
    Tier.CONFIDENTIAL: 7,   # Accessible to Officer Grade A and above (rank >= 7)
    Tier.SECRET: 11,        # Accessible to Officer Grade E (DGM) and above (rank >= 11)
}

# Ordered sensitivity ranking of tiers for classification inheritance
TIER_ORDER: dict[Tier, int] = {
    Tier.PUBLIC: 0,
    Tier.INTERNAL: 1,
    Tier.CONFIDENTIAL: 2,
    Tier.SECRET: 3,
}

REVERSE_TIER_ORDER: dict[int, Tier] = {v: k for k, v in TIER_ORDER.items()}


# ---------------------------------------------------------------------------
# Access Control Gate: Pure Two-Axis Evaluation
# ---------------------------------------------------------------------------

def can_read(principal: Principal, label: Label) -> bool:
    """Evaluate whether an authenticated principal may read a resource with the given label.

    Rules:
    1. Axis 1 (Hierarchical Rank): Principal's grade rank must be >= TIER_FLOOR[label.tier].
    2. Axis 2 (Compartments): label.compartments must be a subset of principal.compartments.
    3. Both axes MUST pass independently. High rank NEVER implies compartment access.
    4. Fails closed: any unknown grade, unknown tier, or invalid data returns False.
    """
    try:
        if not isinstance(principal, Principal) or not isinstance(label, Label):
            return False

        # Axis 1: Rank check
        principal_rank = RANK.get(principal.grade)
        if principal_rank is None:
            return False

        required_floor = TIER_FLOOR.get(label.tier)
        if required_floor is None:
            return False

        if principal_rank < required_floor:
            return False

        # Axis 2: Compartment check (unranked, independent sets)
        if not label.compartments.issubset(principal.compartments):
            return False

        return True
    except Exception:
        # Absolute fail-closed behavior
        return False


def denial_reason(principal: Principal, label: Label) -> str:
    """Generate a precise, deterministic explanation of why access was withheld.

    Note: This explains reasons based on labels only, without leaking document content.
    """
    try:
        principal_rank = RANK.get(principal.grade)
        if principal_rank is None:
            return f"Invalid or unrecognized principal grade '{principal.grade}'."

        required_floor = TIER_FLOOR.get(label.tier)
        if required_floor is None:
            return f"Invalid or unrecognized classification tier '{label.tier}'."

        rank_failed = principal_rank < required_floor
        missing_compartments = label.compartments - principal.compartments

        reasons = []
        if rank_failed:
            reasons.append(
                f"Insufficient rank: Grade '{principal.grade}' (rank {principal_rank}) "
                f"does not meet minimum rank floor {required_floor} required for tier '{label.tier.value}'"
            )

        if missing_compartments:
            missing_names = ", ".join(sorted(c.value for c in missing_compartments))
            reasons.append(f"Missing required compartment(s): {missing_names}")

        if reasons:
            return "; ".join(reasons)

        return ""
    except Exception as exc:
        return f"Access denied due to evaluation error: {str(exc)}"


# ---------------------------------------------------------------------------
# Classification Inheritance
# ---------------------------------------------------------------------------

def inherit_label(labels: Sequence[Label]) -> Label:
    """Compute the inherited security classification label for a synthesized answer.

    Rule: An answer inherits:
    - The HIGHEST tier among all passages placed in the prompt (not just the ones cited).
    - The UNION of all compartments of all passages placed in the prompt.

    Rationale: Over-classifying inconveniences someone; under-classifying leaks secrets.
    """
    if not labels:
        return Label(tier=Tier.PUBLIC, compartments=frozenset())

    max_tier_rank = 0
    all_compartments: set[Compartment] = set()

    for lbl in labels:
        if isinstance(lbl, Label):
            tier_val = TIER_ORDER.get(lbl.tier, 0)
            if tier_val > max_tier_rank:
                max_tier_rank = tier_val
            all_compartments.update(lbl.compartments)

    highest_tier = REVERSE_TIER_ORDER.get(max_tier_rank, Tier.PUBLIC)
    return Label(tier=highest_tier, compartments=frozenset(all_compartments))
