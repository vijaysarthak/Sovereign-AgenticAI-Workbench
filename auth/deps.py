"""FastAPI dependency injection for authentication and role enforcement.

CRITICAL IDENTITY RULE:
The Principal is derived STRICTLY from the signed session cookie and SQLite user store.
It is NEVER read from request bodies or query parameters.
"""

from __future__ import annotations

import os
from typing import Callable, Optional
from fastapi import Cookie, Depends, HTTPException, Request, status
from contracts import Compartment, Principal
from auth.session import COOKIE_NAME, verify_session_token
from auth.sponsors import is_sponsor_or_delegate
from auth.users import get_principal


def get_db_path() -> str:
    """Retrieve SQLite database path from environment."""
    return os.getenv("SEVERANCE_DB_PATH", "severance.db")


def current_principal(
    request: Request,
    severance_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> Principal:
    """Resolve the authenticated Principal from the session cookie.

    Raises 401 Unauthorized if cookie is missing, forged, expired, or deactivated.
    """
    token = severance_session or request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: No active session cookie.",
        )

    person_id = verify_session_token(token)
    if not person_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid signature.",
        )

    db_path = get_db_path()
    principal = get_principal(db_path, person_id)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated.",
        )

    return principal


def require_admin(
    principal: Principal = Depends(current_principal),
) -> Principal:
    """Enforce that the caller possesses administrative authority."""
    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrative privileges required.",
        )
    return principal


def require_sponsor_of(compartment: Compartment) -> Callable[[Principal], Principal]:
    """Dependency factory enforcing that caller sponsors the specified compartment."""
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        db_path = get_db_path()
        if not is_sponsor_or_delegate(db_path, principal.person_id, compartment):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: You do not sponsor compartment '{compartment.value}'.",
            )
        return principal
    return dependency
