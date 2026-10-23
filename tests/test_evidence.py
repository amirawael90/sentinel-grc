import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from evidence import collect, is_stale, load_sources, summary_per_control, verify  # noqa: E402

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "a.log").write_text("one")
    sources = [{"name": "logs", "path": "logs", "pattern": "*.log", "max_age_days": 7, "controls": ["C1", "C2"]}]
    return tmp_path, sources


def test_collect_stores_hash_and_links(env):
    base, sources = env
    store = collect(sources, {}, base, T0)
    e = next(iter(store.values()))
    assert len(store) == 1 and len(e.sha256) == 64 and e.linked_controls == ["C1", "C2"]


def test_recollecting_same_file_adds_nothing_but_refreshes(env):
    base, sources = env
    store = collect(sources, {}, base, T0)
    store = collect(sources, store, base, T0 + timedelta(days=3))
    e = next(iter(store.values()))
    assert len(store) == 1
    assert e.first_collected_at == T0 and e.last_verified_at == T0 + timedelta(days=3)


def test_changed_file_becomes_new_item(env):
    base, sources = env
    store = collect(sources, {}, base, T0)
    (base / "logs" / "a.log").write_text("two")
    assert len(collect(sources, store, base, T0)) == 2


def test_stale_detection(env):
    base, sources = env
    store = collect(sources, {}, base, T0)
    e = next(iter(store.values()))
    assert not is_stale(e, T0 + timedelta(days=6))
    assert is_stale(e, T0 + timedelta(days=8))
    s = summary_per_control(["C1", "C3"], store, T0 + timedelta(days=8))
    assert s["C1"]["state"] == "stale" and s["C3"]["state"] == "no_evidence"


def test_summary_counts_fresh(env):
    base, sources = env
    store = collect(sources, {}, base, T0)
    assert summary_per_control(["C1"], store, T0)["C1"] == {"fresh": 1, "stale": 0, "state": "fresh"}


def test_verify_detects_tampering_and_missing(env):
    base, sources = env
    store = collect(sources, {}, base, T0)
    assert verify(store, base) == []
    (base / "logs" / "a.log").write_text("tampered")
    assert "content changed" in verify(store, base)[0]
    (base / "logs" / "a.log").unlink()
    assert "missing" in verify(store, base)[0]


def test_unknown_control_in_config_is_rejected(tmp_path):
    cfg = tmp_path / "s.yaml"
    cfg.write_text("sources:\n  - {name: x, path: p, max_age_days: 1, controls: [NOPE]}\n")
    with pytest.raises(ValueError):
        load_sources(cfg, known_controls={"C1"})


def test_real_config_only_links_existing_controls():
    from control_library import load_controls
    load_sources(known_controls={c.id for c in load_controls()})
