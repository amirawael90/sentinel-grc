"""Tamper-evident audit log (used by Z9, platform security requirement).

Every entry stores the hash of the previous entry, so changing or deleting a past entry breaks the
chain and verify() reports where. Format (JSON lines): seq, ts, actor, action, target, result,
correlation_id, details, sample, prev_hash, hash.

Limit: deleting the LAST entries cannot be detected from the file alone. Auditors should note the
head hash and entry count (head()) and compare later.

Also converts the executor's action audit lines (Mohamed's ActionRequest/ActionResult) into audit entries.
"""
import csv
import hashlib
import io
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE = Path(__file__).parent
AUDIT_FILE = BASE / "data" / "audit" / "audit.jsonl"
GENESIS = "0" * 64
FIELDS = ["seq", "ts", "actor", "action", "target", "result", "correlation_id", "details", "sample"]
_LOCK = threading.Lock()


def _digest(prev_hash: str, entry: dict) -> str:
    body = json.dumps({k: entry[k] for k in FIELDS}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def read_all(path: Path = AUDIT_FILE) -> list[dict]:
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def append(actor: str, action: str, target: str = "", result: str = "success", correlation_id: str = "",
           details: Optional[dict[str, Any]] = None, sample: bool = False, path: Path = AUDIT_FILE,
           ts: Optional[datetime] = None) -> dict:
    with _LOCK:
        entries = read_all(path)
        prev = entries[-1]["hash"] if entries else GENESIS
        entry = {"seq": len(entries) + 1, "ts": (ts or datetime.now(timezone.utc)).isoformat(), "actor": actor,
                 "action": action, "target": target, "result": result, "correlation_id": correlation_id,
                 "details": details or {}, "sample": sample}
        entry["prev_hash"] = prev
        entry["hash"] = _digest(prev, entry)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry


def verify(path: Path = AUDIT_FILE) -> dict:
    """Walk the chain. Returns {ok, entries, head, broken_at, reason}."""
    entries = read_all(path)
    prev = GENESIS
    for i, e in enumerate(entries, start=1):
        if e["seq"] != i:
            return {"ok": False, "entries": len(entries), "head": prev, "broken_at": i,
                    "reason": "sequence number gap: an entry was removed or reordered"}
        if e["prev_hash"] != prev:
            return {"ok": False, "entries": len(entries), "head": prev, "broken_at": i,
                    "reason": "link to the previous entry is broken"}
        if _digest(prev, e) != e["hash"]:
            return {"ok": False, "entries": len(entries), "head": prev, "broken_at": i,
                    "reason": "entry content was changed after it was written"}
        prev = e["hash"]
    return {"ok": True, "entries": len(entries), "head": prev, "broken_at": None, "reason": None}


def search(actor: str = "", action: str = "", target: str = "", q: str = "", result: str = "",
           since: Optional[str] = None, until: Optional[str] = None, path: Path = AUDIT_FILE) -> list[dict]:
    """Case-insensitive filters; newest first. since/until are YYYY-MM-DD (inclusive)."""
    def has(value: str, needle: str) -> bool:
        return needle.lower() in str(value).lower()

    out = []
    for e in reversed(read_all(path)):
        day = e["ts"][:10]
        if actor and not has(e["actor"], actor):
            continue
        if action and not has(e["action"], action):
            continue
        if target and not has(e["target"], target):
            continue
        if result and e["result"].lower() != result.lower():
            continue
        if since and day < since:
            continue
        if until and day > until:
            continue
        if q and not has(" ".join(str(e[k]) for k in ("actor", "action", "target", "result", "correlation_id", "details")), q):
            continue
        out.append(e)
    return out


def to_csv(entries: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seq", "ts", "actor", "action", "target", "result", "correlation_id", "details", "sample", "hash"])
    for e in entries:
        w.writerow([e["seq"], e["ts"], e["actor"], e["action"], e["target"], e["result"], e["correlation_id"],
                    json.dumps(e["details"], sort_keys=True), e["sample"], e["hash"]])
    return buf.getvalue()


def entry_from_action_line(line: dict) -> dict:
    """Map one line of the executor audit ({"request": ..., "result": ...}) to audit-entry arguments."""
    req, res = line["request"], line["result"]
    args = req.get("args", {})
    target = args.get("ip") or args.get("username") or args.get("pattern") or req.get("incident_id", "")
    return {"actor": req.get("actor", "agent"), "action": req.get("tool", "?"), "target": str(target),
            "result": str(res.get("status", "?")), "correlation_id": res.get("correlation_id") or req.get("correlation_id", ""),
            "ts": datetime.fromisoformat(str(res["finished_at"]).replace("Z", "+00:00")) if res.get("finished_at") else None,
            "details": {"action_id": res.get("action_id"), "incident_id": req.get("incident_id"), "gate": req.get("gate"),
                        "rejection_code": res.get("rejection_code"), "verified": (res.get("verification") or {}).get("ok")}}


def import_action_audit(source: Path, path: Path = AUDIT_FILE) -> int:
    """Add executor audit lines that are not in the log yet (matched by action_id). Returns how many were added."""
    known = {e["details"].get("action_id") for e in read_all(path) if e["details"].get("action_id")}
    added = 0
    for raw in Path(source).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        kwargs = entry_from_action_line(json.loads(raw))
        if kwargs["details"]["action_id"] in known:
            continue
        append(path=path, **kwargs)
        known.add(kwargs["details"]["action_id"])
        added += 1
    return added


def head(path: Path = AUDIT_FILE) -> dict:
    v = verify(path)
    return {"entries": v["entries"], "head": v["head"]}


def seed_sample(path: Path = AUDIT_FILE) -> int:
    """Demo entries (flagged sample=True) so the viewer has something to show before real components write."""
    if read_all(path):
        return 0
    base = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    rows = [
        ("agent", "decision", "INC-41", "success", {"verdict": "true_positive", "confidence": 0.93}),
        ("executor", "block_ip", "203.0.113.7", "success", {"gate": "G2", "ttl_minutes": 60, "verified": True}),
        ("executor", "add_waf_rule", "/search", "success", {"gate": "G2"}),
        ("agent", "decision", "INC-42", "success", {"verdict": "false_positive", "confidence": 0.71}),
        ("policy_guard", "block_ip", "10.0.0.5", "rejected", {"rejection_code": "allowlisted"}),
        ("admin", "login", "admin", "success", {}),
        ("analyst", "undo_action", "203.0.113.7", "success", {"reason": "test traffic"}),
        ("pentest-runner", "scan_started", "skyline-web", "success", {"profile": "quick"}),
        ("pentest-runner", "scan_finished", "skyline-web", "success", {"findings": 12}),
        ("executor", "rate_limit_ip", "198.51.100.20", "success", {"gate": "G1"}),
        ("admin", "update_policy", "POL-001", "success", {"field": "bruteforce_block_ttl_minutes"}),
        ("auditor", "export_audit", "csv", "success", {}),
    ]
    for i, (actor, action, target, result, details) in enumerate(rows):
        append(actor, action, target, result, f"corr-{1000 + i}", details, sample=True, path=path,
               ts=base.replace(minute=i * 7 % 60, hour=9 + i // 8))
    return len(rows)
