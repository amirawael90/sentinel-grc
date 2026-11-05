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
    for name in list(sys.modules):  # forget the app and the GRC modules so each test starts clean
        if name == "app" or name.startswith("app.") or name in (
                "compliance", "evidence", "policies", "control_library", "audit_log", "reports", "remediation"):
            sys.modules.pop(name)
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


# ---------------- Z9: evidence browser, audit log, reports ----------------
def test_evidence_browser_filters_and_verify(client):
    h = login(client, "analyst")
    client.post("/api/grc/evidence/collect", headers=h)
    a = login(client, "auditor")
    page = client.get("/api/grc/evidence", headers=a).json()
    assert page["total"] == 6 and "audit-logs" in page["sources"]
    assert all(len(i["sha256"]) == 64 and i["state"] == "fresh" for i in page["items"])
    assert client.get("/api/grc/evidence?control=ISO-8.15", headers=a).json()["total"] == 1
    assert client.get("/api/grc/evidence?source=detection-rules", headers=a).json()["total"] == 2
    assert client.get("/api/grc/evidence?state=stale", headers=a).json()["total"] == 0
    assert client.get("/api/grc/evidence?since=2999-01-01", headers=a).json()["total"] == 0
    assert client.get("/api/grc/evidence/verify", headers=a).json()["ok"] is True


def test_evidence_verify_detects_a_changed_file(client, tmp_path):
    h = login(client, "analyst")
    client.post("/api/grc/evidence/collect", headers=h)
    f = tmp_path / "grc" / "sample_sources" / "config" / "haproxy.cfg"
    f.write_text(f.read_text() + "tampered")
    result = client.get("/api/grc/evidence/verify", headers=login(client, "auditor")).json()
    assert result["ok"] is False and "haproxy.cfg" in result["problems"][0]


def test_audit_log_search_verify_and_export(client):
    a = login(client, "auditor")
    page = client.get("/api/grc/audit?page_size=5", headers=a).json()
    assert page["total"] == 12 and page["has_sample"] and page["items"][0]["seq"] == 12
    assert client.get("/api/grc/audit?actor=executor", headers=a).json()["total"] == 3
    assert client.get("/api/grc/audit?result=rejected", headers=a).json()["total"] == 1
    assert client.get("/api/grc/audit/verify", headers=a).json()["ok"] is True
    csv = client.get("/api/grc/audit/export?actor=executor", headers=a)
    assert csv.headers["content-type"].startswith("text/csv") and csv.text.count("executor") >= 3
    after = client.get("/api/grc/audit?action=export_audit", headers=a).json()
    assert after["total"] == 2 and after["items"][0]["actor"] == "auditor" and after["items"][0]["sample"] is False


def test_dashboard_actions_are_written_to_the_audit_log(client):
    h = login(client, "analyst")
    client.post("/api/grc/policies/POL-001/acknowledge", headers=h)
    client.post("/api/grc/evidence/collect", headers=h)
    items = client.get("/api/grc/audit?actor=analyst&page_size=50", headers=h).json()["items"]
    assert {"acknowledge_policy", "collect_evidence"} <= {i["action"] for i in items}
    assert client.get("/api/grc/audit/verify", headers=h).json()["ok"] is True


def test_audit_tampering_is_reported(client, tmp_path):
    import json
    f = tmp_path / "grc" / "data" / "audit" / "audit.jsonl"
    lines = [json.loads(x) for x in f.read_text().splitlines()]
    lines[4]["target"] = "198.51.100.99"
    f.write_text("".join(json.dumps(x) + "\n" for x in lines))
    result = client.get("/api/grc/audit/verify", headers=login(client, "auditor")).json()
    assert result["ok"] is False and result["broken_at"] == 5


def test_audit_import_needs_the_environment_variable(client, tmp_path, monkeypatch):
    h = login(client, "analyst")
    monkeypatch.delenv("ACTION_AUDIT_FILE", raising=False)
    assert client.post("/api/grc/audit/import", headers=h).status_code == 400
    src = tmp_path / "actions.jsonl"
    src.write_text('{"request": {"actor": "agent", "tool": "block_ip", "args": {"ip": "1.2.3.4"}, "incident_id": "I", "gate": "G2", '
                   '"correlation_id": "c"}, "result": {"action_id": "a1", "status": "success", "correlation_id": "c"}}\n')
    monkeypatch.setenv("ACTION_AUDIT_FILE", str(src))
    assert client.post("/api/grc/audit/import", headers=h).json()["added"] == 1
    assert client.post("/api/grc/audit/import", headers=h).json()["added"] == 0
    assert client.post("/api/grc/audit/import", headers=login(client, "auditor")).status_code == 403


def test_reports_generate_list_and_download(client):
    h = login(client, "analyst")
    assert client.get("/api/grc/reports", headers=h).json()["runs"] == []
    r = client.post("/api/grc/reports/generate", json={"days": 30, "audience": "both"}, headers=h)
    assert r.status_code == 200 and set(r.json()["files"]) == {"executive", "technical"}
    runs = client.get("/api/grc/reports", headers=login(client, "auditor")).json()["runs"]
    assert runs[0]["days"] == 30 and runs[0]["audience"] == "both"
    name = runs[0]["files"]["executive"]
    pdf = client.get(f"/api/grc/reports/files/{name}", headers=login(client, "auditor"))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get("/api/grc/reports/files/../../etc/passwd", headers=h).status_code in (404, 422)
    assert client.get("/api/grc/reports/files/evil.pdf", headers=h).status_code == 404


def test_reports_rules_for_roles_and_input(client):
    assert client.post("/api/grc/reports/generate", json={"days": 7}, headers=login(client, "auditor")).status_code == 403
    h = login(client, "analyst")
    assert client.post("/api/grc/reports/generate", json={"days": 0}, headers=h).status_code == 422
    assert client.post("/api/grc/reports/generate", json={"audience": "everyone"}, headers=h).status_code == 422
    assert client.get("/api/grc/audit", headers=login(client, "client")).status_code == 403
