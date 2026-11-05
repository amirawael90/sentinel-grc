"""Report generator (task Z7): executive (1-2 pages) and technical reports as PDF.

One command builds both from live data:  python reports.py [--days 7] [--out reports]

Computed from our own modules: compliance (Z2), evidence (Z3), policies (Z4), remediation (Z5).
Read from data/mock/ops_stats.json (SAMPLE until the other components are connected): incidents,
actions, top risks, ATT&CK coverage. Findings come from the Finding contract (remediation.load_findings).
Replace load_ops_stats() with the real sources later; the rest does not change.
Weekly: schedule the same command (see README).
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import compliance
import evidence
import policies
import remediation
from control_library import load_controls

BASE = Path(__file__).parent
OPS_FILE = BASE / "data" / "mock" / "ops_stats.json"
SEV_COLORS = {"critical": "#C62828", "high": "#EF6C00", "medium": "#F9A825", "low": "#1565C0"}
NAVY, GREY = colors.HexColor("#14213D"), colors.HexColor("#555555")
COMPLIANCE_ALERT_BELOW = 50.0
FRAMEWORK_LABELS = {"NIST_CSF_2.0": "NIST CSF 2.0", "ISO27001_2022": "ISO 27001", "CIS_V8_1": "CIS v8.1",
                    "OWASP_TOP10_2025": "OWASP Top 10"}


# ---------------- data ----------------
def load_ops_stats(path: Path = OPS_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def gather_data(days: int = 7, today: date | None = None, ops_path: Path = OPS_FILE) -> dict:
    today = today or date.today()
    controls = load_controls()
    features, overrides = compliance.load_feature_status(), compliance.load_overrides()
    comp = compliance.compute(controls, features, overrides)
    ev_store = evidence.load_store()
    now = datetime.now(timezone.utc)
    ev_by_source: dict[str, dict] = {}
    for e in ev_store.values():
        s = ev_by_source.setdefault(e.source, {"items": 0, "stale": 0})
        s["items"] += 1
        s["stale"] += evidence.is_stale(e, now)
    ev_summary = evidence.summary_per_control([c.id for c in controls], ev_store, now)
    lib = policies.load_policies()
    tasks = remediation.load_store()
    findings = remediation.load_findings()
    return {
        "today": today, "since": today - timedelta(days=days), "ops": load_ops_stats(ops_path),
        "compliance": comp,
        "gaps": compliance.gaps(controls, features, overrides, top=8),
        "quick_wins": compliance.quick_wins(controls, features, overrides, top=8),
        "evidence": {"items": len(ev_store), "by_source": ev_by_source,
                     "controls_fresh": sum(r["state"] == "fresh" for r in ev_summary.values()),
                     "controls_stale": sum(r["state"] == "stale" for r in ev_summary.values()),
                     "controls_none": sum(r["state"] == "no_evidence" for r in ev_summary.values())},
        "policies": lib.policies, "overdue_reviews": lib.overdue_reviews(today),
        "expired_exceptions": lib.expired_exceptions(today),
        "tasks": list(tasks.values()), "task_metrics": remediation.metrics(tasks, today),
        "overdue_tasks": remediation.overdue(tasks, today), "findings": findings,
    }


def decisions_needed(d: dict) -> list[str]:
    out = []
    m = d["task_metrics"]
    if m["overdue"]:
        out.append(f"{m['overdue']} remediation task(s) are overdue: confirm owners and new due dates.")
    no_owner = sum(t.owner == "TBD" and t.status != "Closed" for t in d["tasks"])
    if no_owner:
        out.append(f"{no_owner} open remediation task(s) have no owner: assign owners.")
    crit = sum(f.severity == "critical" and f.status != "fixed" for f in d["findings"])
    if crit:
        out.append(f"{crit} critical finding(s) remain open: approve priority fixes and a retest date.")
    drafts = sum(p.approval_status == "Draft" for p in d["policies"])
    if drafts:
        out.append(f"{drafts} polic(ies) are in Draft: approve or retire them.")
    if d["overdue_reviews"]:
        out.append(f"{len(d['overdue_reviews'])} polic(ies) are past their review date.")
    if d["expired_exceptions"]:
        out.append(f"{len(d['expired_exceptions'])} policy exception(s) expired: renew or remove.")
    low = [FRAMEWORK_LABELS.get(fw, fw) for fw, r in d["compliance"].items()
           if r["percent"] is not None and r["percent"] < COMPLIANCE_ALERT_BELOW]
    if low:
        out.append(f"Compliance is below {int(COMPLIANCE_ALERT_BELOW)}% for {', '.join(low)}: approve the quick-win plan.")
    return out[:6] or ["No decisions needed this period."]


def overall_compliance(d: dict) -> float:
    vals = [r["percent"] for r in d["compliance"].values() if r["percent"] is not None]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


# ---------------- layout helpers ----------------
def styles():
    s = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=s["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=NAVY, alignment=0, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=s["Normal"], fontSize=9, textColor=GREY, spaceAfter=6),
        "h": ParagraphStyle("h", parent=s["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=NAVY, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", parent=s["Normal"], fontSize=9, leading=12),
        "big": ParagraphStyle("b", parent=s["Normal"], fontName="Helvetica-Bold", fontSize=17, leading=22, textColor=NAVY),
        "small": ParagraphStyle("sm", parent=s["Normal"], fontSize=7.5, leading=10, textColor=GREY),
        "cell": ParagraphStyle("c", parent=s["Normal"], fontSize=8, leading=10),
        "warn": ParagraphStyle("w", parent=s["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#8A4B00"),
                               backColor=colors.HexColor("#FFF3D6"), borderPadding=4, spaceAfter=6),
    }


def P(text, style):
    return Paragraph(escape(str(text)), style)


def table(rows, widths, header=True, st=None):
    st = st or styles()
    data = [[c if not isinstance(c, str) else P(c, st["cell"]) for c in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        data[0] = [Paragraph(f'<font color="white"><b>{escape(str(c))}</b></font>', st["cell"]) for c in rows[0]]
        t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t


def compliance_chart(d, width=250, height=130):
    names = [FRAMEWORK_LABELS.get(fw, fw) for fw in d["compliance"]]
    vals = [r["percent"] or 0 for r in d["compliance"].values()]
    dr = Drawing(width, height)
    ch = HorizontalBarChart()
    ch.x, ch.y, ch.width, ch.height = 70, 12, width - 90, height - 32
    ch.data = [vals[::-1]]
    ch.categoryAxis.categoryNames = names[::-1]
    ch.categoryAxis.labels.fontSize = 8
    ch.valueAxis.valueMin, ch.valueAxis.valueMax, ch.valueAxis.valueStep = 0, 100, 25
    ch.valueAxis.labels.fontSize = 7
    ch.bars[0].fillColor = colors.HexColor("#2E7D32")
    ch.barLabelFormat = "%s%%"
    ch.barLabels.fontSize = 7
    ch.barLabels.nudge = 8
    dr.add(ch)
    dr.add(String(0, height - 10, "Compliance by framework (%)", fontSize=9, fontName="Helvetica-Bold"))
    return dr


def severity_chart(d, width=250, height=130):
    counts = d["ops"]["incidents"]["by_severity"]
    order = ["critical", "high", "medium", "low"]
    dr = Drawing(width, height)
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 25, 22, width - 45, height - 44
    ch.data = [[counts.get(k, 0) for k in order]]
    ch.categoryAxis.categoryNames = [k.capitalize() for k in order]
    ch.categoryAxis.labels.fontSize = 8
    ch.valueAxis.valueMin = 0
    ch.valueAxis.labels.fontSize = 7
    ch.barLabelFormat = "%d"
    ch.barLabels.fontSize = 8
    ch.barLabels.nudge = 7
    for i, k in enumerate(order):
        ch.bars[(0, i)].fillColor = colors.HexColor(SEV_COLORS[k])
    dr.add(ch)
    dr.add(String(0, height - 10, "Incidents by severity", fontSize=9, fontName="Helvetica-Bold"))
    return dr


def tile(value, label, st):
    return [P(value, st["big"]), P(label, st["small"])]


def footer(title):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 10 * mm, f"Sentinel - {title} - generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def banners(d, st):
    items = []
    if d["ops"].get("sample"):
        items.append(Paragraph("Note: incidents, actions and risks in this report are SAMPLE data until those components are "
                               "connected. Compliance, evidence, policy and remediation figures are computed from live files.", st["warn"]))
    return items


COMPLIANCE_NOTE = ("Compliance percentages measure how much of each framework the platform covers, based on the build state of "
                   "the features mapped to each control. They are not a certification.")


# ---------------- reports ----------------
def build_executive(d: dict, path: Path) -> Path:
    st = styles()
    ops, inc, m = d["ops"], d["ops"]["incidents"], d["task_metrics"]
    s = [P("Executive Security Report", st["title"]),
         P(f"{ops['client']} - managed by Sentinel - {d['since']} to {d['today']}", st["sub"])] + banners(d, st)
    tiles = Table([[tile(inc["total"], "incidents in period", st), tile(f"{inc['autonomous_pct']}%", "handled automatically", st),
                    tile(f"{overall_compliance(d)}%", "average compliance coverage", st),
                    tile(m["overdue"], "overdue fixes", st)]], colWidths=[43 * mm] * 4)
    tiles.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
                               ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F7FA"))]))
    s += [tiles, Spacer(1, 6), Table([[compliance_chart(d), severity_chart(d)]], colWidths=[88 * mm, 88 * mm])]
    s.append(P("Top risks", st["h"]))
    s.append(table([["Risk", "Asset", "Score", "Level"]] + [[r["title"], r["asset"], f"{r['score']}/25", r["band"]] for r in ops["top_risks"][:5]],
                   [88 * mm, 32 * mm, 22 * mm, 30 * mm], st=st))
    s.append(P("Response summary", st["h"]))
    s.append(P(f"{inc['total']} incidents were detected; {inc['autonomous_pct']}% were handled automatically. Average time to detect: "
               f"{inc['mttd_seconds']} seconds; average time to resolve: {inc['mttr_minutes']} minutes. "
               f"Fixes: {m['open']} open, {m['closed']} closed, {m['overdue']} overdue.", st["p"]))
    s.append(P("Decisions needed", st["h"]))
    s += [P("- " + x, st["p"]) for x in decisions_needed(d)]
    s += [Spacer(1, 6), P(COMPLIANCE_NOTE, st["small"])]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                      title="Executive Security Report").build(s, onFirstPage=footer("Executive report"), onLaterPages=footer("Executive report"))
    return path


def build_technical(d: dict, path: Path) -> Path:
    st = styles()
    ops = d["ops"]
    s = [P("Technical Security Report", st["title"]), P(f"{ops['client']} - {d['since']} to {d['today']}", st["sub"])] + banners(d, st)
    s.append(P("1. Incidents", st["h"]))
    s.append(table([["ID", "Severity", "Type", "Status", "Action taken"]] + [[i["id"], i["severity"], i["type"], i["status"], i["action"]] for i in ops["incident_list"]],
                   [20 * mm, 22 * mm, 36 * mm, 28 * mm, 70 * mm], st=st))
    s.append(P("2. Automatic actions", st["h"]))
    s.append(table([["Tool", "Target", "Gate", "Result", "Verified"]] + [[a["tool"], a["target"], a["gate"], a["status"], "yes" if a["verified"] else "NO"] for a in ops["actions"]],
                   [34 * mm, 54 * mm, 18 * mm, 28 * mm, 22 * mm], st=st))
    s.append(P("3. Penetration-test findings", st["h"]))
    s.append(table([["ID", "Severity", "CWE", "Endpoint", "Finding", "Status"]] + [[f.id, f.severity, f.cwe, f.endpoint, f.title, f.status] for f in d["findings"]],
                   [14 * mm, 20 * mm, 20 * mm, 30 * mm, 66 * mm, 20 * mm], st=st))
    s.append(P("4. Remediation tasks", st["h"]))
    m = d["task_metrics"]
    s.append(P(f"Open: {m['open']} | Overdue: {m['overdue']} | Closed: {m['closed']} | Mean days to remediate: "
               f"{m['mean_days_to_remediate'] if m['mean_days_to_remediate'] is not None else 'n/a'}", st["p"]))
    open_tasks = sorted([t for t in d["tasks"] if t.status != "Closed"], key=lambda t: t.due_date)[:12]
    if open_tasks:
        s.append(table([["Task", "Title", "Owner", "Due", "Status"]] + [[t.id, t.title, t.owner, str(t.due_date), t.status] for t in open_tasks],
                       [20 * mm, 80 * mm, 20 * mm, 24 * mm, 30 * mm], st=st))
    s.append(P("5. Compliance coverage", st["h"]))
    rows = [["Framework", "Coverage", "Implemented", "Partial", "Not implemented"]]
    for fw, r in d["compliance"].items():
        c = r["counts"]
        rows.append([FRAMEWORK_LABELS.get(fw, fw), f"{r['percent']}%", c.get("Implemented", 0), c.get("Partial", 0), c.get("Not implemented", 0)])
    s.append(table(rows, [44 * mm, 26 * mm, 30 * mm, 26 * mm, 40 * mm], st=st))
    s.append(P("Biggest gaps", st["h"]))
    s.append(table([["Framework", "Category", "Points lost"]] + [[FRAMEWORK_LABELS.get(g["framework"], g["framework"]), g["category"], g["points_lost"]] for g in d["gaps"]],
                   [44 * mm, 100 * mm, 22 * mm], st=st))
    s.append(P("Quick wins (closest to done)", st["h"]))
    s.append(table([["Control", "Status", "Features still to finish"]] + [[w["id"], w["status"], ", ".join(w["missing_features"])] for w in d["quick_wins"]],
                   [34 * mm, 28 * mm, 104 * mm], st=st))
    e = d["evidence"]
    s.append(P("6. Evidence", st["h"]))
    s.append(P(f"{e['items']} evidence items. Controls with fresh evidence: {e['controls_fresh']}, stale: {e['controls_stale']}, none: {e['controls_none']}.", st["p"]))
    if e["by_source"]:
        s.append(table([["Source", "Items", "Stale"]] + [[k, v["items"], v["stale"]] for k, v in e["by_source"].items()], [60 * mm, 25 * mm, 25 * mm], st=st))
    s.append(P("7. Policies", st["h"]))
    s.append(table([["ID", "Policy", "Version", "Status", "Review date"]] + [[p.id, p.title, p.version, p.approval_status, str(p.review_date)] for p in d["policies"]],
                   [18 * mm, 86 * mm, 18 * mm, 22 * mm, 24 * mm], st=st))
    s += [Spacer(1, 6), P(COMPLIANCE_NOTE, st["small"])]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                      title="Technical Security Report").build(s, onFirstPage=footer("Technical report"), onLaterPages=footer("Technical report"))
    return path


def generate(out_dir: Path = BASE / "reports", days: int = 7, today: date | None = None, audience: str = "both") -> dict:
    """Build the reports (audience: both | executive | technical) and append the run to the history file."""
    if audience not in ("both", "executive", "technical"):
        raise ValueError("audience must be both, executive or technical")
    d = gather_data(days, today)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{d['today'].isoformat()}_{datetime.now().strftime('%H%M%S')}"
    files = {}
    if audience in ("both", "executive"):
        files["executive"] = build_executive(d, out_dir / f"executive_{stamp}.pdf")
    if audience in ("both", "technical"):
        files["technical"] = build_technical(d, out_dir / f"technical_{stamp}.pdf")
    history_file = out_dir / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
    history.append({"generated_at": datetime.now(timezone.utc).isoformat(), "period_start": str(d["since"]),
                    "period_end": d["today"].isoformat(), "days": days, "audience": audience,
                    "files": {k: v.name for k, v in files.items()}})
    history_file.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return files


if __name__ == "__main__":
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 7
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else BASE / "reports"
    for kind, f in generate(out, days).items():
        print(f"{kind}: {f}")
