"""FastAPI main application entrypoint for SEVERANCE.

ZERO ACCESS DECISIONS INSIDE THIS FILE OR ANY FILE UNDER api/.
All security decisions are made exclusively in trust/labels.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env before any other project module reads os.getenv() at import or
# call time (e.g. agents/real.py's model names, AGENT_BACKEND) -- otherwise
# every setting in .env is silently ignored and callers only ever see
# hardcoded defaults.
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from contracts import Principal
from auth.deps import current_principal, get_db_path
from auth.session import COOKIE_NAME, verify_session_token
from auth.sponsors import init_grants_tables, verify_sponsors
from auth.users import get_principal, init_users_table
from ingest.seed import seed_initial_admin
from trust.conversations import init_conversations_table
from trust.ledger import init_ledger_table
from trust.reports import init_reports_table
from api.routes import admin, ask, auth, conversations, documents, grants, ledger, models

UI_DIR = Path(__file__).parent.parent / "ui"
STATIC_DIR = UI_DIR / "static"

# React SPA build output (used when ui-react/dist exists)
REACT_DIR = Path(__file__).parent.parent / "ui-react" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize database schemas and bootstrap seed on startup."""
    db_path = get_db_path()
    init_ledger_table(db_path)
    init_users_table(db_path)
    init_grants_tables(db_path)
    init_reports_table(db_path)
    init_conversations_table(db_path)

    # Seed initial administrator account if database is fresh
    seeded = seed_initial_admin(db_path)
    if seeded:
        print("[STARTUP] Fresh environment: Seeded initial administrator account.")

    # Startup sponsor verification check
    try:
        verify_sponsors(db_path)
        print("[STARTUP] All declared compartment sponsors verified successfully.")
    except Exception as exc:
        print(f"[STARTUP WARNING] Sponsor verification check: {exc}")
        print("[STARTUP NOTICE] If this is a fresh bootstrap, please log in as admin to provision the sponsor accounts.")

    # 0.0.0.0 (printed by uvicorn's own log line right after this one) is a
    # BIND address, not a URL a browser can open -- it means "listen on
    # every network interface," not "visit this address." Print the actual
    # clickable URL explicitly so that's never ambiguous.
    display_port = os.getenv("SEVERANCE_PORT", "8080")
    print("\n" + "=" * 64)
    print(" SEVERANCE startup complete.")
    print(f" Open this in your browser:  http://localhost:{display_port}")
    print(" (NOT the 0.0.0.0 address uvicorn prints below -- that's a bind")
    print("  address, not a reachable URL.)")
    print("=" * 64 + "\n")

    yield


app = FastAPI(
    title="SEVERANCE — Sovereign Air-Gapped Document Trust Workbench",
    description="Automated RTI Section 10 Severability for Mangalore Refinery and Petrochemicals Limited (MRPL)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for air-gapped web client integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Register API Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(grants.router)
app.include_router(ask.router)
app.include_router(documents.router)
app.include_router(ledger.router)
app.include_router(models.router)
app.include_router(conversations.router)


@app.get("/me")
def get_current_user_profile(
    principal: Principal = Depends(current_principal),
):
    """Retrieve the currently authenticated caller's profile."""
    return principal


# ---------------------------------------------------------------------------
# HTML UI Routes — React SPA (primary) with legacy fallback
# ---------------------------------------------------------------------------

# Mount React SPA static assets if build exists
if REACT_DIR.exists():
    _react_assets = REACT_DIR / "assets"
    if _react_assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_react_assets)), name="react-assets")


def _serve_react_index():
    """Serve the React SPA index.html for client-side routing."""
    index_path = REACT_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return None


@app.get("/")
def index(request: Request):
    """Redirect to /workbench if authenticated, otherwise to /login."""
    token = request.cookies.get(COOKIE_NAME)
    if token and verify_session_token(token):
        # If React build exists, redirect to /workbench (SPA route)
        if REACT_DIR.exists():
            return RedirectResponse(url="/workbench")
        return RedirectResponse(url="/app")
    return RedirectResponse(url="/login")


@app.get("/login")
def login_page():
    """Serve authentication UI (React SPA or legacy)."""
    react = _serve_react_index()
    if react:
        return react
    login_path = UI_DIR / "login.html"
    return FileResponse(str(login_path))


@app.get("/app")
def app_page(request: Request):
    """Serve main workbench UI (legacy)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or not verify_session_token(token):
        return RedirectResponse(url="/login")
    react = _serve_react_index()
    if react:
        return react
    app_path = UI_DIR / "app.html"
    return FileResponse(str(app_path))


# React SPA client-side routes. Some share a path with a JSON API endpoint
# (/documents, /models), so a plain @app.get route here would never be
# reached -- the API router registered above matches first, and reloading
# those pages showed raw JSON. Instead, route by intent: a browser page load
# sends Accept: text/html and gets the SPA; the frontend's fetch() calls don't,
# and fall through to the API as before.
_SPA_ROUTES = {
    "/workbench", "/sovereignty", "/knowledge-base", "/models",
    "/documents", "/generated-outputs", "/profile",
}


@app.middleware("http")
async def serve_spa_on_html_navigation(request: Request, call_next):
    if (
        request.method == "GET"
        and request.url.path in _SPA_ROUTES
        and "text/html" in request.headers.get("accept", "")
    ):
        token = request.cookies.get(COOKIE_NAME)
        if not token or not verify_session_token(token):
            return RedirectResponse(url="/login")
        react = _serve_react_index()
        if react:
            return react
        return RedirectResponse(url="/app")
    return await call_next(request)


@app.get("/admin")
def admin_page(request: Request):
    """Serve administrative console (React SPA or legacy)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or not verify_session_token(token):
        return RedirectResponse(url="/login")
    react = _serve_react_index()
    if react:
        return react
    admin_path = UI_DIR / "admin.html"
    return FileResponse(str(admin_path))

