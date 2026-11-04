import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).parent.parent))
from reports import decisions_needed, generate, overall_compliance  # noqa: E402


def data(**over):
    d = {"task_metrics": {"overdue": 0, "open": 0, "closed": 0}, "tasks": [], "findings": [], "policies": [],
         "overdue_reviews": [], "expired_exceptions": [], "compliance": {"X": {"percent": 80.0}}}
    d.update(over)
    return d


def test_no_decisions_when_everything_is_fine():
    assert decisions_needed(data()) == ["No decisions needed this period."]


def test_decisions_are_derived_from_the_data():
    d = data(task_metrics={"overdue": 2, "open": 3, "closed": 0},
             tasks=[NS(owner="TBD", status="Open")],
             findings=[NS(severity="critical", status="open")],
             policies=[NS(approval_status="Draft")],
             compliance={"CIS_V8_1": {"percent": 10.0}})
    text = " ".join(decisions_needed(d))
    for expected in ("overdue", "no owner", "critical finding", "Draft", "CIS v8.1"):
        assert expected in text


def test_overall_compliance_is_the_mean():
    assert overall_compliance(data(compliance={"A": {"percent": 10.0}, "B": {"percent": 30.0}, "C": {"percent": None}})) == 20.0


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("reports")
    return out, generate(out, days=7, today=date(2026, 11, 1))


def test_both_reports_are_created(built):
    _, files = built
    assert files["executive"].stat().st_size > 1000 and files["technical"].stat().st_size > 1000


def test_executive_report_fits_two_pages_and_has_key_sections(built):
    _, files = built
    pdf = PdfReader(str(files["executive"]))
    text = " ".join(p.extract_text() for p in pdf.pages)
    assert len(pdf.pages) <= 2
    for expected in ("Executive Security Report", "Top risks", "Decisions needed", "SAMPLE", "not a certification"):
        assert expected in text


def test_technical_report_has_all_sections(built):
    _, files = built
    text = " ".join(p.extract_text() for p in PdfReader(str(files["technical"])).pages)
    for expected in ("Incidents", "Automatic actions", "Penetration-test findings", "Remediation tasks",
                     "Compliance coverage", "Evidence", "Policies"):
        assert expected in text


def test_history_is_recorded(built):
    out, _ = built
    history = json.loads((out / "history.json").read_text())
    assert history[-1]["period_end"] == "2026-11-01" and "executive" in history[-1]["files"]
