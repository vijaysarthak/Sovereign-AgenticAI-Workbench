"""Authentication endpoints for session management.

ZERO ACCESS DECISIONS INSIDE.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from contracts import ChangePasswordRequest, LoginRequest, Principal
from auth.deps import current_principal, get_db_path
from auth.session import clear_session_cookie, create_session_token, set_session_cookie
from auth.users import authenticate_user, change_password

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    """Establish authenticated session and issue signed HttpOnly cookie."""
    db_path = get_db_path()
    user = authenticate_user(db_path, payload.person_id, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee ID or password.",
        )

    token = create_session_token(user["person_id"])
    set_session_cookie(response, token)

    return {
        "status": "success",
        "principal": {
            "person_id": user["person_id"],
            "name": user["name"],
            "job_title": user["job_title"],
            "grade": user["grade"],
            "compartments": user["compartments"],
            "is_admin": user["is_admin"],
        },
        "must_change_password": user["must_change_password"],
    }


@router.post("/logout")
def logout(response: Response):
    """Clear active session cookie. Conversation history is durably stored
    per person (see trust/conversations.py), so there is nothing transient
    to clear here -- it's simply there again on the next login."""
    clear_session_cookie(response)
    return {"status": "logged_out"}


@router.post("/change-password")
def update_password(
    payload: ChangePasswordRequest,
    principal: Principal = Depends(current_principal),
):
    """Update password, mandatory for accounts created with temporary credentials."""
    db_path = get_db_path()
    try:
        change_password(
            db_path=db_path,
            person_id=principal.person_id,
            old_password=payload.old_password,
            new_password=payload.new_password,
        )
        return {"status": "password_updated"}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
