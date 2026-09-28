"""Administrative endpoints for account provisioning, grades, and compartment assignment.

ZERO ACCESS DECISIONS INSIDE.
Admins can set pay grades and assign any compartment to another user
(decided in auth/sponsors.py's admin_set_compartments).
Nobody can modify their own grade or compartments.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from contracts import CreateUserRequest, Principal, SetCompartmentsRequest, UpdateGradeRequest, UserSummary
from auth.deps import current_principal, get_db_path, require_admin
from auth.sponsors import admin_set_compartments, load_compartment_config
from auth.users import create_user, deactivate_user, list_users, reactivate_user, reset_password, update_grade

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.post("/users", status_code=status.HTTP_201_CREATED)
def provision_user(
    payload: CreateUserRequest,
    admin: Principal = Depends(require_admin),
):
    """Provision a new employee record and generate a temporary password."""
    db_path = get_db_path()
    try:
        user_record, temp_pwd = create_user(
            db_path=db_path,
            actor_id=admin.person_id,
            person_id=payload.person_id,
            name=payload.name,
            job_title=payload.job_title,
            grade=payload.grade,
            is_admin=False,
            must_change_password=True,
        )
        return {
            "user": user_record,
            "temporary_password": temp_pwd,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/users", response_model=list[UserSummary])
def get_users(
    admin: Principal = Depends(require_admin),
):
    """List all accounts for the administrative console."""
    db_path = get_db_path()
    return list_users(db_path)


@router.patch("/users/{target_id}/grade")
def set_grade(
    target_id: str,
    payload: UpdateGradeRequest,
    admin: Principal = Depends(require_admin),
):
    """Update an employee's pay grade. Self-modification is strictly blocked."""
    db_path = get_db_path()
    try:
        update_grade(
            db_path=db_path,
            actor_id=admin.person_id,
            target_id=target_id,
            new_grade=payload.grade,
        )
        return {
            "status": "grade_updated",
            "person_id": target_id,
            "new_grade": payload.grade,
        }
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/users/{target_id}/reset-password")
def reset_user_password(
    target_id: str,
    admin: Principal = Depends(require_admin),
):
    """Issue a new temporary password for an account whose credentials were lost.
    Self-reset is strictly blocked."""
    db_path = get_db_path()
    try:
        temp_pwd = reset_password(
            db_path=db_path,
            actor_id=admin.person_id,
            target_id=target_id,
        )
        return {"status": "password_reset", "person_id": target_id, "temporary_password": temp_pwd}
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/users/{target_id}/deactivate")
def deactivate(
    target_id: str,
    admin: Principal = Depends(require_admin),
):
    """Deactivate an employee account. Self-deactivation is strictly blocked."""
    db_path = get_db_path()
    try:
        deactivate_user(
            db_path=db_path,
            actor_id=admin.person_id,
            target_id=target_id,
        )
        return {"status": "user_deactivated", "person_id": target_id}
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/users/{target_id}/reactivate")
def reactivate(
    target_id: str,
    admin: Principal = Depends(require_admin),
):
    """Reactivate a previously deactivated employee account. Self-reactivation is strictly blocked."""
    db_path = get_db_path()
    try:
        reactivate_user(
            db_path=db_path,
            actor_id=admin.person_id,
            target_id=target_id,
        )
        return {"status": "user_reactivated", "person_id": target_id}
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/compartments")
def list_compartments(
    admin: Principal = Depends(require_admin),
):
    """List every compartment with its description and designated sponsor."""
    config = load_compartment_config()
    return [
        {"id": comp_id, "description": info.get("description", ""), "sponsor": info.get("sponsor")}
        for comp_id, info in config.items()
    ]


@router.put("/users/{target_id}/compartments")
def set_user_compartments(
    target_id: str,
    payload: SetCompartmentsRequest,
    admin: Principal = Depends(require_admin),
):
    """Set another user's full compartment set. Self-assignment is strictly blocked."""
    db_path = get_db_path()
    try:
        result = admin_set_compartments(
            db_path=db_path,
            actor_id=admin.person_id,
            target_id=target_id,
            compartments=payload.compartments,
        )
        return {"status": "compartments_updated", "person_id": target_id, **result}
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
