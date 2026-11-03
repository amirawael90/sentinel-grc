import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from remediation import (Finding, create_from_findings, create_from_gaps, metrics, overdue,  # noqa: E402
                         process_retest, risk_signals, set_status, sync_control_gaps)

T0 = date(2026, 11, 1)
CFG = {"due_days": {"critical": 7, "high": 14, "medium": 30, "low": 60}, "control_gap_due_days": 90,
       "default_owner": "TBD"}


def finding(id="F1", severity="high", status="open", asset="web"):
    return Finding(id=id, title="t", endpoint="/x", cwe="CWE-1", severity=severity, status=status, asset=asset)


def test_due_date_depends_on_severity():
    store = {}
    create_from_findings([finding("A", "critical"), finding("B", "low")], store, CFG, T0)
    due = {t.source_id: t.due_date for t in store.values()}
    assert due["A"] == T0 + timedelta(days=7) and due["B"] == T0 + timedelta(days=60)


def test_no_duplicate_tasks():
    store = {}
    create_from_findings([finding()], store, CFG, T0)
    assert create_from_findings([finding()], store, CFG, T0) == []
    assert len(store) == 1


def test_cannot_close_by_hand():
    store = {}
    create_from_findings([finding()], store, CFG, T0)
    set_status(store, "REM-001", "Awaiting retest")
    with pytest.raises(ValueError):
        set_status(store, "REM-001", "Closed")


def test_retest_fixed_closes_task():
    store = {}
    create_from_findings([finding()], store, CFG, T0)
    ch = process_retest(store, [finding(status="fixed")], CFG, T0 + timedelta(days=5))
    t = store["REM-001"]
    assert ch["closed"] == ["REM-001"] and t.status == "Closed" and t.closed_on == T0 + timedelta(days=5)


def test_retest_remaining_keeps_task_open():
    store = {}
    create_from_findings([finding()], store, CFG, T0)
    set_status(store, "REM-001", "Awaiting retest")
    process_retest(store, [finding(status="remaining")], CFG, T0)
    assert store["REM-001"].status == "In progress"


def test_retest_new_finding_creates_task():
    store = {}
    ch = process_retest(store, [finding("N", status="new")], CFG, T0)
    assert ch["new"] == ["REM-001"] and store["REM-001"].source_id == "N"


def test_overdue_and_risk_signals():
    store = {}
    create_from_findings([finding("A", "critical"), finding("B", "low", asset="db")], store, CFG, T0)
    late = T0 + timedelta(days=10)  # critical due day 7, low due day 60
    assert [t.source_id for t in overdue(store, late)] == ["A"]
    assert risk_signals(store, late) == {"web": {"overdue": 1, "worst_priority": "critical", "max_days_late": 3}}


def test_closed_task_is_not_overdue():
    store = {}
    create_from_findings([finding()], store, CFG, T0)
    process_retest(store, [finding(status="fixed")], CFG, T0)
    assert overdue(store, T0 + timedelta(days=100)) == []


def test_metrics_mean_time_to_remediate():
    store = {}
    create_from_findings([finding("A"), finding("B")], store, CFG, T0)
    process_retest(store, [finding("A", status="fixed")], CFG, T0 + timedelta(days=4))
    assert metrics(store, T0) == {"open": 1, "overdue": 0, "closed": 1, "mean_days_to_remediate": 4.0}


def test_gap_task_closes_when_gap_disappears():
    store = {}
    gaps = [{"framework": "X", "category": "C", "points_lost": 2.0}]
    create_from_gaps(gaps, store, CFG, T0)
    assert sync_control_gaps(store, gaps, T0) == []
    assert sync_control_gaps(store, [], T0) == ["REM-001"] and store["REM-001"].status == "Closed"
