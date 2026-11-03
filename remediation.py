"""Remediation tracker (task Z5).

Tasks come from pentest findings and from compliance gaps. A finding task closes ONLY when
a retest confirms the fix. Overdue tasks are reported so the risk job can raise the risk.

Input contract (Finding record, owned by Omar): id, title, endpoint, cwe, severity, status, evidence
(+ optional asset). Until the pentest module exists we read data/mock/findings.json; swap
load_findings() for the real source later, nothing else changes.

Usage: python remediation.py [--reset] [--retest data/mock/retest.json]
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "data" / "remediation_config.yaml"
STORE_FILE = BASE / "data" / "remediation" / "tasks.json"
FINDINGS_FILE = BASE / "data" / "mock" / "findings.json"

Severity = Literal["critical", "high", "medium", "low"]
Status = Literal["Open", "In progress", "Awaiting retest", "Closed"]


class Finding(BaseModel):
    id: str
    title: str
    endpoint: str
    cwe: str
    severity: Severity
    status: Literal["open", "fixed", "remaining", "new"] = "open"
    evidence: str = ""
    asset: Optional[str] = None


class Task(BaseModel):
    id: str
    source_type: Literal["finding", "control_gap"]
    source_id: str
    title: str
    owner: str
    priority: Severity
    due_date: date
    status: Status = "Open"
    created_on: date
    closed_on: Optional[date] = None
    closed_reason: Optional[str] = None
    asset: Optional[str] = None


def load_config(path: Path = CONFIG_FILE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_findings(path: Path = FINDINGS_FILE) -> list[Finding]:
    return [Finding(**f) for f in json.loads(Path(path).read_text(encoding="utf-8"))]


def load_store(path: Path = STORE_FILE) -> dict[str, Task]:
    if not path.exists():
        return {}
    return {k: Task(**v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def save_store(store: dict[str, Task], path: Path = STORE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: json.loads(v.model_dump_json()) for k, v in store.items()}, indent=2),
                    encoding="utf-8")


def _next_id(store: dict[str, Task]) -> str:
    return f"REM-{len(store) + 1:03d}"


def _find(store: dict[str, Task], source_type: str, source_id: str) -> Optional[Task]:
    return next((t for t in store.values() if t.source_type == source_type and t.source_id == source_id), None)


def create_from_findings(findings: list[Finding], store: dict[str, Task], config: dict,
                         today: Optional[date] = None) -> list[Task]:
    """One task per finding. A finding that already has a task is skipped."""
    today = today or date.today()
    created = []
    for f in findings:
        if f.status == "fixed" or _find(store, "finding", f.id):
            continue
        t = Task(id=_next_id(store), source_type="finding", source_id=f.id,
                 title=f"Fix {f.title} ({f.cwe}) at {f.endpoint}", owner=config["default_owner"],
                 priority=f.severity, due_date=today + timedelta(days=config["due_days"][f.severity]),
                 created_on=today, asset=f.asset)
        store[t.id] = t
        created.append(t)
    return created


def create_from_gaps(gaps: list[dict], store: dict[str, Task], config: dict,
                     today: Optional[date] = None) -> list[Task]:
    """One task per compliance gap category (input = compliance.gaps())."""
    today = today or date.today()
    created = []
    for g in gaps:
        key = f"{g['framework']}|{g['category']}"
        existing = _find(store, "control_gap", key)
        if existing and existing.status != "Closed":
            continue
        t = Task(id=_next_id(store), source_type="control_gap", source_id=key,
                 title=f"Close compliance gap: {g['category']} ({g['framework']})",
                 owner=config["default_owner"], priority="medium", created_on=today,
                 due_date=today + timedelta(days=config["control_gap_due_days"]))
        store[t.id] = t
        created.append(t)
    return created


def set_status(store: dict[str, Task], task_id: str, status: Status) -> None:
    """Owner moves a task. Closing is not allowed here: findings close by retest, gaps by compliance sync."""
    if status == "Closed":
        raise ValueError("A task cannot be closed by hand: it closes when a retest or the compliance score confirms the fix.")
    store[task_id].status = status


def process_retest(store: dict[str, Task], retest: list[Finding], config: dict,
                   today: Optional[date] = None) -> dict[str, list[str]]:
    """fixed -> Closed | remaining -> back to In progress | new -> new task."""
    today = today or date.today()
    changes: dict[str, list[str]] = {"closed": [], "reopened": [], "new": []}
    for f in retest:
        task = _find(store, "finding", f.id)
        if f.status == "fixed" and task and task.status != "Closed":
            task.status, task.closed_on, task.closed_reason = "Closed", today, "retest confirmed fix"
            changes["closed"].append(task.id)
        elif f.status == "remaining" and task:
            task.status, task.closed_on, task.closed_reason = "In progress", None, None
            changes["reopened"].append(task.id)
        elif f.status == "new" and not task:
            changes["new"] += [t.id for t in create_from_findings([f.model_copy(update={"status": "open"})], store, config, today)]
    return changes


def sync_control_gaps(store: dict[str, Task], current_gaps: list[dict], today: Optional[date] = None) -> list[str]:
    """Close gap tasks whose category no longer loses points in the compliance score."""
    today = today or date.today()
    still_open = {f"{g['framework']}|{g['category']}" for g in current_gaps}
    closed = []
    for t in store.values():
        if t.source_type == "control_gap" and t.status != "Closed" and t.source_id not in still_open:
            t.status, t.closed_on, t.closed_reason = "Closed", today, "compliance gap closed"
            closed.append(t.id)
    return closed


def overdue(store: dict[str, Task], today: Optional[date] = None) -> list[Task]:
    today = today or date.today()
    return [t for t in store.values() if t.status != "Closed" and t.due_date < today]


def risk_signals(store: dict[str, Task], today: Optional[date] = None) -> dict[str, dict]:
    """Per asset: overdue count and the worst priority. The risk job (Rawda) raises likelihood from this."""
    today = today or date.today()
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    signals: dict[str, dict] = {}
    for t in overdue(store, today):
        s = signals.setdefault(t.asset or "unassigned", {"overdue": 0, "worst_priority": "low", "max_days_late": 0})
        s["overdue"] += 1
        if rank[t.priority] > rank[s["worst_priority"]]:
            s["worst_priority"] = t.priority
        s["max_days_late"] = max(s["max_days_late"], (today - t.due_date).days)
    return signals


def metrics(store: dict[str, Task], today: Optional[date] = None) -> dict:
    """Numbers for the KRI endpoint: open, overdue, closed, mean time to remediate (days)."""
    closed = [t for t in store.values() if t.status == "Closed"]
    days = [(t.closed_on - t.created_on).days for t in closed if t.closed_on]
    return {"open": len(store) - len(closed), "overdue": len(overdue(store, today)), "closed": len(closed),
            "mean_days_to_remediate": round(sum(days) / len(days), 1) if days else None}


if __name__ == "__main__":
    from compliance import gaps as compliance_gaps, load_feature_status, load_overrides
    from control_library import load_controls

    config = load_config()
    if "--reset" in sys.argv and STORE_FILE.exists():
        STORE_FILE.unlink()
    store = load_store()
    if "--retest" in sys.argv:
        retest_file = sys.argv[sys.argv.index("--retest") + 1]
        print("Retest:", process_retest(store, load_findings(Path(retest_file)), config))
    else:
        made = create_from_findings(load_findings(), store, config)
        print(f"New tasks from findings: {len(made)}")
    current = compliance_gaps(load_controls(), load_feature_status(), load_overrides(), top=config["top_gaps"])
    print(f"New tasks from compliance gaps: {len(create_from_gaps(current, store, config))}")
    print("Closed because the gap is gone:", sync_control_gaps(store, current))
    save_store(store)
    print("Metrics:", metrics(store))
    print("Risk signals:", risk_signals(store))
