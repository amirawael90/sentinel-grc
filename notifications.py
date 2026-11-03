"""Notification engine (task Z6).

Turns an executed action into a message that says WHAT was done, WHY and HOW TO UNDO it, sends it
through Telegram / email / webhook according to routing rules, avoids duplicates, retries failures,
records every delivery, and escalates unacknowledged critical/high incidents.

Input: the action contract (Mohamed): ActionResult + ActionRequest as dicts, plus the decision
(Habiba) and incident (Alaa) if available. See event_from_contract().

Secrets come from environment variables (never from files in git):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID | SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TO
  | WEBHOOK_URL.  A channel without settings runs in DRY-RUN mode (recorded as dry_run, nothing is sent).

Usage: python notifications.py        send a sample critical event (twice, to show de-duplication)
"""
import json
import os
import smtplib
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Optional

import yaml

BASE = Path(__file__).parent
RULES_FILE = BASE / "data" / "notification_rules.yaml"
LOG_FILE = BASE / "data" / "notifications" / "deliveries.jsonl"
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
UNDO = {
    "block_ip": "unblock_ip", "rate_limit_ip": "remove the rate limit", "tarpit_ip": "remove the tarpit",
    "lock_account": "unlock the account", "add_waf_rule": "remove the WAF rule",
    "revoke_sessions": "(sessions cannot be restored; the user logs in again)",
}


# ---------- input ----------
def event_from_contract(result: dict, request: dict, decision: Optional[dict] = None,
                        incident: Optional[dict] = None, case_url: str = "") -> dict:
    """Merge the action contract records into one notification event."""
    decision, incident = decision or {}, incident or {}
    return {
        "incident_id": result.get("incident_id") or request.get("incident_id", "?"),
        "severity": decision.get("severity") or incident.get("severity") or "medium",
        "asset": incident.get("asset"),
        "tool": result.get("tool") or request.get("tool"),
        "args": request.get("args", {}),
        "gate": request.get("gate"),
        "actor": request.get("actor", "agent"),
        "status": result.get("status"),
        "verified": bool((result.get("verification") or {}).get("ok", result.get("verification") is not None)),
        "expires_at": result.get("expires_at"),
        "rollback": result.get("rollback"),
        "reasoning": decision.get("reasoning", ""),
        "evidence": decision.get("evidence", []),
        "case_url": case_url,
    }


def build_message(e: dict) -> tuple[str, str]:
    """Return (subject, text): what was done, why, and how to undo it."""
    args = ", ".join(f"{k}={v}" for k, v in e["args"].items())
    ttl = e["args"].get("ttl_minutes")
    target = e["args"].get("ip") or e["args"].get("username") or ""
    what = f"{e['tool']} {args}".strip() + f" (gate {e['gate']}, by {e['actor']}) - {e['status']}"
    if e["status"] == "success":
        what += ", verified" if e.get("verified") else ", NOT verified"
    if e["tool"] == "block_ip" and ttl:
        undo = f"send /unblock {target} on Telegram, or press Undo in the Actions Ledger."
    elif e.get("rollback"):
        undo = f"rollback available: {json.dumps(e['rollback'])}"
    else:
        undo = f"use Undo in the Actions Ledger ({UNDO.get(e['tool'], 'reverse the action')})."
    lines = [f"What: {what}", f"Why: {e['reasoning'] or 'see the incident reasoning'}"]
    if e["evidence"]:
        lines.append("Evidence: " + "; ".join(e["evidence"]))
    if e.get("expires_at"):
        lines.append(f"Expires: {e['expires_at']}")
    lines.append(f"Undo: {undo}")
    if e.get("case_url"):
        lines.append(f"Case: {e['case_url']}")
    subject = f"[{e['severity'].upper()}] Sentinel acted on incident {e['incident_id']}"
    return subject, subject + "\n" + "\n".join(lines)


# ---------- senders ----------
def http_post(url: str, payload: dict) -> int:
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


class Sender:
    name = "base"
    dry = False

    def send(self, subject: str, text: str, event: dict) -> None:  # raise on failure
        raise NotImplementedError


class DryRunSender(Sender):
    dry = True

    def __init__(self, name: str):
        self.name = name

    def send(self, subject, text, event):
        pass  # nothing is sent: the channel is not configured


class TelegramSender(Sender):
    name = "telegram"

    def __init__(self, token: str, chat_id: str, post: Callable = http_post):
        self.token, self.chat_id, self.post = token, chat_id, post

    def send(self, subject, text, event):
        self.post(f"https://api.telegram.org/bot{self.token}/sendMessage", {"chat_id": self.chat_id, "text": text})


class WebhookSender(Sender):
    name = "webhook"

    def __init__(self, url: str, post: Callable = http_post):
        self.url, self.post = url, post

    def send(self, subject, text, event):
        self.post(self.url, {"subject": subject, "text": text, "event": event})


class EmailSender(Sender):
    name = "email"

    def __init__(self, host, port, user, password, sender, to):
        self.host, self.port, self.user, self.password, self.sender, self.to = host, int(port), user, password, sender, to

    def send(self, subject, text, event):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, self.sender, self.to
        msg.set_content(text)
        with smtplib.SMTP(self.host, self.port, timeout=15) as s:
            s.starttls()
            s.login(self.user, self.password)
            s.send_message(msg)


def build_senders_from_env(env=os.environ) -> dict[str, Sender]:
    senders: dict[str, Sender] = {}
    senders["telegram"] = (TelegramSender(env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"])
                           if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID") else DryRunSender("telegram"))
    smtp = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO")
    senders["email"] = (EmailSender(env["SMTP_HOST"], env.get("SMTP_PORT", 587), env["SMTP_USER"], env["SMTP_PASSWORD"],
                                    env["SMTP_FROM"], env["SMTP_TO"]) if all(env.get(k) for k in smtp) else DryRunSender("email"))
    senders["webhook"] = WebhookSender(env["WEBHOOK_URL"]) if env.get("WEBHOOK_URL") else DryRunSender("webhook")
    return senders


# ---------- engine ----------
class NotificationEngine:
    def __init__(self, config: dict, senders: dict[str, Sender], log_path: Path = LOG_FILE,
                 now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep_fn: Callable[[float], None] = time.sleep):
        self.config, self.senders, self.log_path = config, senders, log_path
        self.now, self.sleep = now_fn, sleep_fn

    # --- log (delivery tracking) ---
    def _records(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, rec: dict) -> dict:
        rec["ts"] = self.now().isoformat()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    # --- routing ---
    def route(self, event: dict) -> tuple[list[str], bool]:
        sev = SEVERITY_RANK[event["severity"]]
        for rule in sorted(self.config["rules"], key=lambda r: -SEVERITY_RANK[r["min_severity"]]):
            if sev >= SEVERITY_RANK[rule["min_severity"]]:
                channels = list(rule["channels"])
                for extra in self.config.get("asset_overrides", {}).get(event.get("asset"), []):
                    if extra not in channels:
                        channels.append(extra)
                return channels, bool(rule.get("needs_ack"))
        return [], False

    # --- sending ---
    def _deliver(self, channel: str, subject: str, text: str, event: dict, kind: str, dedup_key: str, needs_ack: bool) -> dict:
        sender, attempts, error = self.senders[channel], 0, None
        for attempts in range(1, self.config["retries"] + 1):
            try:
                sender.send(subject, text, event)
                error = None
                break
            except Exception as exc:  # delivery must never crash the platform
                error = str(exc)
                if attempts < self.config["retries"]:
                    self.sleep(2 ** (attempts - 1))
        status = "failed" if error else ("dry_run" if sender.dry else "sent")
        return self._append({"kind": kind, "incident_id": event["incident_id"], "channel": channel, "status": status,
                             "attempts": attempts, "error": error, "dedup_key": dedup_key, "needs_ack": needs_ack})

    def _is_duplicate(self, dedup_key: str) -> bool:
        window = timedelta(seconds=self.config["dedup_window_seconds"])
        for r in self._records():
            if r["dedup_key"] == dedup_key and r["status"] in ("sent", "dry_run") \
                    and self.now() - datetime.fromisoformat(r["ts"]) < window:
                return True
        return False

    def notify(self, event: dict) -> list[dict]:
        channels, needs_ack = self.route(event)
        subject, text = build_message(event)
        target = event["args"].get("ip") or event["args"].get("username") or ""
        out = []
        for ch in channels:
            key = f"{event['incident_id']}|{event['tool']}|{target}|{ch}"
            if self._is_duplicate(key):
                out.append(self._append({"kind": "delivery", "incident_id": event["incident_id"], "channel": ch,
                                         "status": "duplicate", "attempts": 0, "error": None, "dedup_key": key,
                                         "needs_ack": needs_ack}))
            else:
                out.append(self._deliver(ch, subject, text, event, "delivery", key, needs_ack))
        return out

    # --- escalation ---
    def acknowledge(self, incident_id: str, by: str) -> None:
        self._append({"kind": "ack", "incident_id": incident_id, "by": by, "status": "ack", "dedup_key": "",
                      "channel": "", "attempts": 0, "error": None, "needs_ack": False})

    def check_escalations(self) -> list[dict]:
        """Send one more channel for every incident that needs acknowledgement and still has none."""
        records = self._records()
        acked = {r["incident_id"] for r in records if r["kind"] == "ack"}
        first: dict[str, dict] = {}
        for r in records:
            if r["kind"] == "delivery" and r["needs_ack"] and r["incident_id"] not in first:
                first[r["incident_id"]] = r
        chain, minutes = self.config["escalation"]["chain"], self.config["escalation"]["after_minutes"]
        out = []
        for inc, r in first.items():
            level = sum(1 for x in records if x["kind"] == "escalation" and x["incident_id"] == inc)
            waited = self.now() - datetime.fromisoformat(r["ts"])
            if inc in acked or level >= len(chain) or waited < timedelta(minutes=minutes * (level + 1)):
                continue
            ev = {"incident_id": inc, "severity": "critical", "tool": "escalation", "args": {}, "gate": "-",
                  "actor": "-", "status": "-", "reasoning": "", "evidence": []}
            text = (f"ESCALATION: incident {inc} has not been acknowledged for {int(waited.total_seconds() // 60)} minutes.")
            out.append(self._deliver(chain[level], text, text, ev, "escalation", f"{inc}|escalation|{level}", False))
        return out


def load_rules(path: Path = RULES_FILE) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    valid = {"telegram", "email", "webhook"}
    used = {c for r in cfg["rules"] for c in r["channels"]} | set(cfg["escalation"]["chain"])
    used |= {c for v in cfg.get("asset_overrides", {}).values() for c in v}
    if used - valid:
        raise ValueError(f"Unknown channel(s) in notification rules: {sorted(used - valid)}")
    return cfg


if __name__ == "__main__":
    engine = NotificationEngine(load_rules(), build_senders_from_env())
    sample = event_from_contract(
        {"incident_id": "INC-42", "tool": "block_ip", "status": "success", "verification": {"ok": True},
         "expires_at": "2026-11-03T15:30:00Z"},
        {"incident_id": "INC-42", "actor": "agent", "gate": "G2", "args": {"ip": "203.0.113.7", "ttl_minutes": 60}},
        {"severity": "critical", "reasoning": "Repeated failed logins from one IP, confirmed by ML and rate layers.",
         "evidence": ["ml:BruteForce p=0.97", "rate:203 req/10s"]}, {"asset": "skyline-web"}, "http://localhost/cases/INC-42")
    print(build_message(sample)[1], "\n")
    for _ in range(2):
        for r in engine.notify(sample):
            print(r["channel"], "->", r["status"])
    print("Delivery log:", LOG_FILE)
