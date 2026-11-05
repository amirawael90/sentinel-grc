"""GRC endpoints (Amira, tasks Z8/Z9): compliance, controls, policies, evidence, audit log, reports.

The GRC core (control library, compliance scoring, evidence collector, policy library, audit log, report
generator) lives in api/app/grc/ (a copy of the grc/ folder of github.com/amirawael90/sentinel-grc).
Set GRC_DIR to use another copy. Every request re-reads the files, so the pages update when data changes.
Environment: ACTION_AUDIT_FILE = path of the executor's actions.jsonl (for POST /audit/import).
"""
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth.deps import require_roles

GRC_DIR = Path(os.environ.get("GRC_DIR") or Path(__file__).resolve().parent.parent / "grc")
if str(GRC_DIR) not in sys.path:
    sys.path.insert(0, str(GRC_DIR))

import audit_log  # noqa: E402
import compliance  # noqa: E402
import evidence  # noqa: E402
import policies  # noqa: E402
from control_library import load_controls  # noqa: E402

router = APIRouter(prefix="/grc", tags=["grc"])
READ = require_roles("Admin", "Analyst", "Auditor")
WRITE = require_roles("Admin", "Analyst")

LABELS = {"NIST_CSF_2.0": "NIST CSF 2.0", "ISO27001_2022": "ISO/IEC 27001:2022", "CIS_V8_1": "CIS Controls v8.1",
          "OWASP_TOP10_2025": "OWASP Top 10:2025"}
REPORT_NAME = re.compile(r"^(executive|technical)_\d{4}-\d{2}-\d{2}_\d{6}\.pdf$")


def _state():
    controls = load_controls()
    features, overrides = compliance.load_feature_status(), compliance.load_overrides()
    return controls, features, overrides


def _evidence_summary(controls):
    store = evidence.load_store()
    return evidence.summary_per_control([c.id for c in controls], store, datetime.now(timezone.utc)), store


def _log(user: dict, action: str, target: str = "", result: str = "success", details: Optional[dict] = None) -> None:
    audit_log.append(user["username"], action, target, result, details=details)


def _page(rows: list, page: int, page_size: int) -> dict:
    start = (page - 1) * page_size
    return {"total": len(rows), "page": page, "page_size": page_size, "items": rows[start:start + page_size]}


# ---------------- compliance (Z8) ----------------
@router.get("/compliance")
def compliance_overview(_user: dict = Depends(READ)) -> dict:
    controls, features, overrides = _state()
    scores = compliance.compute(controls, features, overrides)
    ev, store = _evidence_summary(controls)
    percents = [r["percent"] for r in scores.values() if r["percent"] is not None]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": round(sum(percents) / len(percents), 1) if percents else 0.0,
        "total_controls": len(controls),
        "frameworks": [
            {"id": fw, "label": LABELS.get(fw, fw), "percent": r["percent"] or 0.0, "counts": r["counts"],
             "functions": [{"name": n, "percent": p or 0.0} for n, p in r["functions"].items()]}
            for fw, r in scores.items()],
        "gaps": compliance.gaps(controls, features, overrides, top=8),
        "quick_wins": compliance.quick_wins(controls, features, overrides, top=8),
        "evidence": {"items": len(store), "controls_fresh": sum(v["state"] == "fresh" for v in ev.values()),
                     "controls_stale": sum(v["state"] == "stale" for v in ev.values()),
                     "controls_none": sum(v["state"] == "no_evidence" for v in ev.values())},
    }


@router.get("/controls")
def list_controls(
    framework: Optional[str] = None,
    status: Optional[str] = Query(None, description="Implemented | Partial | Not implemented | Not applicable"),
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _user: dict = Depends(READ),
) -> dict:
    controls, features, overrides = _state()
    ev, _ = _evidence_summary(controls)
    rows = []
    needle = (q or "").lower()
    for c in controls:
        st = compliance.effective_status(c, features, overrides)
        if framework and c.framework != framework:
            continue
        if status and st != status:
            continue
        if needle and needle not in f"{c.id} {c.title or ''} {c.description} {c.category}".lower():
            continue
        rows.append({
            "id": c.id, "framework": c.framework, "function": c.function, "category": c.category,
            "title": c.title, "description": c.description, "status": st, "maturity": c.maturity, "owner": c.owner,
            "review_date": c.review_date.isoformat() if c.review_date else None,
            "platform_features": c.platform_features, "evidence": ev[c.id],
        })
    return _page(rows, page, page_size)


# ---------------- policies (Z8) ----------------
@router.get("/policies")
def list_policies(_user: dict = Depends(READ)) -> dict:
    lib = policies.load_policies()
    today = date.today()
    overdue_ids = {p.id for p in lib.overdue_reviews(today)}
    pb = sorted({d.playbook for p in lib.policies for d in p.drives})
    return {
        "policies": [{**p.model_dump(mode="json"), "review_overdue": p.id in overdue_ids} for p in lib.policies],
        "exceptions": [{**e.model_dump(mode="json"), "expired": e.expires_on < today} for e in lib.exceptions],
        "effective_parameters": {name: lib.parameters(name, today) for name in pb},
        "overdue_reviews": len(overdue_ids),
        "expired_exceptions": len(lib.expired_exceptions(today)),
    }


@router.post("/policies/{policy_id}/acknowledge")
def acknowledge_policy(policy_id: str, user: dict = Depends(WRITE)) -> dict:
    lib = policies.load_policies()
    if not any(p.id == policy_id for p in lib.policies):
        raise HTTPException(status_code=404, detail="Policy not found")
    lib.acknowledge(policy_id, user["username"])
    policies.save_policies(lib)
    _log(user, "acknowledge_policy", policy_id)
    p = next(p for p in lib.policies if p.id == policy_id)
    return {"id": p.id, "acknowledgements": [a.model_dump(mode="json") for a in p.acknowledgements]}


# ---------------- evidence (Z3 / Z9) ----------------
@router.post("/evidence/collect")
def collect_evidence(user: dict = Depends(WRITE)) -> dict:
    controls = load_controls()
    sources = evidence.load_sources(known_controls={c.id for c in controls})
    store = evidence.collect(sources, evidence.load_store())
    evidence.save_store(store)
    _log(user, "collect_evidence", "all sources", details={"items": len(store)})
    return {"items": len(store)}


@router.get("/evidence")
def browse_evidence(
    control: Optional[str] = Query(None, description="control id, or part of it"),
    source: Optional[str] = None,
    state: Optional[Literal["fresh", "stale"]] = None,
    since: Optional[str] = Query(None, description="YYYY-MM-DD, last verified on or after"),
    until: Optional[str] = Query(None, description="YYYY-MM-DD, last verified on or before"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user: dict = Depends(READ),
) -> dict:
    store = evidence.load_store()
    now = datetime.now(timezone.utc)
    rows = []
    for e in sorted(store.values(), key=lambda x: x.last_verified_at, reverse=True):
        stale = evidence.is_stale(e, now)
        day = e.last_verified_at.date().isoformat()
        if control and not any(control.lower() in c.lower() for c in e.linked_controls):
            continue
        if source and e.source != source:
            continue
        if state and (state == "stale") != stale:
            continue
        if since and day < since:
            continue
        if until and day > until:
            continue
        rows.append({**e.model_dump(mode="json"), "state": "stale" if stale else "fresh"})
    body = _page(rows, page, page_size)
    body["sources"] = sorted({e.source for e in store.values()})
    return body


@router.get("/evidence/verify")
def verify_evidence(_user: dict = Depends(READ)) -> dict:
    """Re-hash every stored evidence file: detects files changed or removed after collection."""
    store = evidence.load_store()
    problems = evidence.verify(store)
    return {"ok": not problems, "checked": len(store), "problems": problems}


# ---------------- audit log (Z9) ----------------
@router.get("/audit")
def browse_audit(
    actor: str = "", action: str = "", target: str = "", q: str = "", result: str = "",
    since: Optional[str] = None, until: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    _user: dict = Depends(READ),
) -> dict:
    entries = audit_log.search(actor, action, target, q, result, since, until)
    body = _page(entries, page, page_size)
    body["chain"] = audit_log.head()
    body["has_sample"] = any(e["sample"] for e in audit_log.read_all())
    return body


@router.get("/audit/verify")
def verify_audit(_user: dict = Depends(READ)) -> dict:
    return audit_log.verify()


@router.get("/audit/export")
def export_audit(
    actor: str = "", action: str = "", target: str = "", q: str = "", result: str = "",
    since: Optional[str] = None, until: Optional[str] = None,
    user: dict = Depends(READ),
) -> Response:
    entries = audit_log.search(actor, action, target, q, result, since, until)
    _log(user, "export_audit", "csv", details={"rows": len(entries)})
    return Response(audit_log.to_csv(entries), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="sentinel_audit_log.csv"'})


@router.post("/audit/import")
def import_executor_audit(user: dict = Depends(WRITE)) -> dict:
    """Add the executor's action audit (actions.jsonl) to the audit log. Needs ACTION_AUDIT_FILE."""
    source = os.environ.get("ACTION_AUDIT_FILE")
    if not source or not Path(source).exists():
        raise HTTPException(status_code=400, detail="Set ACTION_AUDIT_FILE to the executor's actions.jsonl first")
    added = audit_log.import_action_audit(Path(source))
    _log(user, "import_action_audit", Path(source).name, details={"added": added})
    return {"added": added}


# ---------------- reports (Z7 / Z9) ----------------
class ReportRequest(BaseModel):
    days: int = Field(7, ge=1, le=365)
    audience: Literal["both", "executive", "technical"] = "both"


def _reports_dir() -> Path:
    return GRC_DIR / "reports"


@router.get("/reports")
def report_history(_user: dict = Depends(READ)) -> dict:
    import json
    history_file = _reports_dir() / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
    return {"runs": list(reversed(history))}


@router.post("/reports/generate")
def generate_reports(req: ReportRequest, user: dict = Depends(WRITE)) -> dict:
    try:
        import reports  # imported here so the API still starts if reportlab is not installed yet
    except ImportError as exc:
        raise HTTPException(status_code=501, detail=f"PDF library missing ({exc}). Run: pip install reportlab") from exc
    files = reports.generate(_reports_dir(), days=req.days, audience=req.audience)
    _log(user, "generate_report", req.audience, details={"days": req.days, "files": [f.name for f in files.values()]})
    return {"files": {k: v.name for k, v in files.items()}}


@router.get("/reports/files/{name}")
def report_file(name: str, _user: dict = Depends(READ)) -> FileResponse:
    path = _reports_dir() / name
    if not REPORT_NAME.match(name) or not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})
