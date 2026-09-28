"""Corpus exploration endpoints.

ZERO ACCESS DECISIONS INSIDE.
Per-user readability is evaluated strictly by trust/labels.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, Depends
from contracts import Compartment, Label, Principal, Tier
from auth.deps import current_principal
from trust.labels import can_read, denial_reason

router = APIRouter(prefix="/documents", tags=["Corpus"])

MANIFEST_PATH = Path(__file__).parent.parent.parent / "corpus" / "manifest.json"


@router.get("")
def list_documents(
    principal: Principal = Depends(current_principal),
):
    """List all documents in the corpus with per-user readability indicators."""
    if not MANIFEST_PATH.exists():
        return []

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    results = []
    for entry in manifest:
        label_data = entry.get("label", {})
        tier = Tier(label_data.get("tier", Tier.INTERNAL.value))
        comps = frozenset(Compartment(c) for c in label_data.get("compartments", []))
        label = Label(tier=tier, compartments=comps)

        # Pure evaluation via trust/labels.py
        is_readable = can_read(principal, label)
        reason = None if is_readable else denial_reason(principal, label)

        results.append({
            "doc_id": entry["doc_id"],
            "title": entry.get("title", entry["doc_id"]),
            "source": entry.get("source", "MRPL Internal"),
            "label": {
                "tier": tier.value,
                "compartments": [c.value for c in comps],
            },
            "readable": is_readable,
            "denial_reason": reason,
        })

    return results
