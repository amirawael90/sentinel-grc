import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from notifications import (DryRunSender, NotificationEngine, Sender, TelegramSender, WebhookSender,  # noqa: E402
                           build_message, build_senders_from_env, event_from_contract, load_rules)

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
CFG = {"rules": [{"min_severity": "critical", "channels": ["telegram", "email", "webhook"], "needs_ack": True},
                 {"min_severity": "high", "channels": ["telegram", "email"], "needs_ack": True},
                 {"min_severity": "medium", "channels": ["telegram"], "needs_ack": False},
                 {"min_severity": "low", "channels": [], "needs_ack": False}],
       "asset_overrides": {"db": ["email"]}, "dedup_window_seconds": 300, "retries": 3,
       "escalation": {"after_minutes": 15, "chain": ["email", "webhook"]}}


class Fake(Sender):
    def __init__(self, name, fail_times=0):
        self.name, self.fail_times, self.sent = name, fail_times, []

    def send(self, subject, text, event):
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("boom")
        self.sent.append(text)


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


def event(severity="critical", asset=None, incident="INC-1", ip="1.2.3.4"):
    return event_from_contract(
        {"incident_id": incident, "tool": "block_ip", "status": "success", "verification": {"ok": True},
         "expires_at": "2026-11-01T13:00:00Z"},
        {"incident_id": incident, "actor": "agent", "gate": "G2", "args": {"ip": ip, "ttl_minutes": 60}},
        {"severity": severity, "reasoning": "Repeated failed logins.", "evidence": ["ml:BruteForce p=0.97"]},
        {"asset": asset})


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    senders = {n: Fake(n) for n in ("telegram", "email", "webhook")}
    engine = NotificationEngine(CFG, senders, tmp_path / "log.jsonl", clock, lambda s: None)
    return engine, senders, clock


def test_message_says_what_why_and_how_to_undo():
    subject, text = build_message(event())
    assert "block_ip" in text and "ip=1.2.3.4" in text and "verified" in text
    assert "Why: Repeated failed logins." in text
    assert "/unblock 1.2.3.4" in text and "Undo" in text
    assert subject.startswith("[CRITICAL]")


def test_routing_by_severity(env):
    engine, _, _ = env
    assert engine.route(event("critical")) == (["telegram", "email", "webhook"], True)
    assert engine.route(event("medium")) == (["telegram"], False)
    assert engine.route(event("low")) == ([], False)


def test_asset_override_adds_channel(env):
    engine, _, _ = env
    assert engine.route(event("medium", asset="db"))[0] == ["telegram", "email"]


def test_duplicate_within_window_is_not_sent_twice(env):
    engine, senders, clock = env
    engine.notify(event("medium"))
    second = engine.notify(event("medium"))
    assert second[0]["status"] == "duplicate" and len(senders["telegram"].sent) == 1
    clock.t += timedelta(seconds=301)
    assert engine.notify(event("medium"))[0]["status"] == "sent"


def test_different_target_is_not_duplicate(env):
    engine, senders, _ = env
    engine.notify(event("medium", ip="1.1.1.1"))
    engine.notify(event("medium", ip="2.2.2.2"))
    assert len(senders["telegram"].sent) == 2


def test_retry_then_success(env):
    engine, senders, _ = env
    senders["telegram"].fail_times = 2
    rec = engine.notify(event("medium"))[0]
    assert rec["status"] == "sent" and rec["attempts"] == 3


def test_failure_is_recorded_and_other_channels_still_sent(env):
    engine, senders, _ = env
    senders["email"].fail_times = 99
    recs = {r["channel"]: r for r in engine.notify(event("critical"))}
    assert recs["email"]["status"] == "failed" and recs["email"]["error"] == "boom"
    assert recs["telegram"]["status"] == "sent" and recs["webhook"]["status"] == "sent"


def test_unconfigured_channel_is_dry_run_not_sent(tmp_path):
    engine = NotificationEngine(CFG, build_senders_from_env({}), tmp_path / "l.jsonl", Clock(), lambda s: None)
    assert {r["status"] for r in engine.notify(event("critical"))} == {"dry_run"}


def test_escalation_goes_through_the_chain(env):
    engine, senders, clock = env
    engine.notify(event("critical"))
    assert engine.check_escalations() == []
    clock.t += timedelta(minutes=15)
    first = engine.check_escalations()
    assert [r["channel"] for r in first] == ["email"]
    assert engine.check_escalations() == []            # next step needs another 15 minutes
    clock.t += timedelta(minutes=15)
    assert [r["channel"] for r in engine.check_escalations()] == ["webhook"]
    clock.t += timedelta(minutes=60)
    assert engine.check_escalations() == []            # chain finished
    assert "ESCALATION" in senders["webhook"].sent[-1]


def test_acknowledged_incident_does_not_escalate(env):
    engine, _, clock = env
    engine.notify(event("critical"))
    engine.acknowledge("INC-1", "amira")
    clock.t += timedelta(hours=2)
    assert engine.check_escalations() == []


def test_medium_does_not_escalate(env):
    engine, _, clock = env
    engine.notify(event("medium"))
    clock.t += timedelta(hours=2)
    assert engine.check_escalations() == []


def test_telegram_and_webhook_payloads():
    calls = []
    TelegramSender("TOKEN", "42", lambda url, p: calls.append((url, p))).send("s", "hello", {})
    WebhookSender("http://x/hook", lambda url, p: calls.append((url, p))).send("s", "hello", {"a": 1})
    assert calls[0] == ("https://api.telegram.org/botTOKEN/sendMessage", {"chat_id": "42", "text": "hello"})
    assert calls[1][0] == "http://x/hook" and calls[1][1]["event"] == {"a": 1}


def test_real_rules_file_is_valid():
    cfg = load_rules()
    assert cfg["dedup_window_seconds"] > 0 and isinstance(DryRunSender("x"), Sender)
