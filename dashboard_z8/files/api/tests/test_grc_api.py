"""Tests for the GRC endpoints. Run from the api folder:  pip install pytest httpx  then  python -m pytest tests"""
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Run against a temporary copy of the GRC data so tests never change the real files."""
    src = Path(__file__).resolve().parent.parent / "app" / "grc"
    shutil.copytree(src, tmp_path / "grc")
    monkeypatch.setenv("GRC_DIR", str(tmp_path / "grc"))
    for name in ("app.routers.grc", "compliance", "evidence", "policies", "control_library"):
        sys.modules.pop(name, None)
    from app.main import app
    return TestClient(app)


def login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "sentinel123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_requires_login(client):
    assert client.get("/api/grc/compliance").status_code == 401


def test_client_role_is_forbidden(client):
    assert client.get("/api/grc/compliance", headers=login(client, "client")).status_code == 403


def test_compliance_overview(client):
    body = client.get("/api/grc/compliance", headers=login(client, "auditor")).json()
    assert body["total_controls"] == 362
    assert {f["id"] for f in body["frameworks"]} == {"NIST_CSF_2.0", "ISO27001_2022", "CIS_V8_1", "OWASP_TOP10_2025"}
    assert all("functions" in f for f in body["frameworks"]) and body["gaps"]


def test_controls_are_paged_and_filterable(client):
    h = login(client, "analyst")
    page = client.get("/api/grc/controls?page_size=10", headers=h).json()
    assert page["total"] == 362 and len(page["items"]) == 10
    owasp = client.get("/api/grc/controls?framework=OWASP_TOP10_2025", headers=h).json()
    assert owasp["total"] == 10
    found = client.get("/api/grc/controls?q=ISO-8.15", headers=h).json()
    assert found["total"] == 1 and found["items"][0]["id"] == "ISO-8.15"
    assert client.get("/api/grc/controls?status=Implemented", headers=h).json()["total"] == 0


def test_policies_list(client):
    body = client.get("/api/grc/policies", headers=login(client, "auditor")).json()
    assert len(body["policies"]) == 3
    assert body["effective_parameters"]["web_bruteforce_response"]["bruteforce_block_ttl_minutes"] == 1440


def test_auditor_cannot_write_but_analyst_can(client):
    assert client.post("/api/grc/policies/POL-001/acknowledge", headers=login(client, "auditor")).status_code == 403
    r = client.post("/api/grc/policies/POL-001/acknowledge", headers=login(client, "analyst"))
    assert r.status_code == 200 and r.json()["acknowledgements"][0]["user"] == "analyst"
    assert client.post("/api/grc/policies/NOPE/acknowledge", headers=login(client, "analyst")).status_code == 404


def test_collecting_evidence_updates_the_controls(client):
    h = login(client, "analyst")
    before = client.get("/api/grc/compliance", headers=h).json()["evidence"]
    assert before["controls_fresh"] == 0
    assert client.post("/api/grc/evidence/collect", headers=h).json()["items"] == 6
    after = client.get("/api/grc/compliance", headers=h).json()["evidence"]
    assert after["controls_fresh"] == 19
    row = client.get("/api/grc/controls?q=ISO-8.15", headers=h).json()["items"][0]
    assert row["evidence"]["state"] == "fresh"
