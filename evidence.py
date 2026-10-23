"""Automatic evidence collector (task Z3).

Evidence = a file or export that proves a control works (rules in force, config
snapshot, audit log, executed actions, scan report). For each item we store a
SHA-256 hash, timestamps, the source and the controls it supports.

Sources are listed in data/evidence_sources.yaml. Today they point at sample files;
when teammates' components exist, point them at the real outputs.

Usage:  python evidence.py            collect, then print a summary
        python evidence.py --verify   re-hash every stored file and report tampering
"""
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel

from control_library import load_controls

BASE = Path(__file__).parent
SOURCES_FILE = BASE / "data" / "evidence_sources.yaml"
STORE_FILE = BASE / "data" / "evidence" / "evidence.json"


class Evidence(BaseModel):
    id: str  # sha256 of source + path + content hash
    source: str
    path: str
    sha256: str
    size: int
    first_collected_at: datetime
    last_verified_at: datetime
    max_age_days: int
    linked_controls: list[str]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sources(path: Path = SOURCES_FILE, known_controls: set[str] | None = None) -> list[dict]:
    sources = yaml.safe_load(path.read_text(encoding="utf-8"))["sources"]
    if known_controls is not None:
        for s in sources:
            unknown = [c for c in s["controls"] if c not in known_controls]
            if unknown:
                raise ValueError(f"Source '{s['name']}' links unknown control(s): {unknown}")
    return sources


def load_store(path: Path = STORE_FILE) -> dict[str, Evidence]:
    if not path.exists():
        return {}
    return {k: Evidence(**v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def save_store(store: dict[str, Evidence], path: Path = STORE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: json.loads(v.model_dump_json()) for k, v in store.items()}, indent=2),
                    encoding="utf-8")


def collect(sources: list[dict], store: dict[str, Evidence], base: Path = BASE,
            now: datetime | None = None) -> dict[str, Evidence]:
    """Hash every file of every source. Unchanged content is refreshed; changed content is a new item."""
    now = now or datetime.now(timezone.utc)
    for s in sources:
        for file in sorted((base / s["path"]).glob(s.get("pattern", "*"))):
            if not file.is_file():
                continue
            digest = sha256_of(file)
            rel = file.relative_to(base).as_posix()
            eid = hashlib.sha256(f"{s['name']}|{rel}|{digest}".encode()).hexdigest()[:16]
            if eid in store:
                store[eid].last_verified_at = now
            else:
                store[eid] = Evidence(id=eid, source=s["name"], path=rel, sha256=digest,
                                      size=file.stat().st_size, first_collected_at=now,
                                      last_verified_at=now, max_age_days=s["max_age_days"],
                                      linked_controls=s["controls"])
    return store


def is_stale(e: Evidence, now: datetime) -> bool:
    return now - e.last_verified_at > timedelta(days=e.max_age_days)


def summary_per_control(controls_ids: list[str], store: dict[str, Evidence], now: datetime | None = None) -> dict:
    """For each control: fresh count, stale count and a state (no_evidence | fresh | stale)."""
    now = now or datetime.now(timezone.utc)
    result = {cid: {"fresh": 0, "stale": 0, "state": "no_evidence"} for cid in controls_ids}
    for e in store.values():
        for cid in e.linked_controls:
            if cid in result:
                result[cid]["stale" if is_stale(e, now) else "fresh"] += 1
    for r in result.values():
        if r["fresh"]:
            r["state"] = "fresh"
        elif r["stale"]:
            r["state"] = "stale"
    return result


def verify(store: dict[str, Evidence], base: Path = BASE) -> list[str]:
    """Return the evidence items whose file is missing or no longer matches its stored hash."""
    problems = []
    for e in store.values():
        f = base / e.path
        if not f.exists():
            problems.append(f"{e.path}: file missing")
        elif sha256_of(f) != e.sha256:
            problems.append(f"{e.path}: content changed since collection")
    return problems


if __name__ == "__main__":
    controls = load_controls()
    ids = [c.id for c in controls]
    store = load_store()
    if "--verify" in sys.argv:
        problems = verify(store)
        print("All evidence intact" if not problems else "\n".join(problems))
        sys.exit(1 if problems else 0)
    store = collect(load_sources(known_controls=set(ids)), store)
    save_store(store)
    s = summary_per_control(ids, store)
    states = [r["state"] for r in s.values()]
    print(f"Evidence items: {len(store)}")
    print(f"Controls with fresh evidence: {states.count('fresh')} | stale: {states.count('stale')} "
          f"| none: {states.count('no_evidence')}")
