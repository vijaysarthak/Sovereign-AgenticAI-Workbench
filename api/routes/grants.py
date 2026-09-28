"""Compartment grant and revocation endpoints.

ZERO ACCESS DECISIONS INSIDE.
All authority is delegated to auth/sponsors.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from contracts import GrantCompartmentRequest, Principal, RevokeCompartmentRequest
from auth.deps import current_principal, get_db_path
from auth.sponsors import get_sponsored_compartments, grant_compartment, revoke_compartment

router = APIRouter(prefix="/grants", tags=["Compartment Grants"])


@router.post("")
def add_compartment_grant(
    payload: GrantCompartmentRequest,
    principal: Principal = Depends(current_principal),
):
    """Grant a compartment clearance. Caller must be the designated sponsor."""
    db_path = get_db_path()
    try:
        grant_compartment(
            db_path=db_path,
            actor_id=principal.person_id,
            target_id=payload.person_id,
            compartment=payload.compartment,
        )
        return {
            "status": "compartment_granted",
            "actor": principal.person_id,
            "subject": payload.person_id,
            "compartment": payload.compartment.value,
        }
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("")
def remove_compartment_grant(
    payload: RevokeCompartmentRequest,
    principal: Principal = Depends(current_principal),
):
    """Revoke a compartment clearance. Caller must be the designated sponsor."""
    db_path = get_db_path()
    try:
        revoke_compartment(
            db_path=db_path,
            actor_id=principal.person_id,
            target_id=payload.person_id,
            compartment=payload.compartment,
        )
        return {
            "status": "compartment_revoked",
            "actor": principal.person_id,
            "subject": payload.person_id,
            "compartment": payload.compartment.value,
        }
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/mine")
def get_my_sponsored_compartments(
    principal: Principal = Depends(current_principal),
):
    """List compartments that the caller is authorized to grant or revoke."""
    db_path = get_db_path()
    comps = get_sponsored_compartments(db_path, principal.person_id)
    return {"sponsored_compartments": [c.value for c in comps]}
