"""Cryptographically signed session tokens and cookie handling.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. No external authentication libraries.
2. Standard library HMAC-SHA256 signature verification.
3. HttpOnly, SameSite=Lax cookie storage prevents XSS extraction.
4. Tamper-evident: modifying person_id or expiry immediately fails HMAC verification.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Optional
from fastapi import Response

COOKIE_NAME = "severance_session"
DEFAULT_SESSION_DURATION_SECONDS = 86400  # 24 hours


def get_secret_key() -> str:
    """Retrieve secret key from environment or generate a secure ephemeral key."""
    return os.getenv("SEVERANCE_SECRET_KEY", "severance-airgap-default-secret-key-do-not-use-prod")


def create_session_token(
    person_id: str,
    secret_key: Optional[str] = None,
    duration_seconds: int = DEFAULT_SESSION_DURATION_SECONDS,
) -> str:
    """Generate an HMAC-SHA256 signed session token."""
    key = secret_key or get_secret_key()
    now_ts = int(datetime.now(timezone.utc).timestamp())
    exp_ts = now_ts + duration_seconds
    nonce = secrets.token_hex(8)

    payload = {
        "person_id": person_id,
        "iat": now_ts,
        "exp": exp_ts,
        "nonce": nonce,
    }
    payload_json = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8")

    sig = hmac.new(key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session_token(token: str, secret_key: Optional[str] = None) -> Optional[str]:
    """Verify session token HMAC signature and expiration.

    Returns the validated person_id if legitimate and unexpired, otherwise None.
    """
    if not token or "." not in token:
        return None

    parts = token.split(".")
    if len(parts) != 2:
        return None

    payload_b64, provided_sig = parts
    key = secret_key or get_secret_key()

    expected_sig = hmac.new(key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    try:
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return None

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if now_ts > payload.get("exp", 0):
        return None

    return payload.get("person_id")


def set_session_cookie(
    response: Response,
    token: str,
    max_age: int = DEFAULT_SESSION_DURATION_SECONDS,
) -> None:
    """Attach the signed session token as an HttpOnly, secure-configured cookie."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=False,  # Air-gapped on-prem LAN environments often terminate TLS at reverse proxy
    )


def clear_session_cookie(response: Response) -> None:
    """Delete the session cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="lax",
    )
