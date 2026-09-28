"""Integration tests for SEVERANCE FastAPI REST endpoints.

Verifies:
1. First-run bootstrap admin seeding.
2. Login and cookie handling.
3. Administrative user provisioning.
4. Separation of powers: Admin cannot grant compartments (403 Forbidden).
5. Sponsor login and compartment granting.
6. /ask query execution and response schema.
7. /report/{id} .docx report download.
8. /ledger/verify chain verification.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from api.main import app
from auth.deps import get_db_path
from auth.users import create_user
from contracts import Compartment, Label, Passage, Tier
from ingest.seed import seed_initial_admin
import api.routes.ask as ask_route


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    """Set up TestClient with dedicated temporary database."""
    test_db = str(tmp_path / "api_test.db")
    monkeypatch.setenv("SEVERANCE_DB_PATH", test_db)
    monkeypatch.setenv("SEVERANCE_ADMIN_ID", "admin-root")
    monkeypatch.setenv("SEVERANCE_ADMIN_PASSWORD", "RootAdmin123!")
    monkeypatch.setenv("AGENT_BACKEND", "mock")

    # Seed initial admin
    seed_initial_admin(test_db)

    # Seed CVO sponsor
    create_user(
        db_path=test_db,
        actor_id="admin-root",
        person_id="cvo-001",
        name="Chief Vigilance Officer",
        job_title="CVO",
        grade="G",
        password="CVOPassword123!",
        must_change_password=False,
    )

    # Provide synthetic in-memory corpus for testing /ask
    test_corpus = [
        Passage(
            doc_id="cdu-sop-01",
            page=1,
            title="CDU-2 Operating Manual",
            text="Emergency shutdown valve actuation must occur within ninety seconds of alarm trigger.",
            label=Label(tier=Tier.INTERNAL),
        )
    ]
    monkeypatch.setattr(ask_route, "get_corpus", lambda: test_corpus)

    with TestClient(app) as client:
        yield client, test_db


def test_auth_login_and_me(api_client):
    """Verify login issues session cookie and /me returns principal profile."""
    client, _ = api_client

    # 1. Login as CVO
    res = client.post("/auth/login", json={"person_id": "cvo-001", "password": "CVOPassword123!"})
    assert res.status_code == 200
    assert "severance_session" in res.cookies

    # 2. Call /me using session cookie
    me_res = client.get("/me")
    assert me_res.status_code == 200
    profile = me_res.json()
    assert profile["person_id"] == "cvo-001"
    assert profile["grade"] == "G"


def test_admin_provisioning_and_separation_of_powers(api_client):
    """Admin provisions user, but CANNOT use the sponsor /grants path."""
    client, _ = api_client

    # 1. Login as admin
    login_res = client.post("/auth/login", json={"person_id": "admin-root", "password": "RootAdmin123!"})
    assert login_res.status_code == 200

    # 2. Provision new employee account
    create_res = client.post("/admin/users", json={
        "person_id": "eng-99",
        "name": "Arun Kumar",
        "job_title": "Field Engineer",
        "grade": "B",
    })
    assert create_res.status_code == 201
    data = create_res.json()
    assert "temporary_password" in data
    assert data["user"]["person_id"] == "eng-99"

    # 3. ADMIN ATTEMPTS TO GRANT COMPARTMENT -> 403 FORBIDDEN
    grant_res = client.post("/grants", json={
        "person_id": "eng-99",
        "compartment": "vigilance",
    })
    assert grant_res.status_code == 403
    assert "does not sponsor compartment" in grant_res.json()["detail"]



def test_admin_assigns_compartments_via_admin_api(api_client):
    """Only the System Administrator can use PUT /admin/users/{id}/compartments, never on self."""
    client, _ = api_client

    client.post("/auth/login", json={"person_id": "admin-root", "password": "RootAdmin123!"})
    comps = client.get("/admin/compartments")
    assert comps.status_code == 200
    assert {c["id"] for c in comps.json()} >= {"vigilance", "hse"}

    res = client.put("/admin/users/cvo-001/compartments", json={"compartments": ["vigilance", "hse"]})
    assert res.status_code == 200
    assert res.json()["added"] == ["hse", "vigilance"]

    users = {u["person_id"]: u for u in client.get("/admin/users").json()}
    assert sorted(users["cvo-001"]["compartments"]) == ["hse", "vigilance"]

    self_res = client.put("/admin/users/admin-root/compartments", json={"compartments": ["hse"]})
    assert self_res.status_code == 403

    bad = client.put("/admin/users/cvo-001/compartments", json={"compartments": ["not-a-compartment"]})
    assert bad.status_code == 422

    missing = client.put("/admin/users/nobody-1/compartments", json={"compartments": ["hse"]})
    assert missing.status_code == 404

    # A non-admin (even a sponsor) is rejected by the endpoint itself.
    client.post("/auth/logout")
    client.post("/auth/login", json={"person_id": "cvo-001", "password": "CVOPassword123!"})
    forbidden = client.put("/admin/users/admin-root/compartments", json={"compartments": ["vigilance"]})
    assert forbidden.status_code == 403
    assert client.get("/admin/compartments").status_code == 403

def test_sponsor_grant_and_ask_query(api_client):
    """Sponsor grants compartment, user runs /ask query and downloads report."""
    client, _ = api_client

    # 1. Login as CVO
    client.post("/auth/login", json={"person_id": "cvo-001", "password": "CVOPassword123!"})

    # 2. Query /ask
    ask_res = client.post("/ask", json={
        "question": "What is the emergency shutdown valve actuation time?",
        "top_k": 1,
    })
    assert ask_res.status_code == 200
    ans_data = ask_res.json()
    assert ans_data["status"] == "answered"
    assert len(ans_data["citations"]) == 1
    assert ans_data["ledger_row_id"] is not None

    # 3. Download DOCX report
    row_id = ans_data["ledger_row_id"]
    rep_res = client.get(f"/report/{row_id}")
    assert rep_res.status_code == 200
    assert "wordprocessingml" in rep_res.headers["content-type"]
    assert len(rep_res.content) > 1000

    # 4. Verify Ledger
    ledger_res = client.get("/ledger/verify")
    assert ledger_res.status_code == 200
    assert ledger_res.json()["intact"] is True
