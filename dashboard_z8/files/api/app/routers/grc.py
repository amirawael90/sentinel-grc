"""GRC endpoints (Amira, tasks Z8/Z9): compliance, controls, policies, evidence.

The GRC core (control library, compliance scoring, evidence collector, policy library) lives in
api/app/grc/ (a copy of the grc/ folder of github.com/amirawael90/sentinel-grc). Set the GRC_DIR
environment variable to use another copy. Every request re-reads the files, so the pages update
when evidence, feature status or policies change.
"""
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import require_roles

GRC_DIR = Path(os.environ.get("GRC_DIR") or Path(__file__).resolve().parent.parent / "grc")
if str(GRC_DIR) not in sys.path:
    sys.path.insert(0, str(GRC_DIR))

import compliance  # noqa: E402
import evidence  # noqa: E402
import policies  # noqa: E402
from control_library import load_controls  # noqa: E402

router = APIRouter(prefix="/grc", tags=["grc"])
READ = require_roles("Admin", "Analyst", "Auditor")
WRITE = require_roles("Admin", "Analyst")

LABELS = {"NIST_CSF_2.0": "NIST CSF 2.0", "ISO27001_2022": "ISO/IEC 27001:2022", "CIS_V8_1": "CIS Controls v8.1",
          "OWASP_TOP10_2025": "OWASP Top 10:2025"}
STATUSES = ["Implemented", "Partial", "Not implemented", "Not applicable"]


def _state():
    controls = load_controls()
    features, overrides = compliance.load_feature_status(), compliance.load_overrides()
    return controls, features, overrides


def _evidence_summary(controls):
    store = evidence.load_store()
    return evidence.summary_per_control([c.id for c in controls], store, datetime.now(timezone.utc)), store


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
    start = (page - 1) * page_size
    return {"total": len(rows), "page": page, "page_size": page_size, "items": rows[start:start + page_size]}


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
    p = next(p for p in lib.policies if p.id == policy_id)
    return {"id": p.id, "acknowledgements": [a.model_dump(mode="json") for a in p.acknowledgements]}


@router.post("/evidence/collect")
def collect_evidence(_user: dict = Depends(WRITE)) -> dict:
    controls = load_controls()
    sources = evidence.load_sources(known_controls={c.id for c in controls})
    store = evidence.collect(sources, evidence.load_store())
    evidence.save_store(store)
    return {"items": len(store)}
