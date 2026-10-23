"""Compliance scoring (task Z2).

framework_pct = sum(control_score * weight) / sum(weight) * 100
control_score: Implemented 1.0 | Partial 0.5 | Not implemented 0.0
Controls marked "Not applicable" are excluded.

A control's status is calculated from the build state of the platform
features that cover it (data/feature_status.yaml). A manual status in the
control file can only raise it; data/status_overrides.yaml beats everything.

Usage:  python compliance.py            print the scores
        python compliance.py --save     also store a daily snapshot (JSON)
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

from control_library import Control, load_controls

DATA = Path(__file__).parent / "data"
SCORE = {"Implemented": 1.0, "Partial": 0.5, "Not implemented": 0.0}
FEATURE_VALUE = {"built": 1.0, "in_progress": 0.5, "planned": 0.0}
STATUS_FROM_SCORE = {1.0: "Implemented", 0.5: "Partial", 0.0: "Not implemented"}


def _load_map(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_feature_status(path: Path = DATA / "feature_status.yaml") -> dict[str, str]:
    status = _load_map(path)
    bad = {k: v for k, v in status.items() if v not in FEATURE_VALUE}
    if bad:
        raise ValueError(f"Unknown feature state(s): {bad}")
    return status


def load_overrides(path: Path = DATA / "status_overrides.yaml") -> dict[str, str]:
    return _load_map(path)


def effective_status(c: Control, features: dict[str, str], overrides: dict[str, str]) -> str:
    if c.id in overrides:
        return overrides[c.id]
    if c.status == "Not applicable":
        return c.status
    derived = 0.0
    if c.platform_features:
        values = [FEATURE_VALUE[features.get(f, "planned")] for f in c.platform_features]
        coverage = sum(values) / len(values)
        derived = 1.0 if coverage >= 1 else 0.5 if coverage > 0 else 0.0
    return STATUS_FROM_SCORE[max(derived, SCORE[c.status])]


def _percent(rows: list[tuple[float, float]]) -> float | None:
    total = sum(w for _, w in rows)
    return None if total == 0 else round(sum(s * w for s, w in rows) / total * 100, 1)


def compute(controls: list[Control], features: dict[str, str], overrides: dict[str, str]) -> dict:
    """Percent per framework and per function, plus status counts."""
    result: dict = {}
    for fw in sorted({c.framework for c in controls}):
        items = [(c, effective_status(c, features, overrides)) for c in controls if c.framework == fw]
        scored = [(SCORE[s], c.weight) for c, s in items if s in SCORE]
        counts = defaultdict(int)
        for _, s in items:
            counts[s] += 1
        by_function: dict[str, list] = defaultdict(list)
        for c, s in items:
            if s in SCORE:
                by_function[c.function or "All"].append((SCORE[s], c.weight))
        result[fw] = {
            "percent": _percent(scored),
            "counts": dict(counts),
            "functions": {f: _percent(r) for f, r in sorted(by_function.items())},
        }
    return result


def gaps(controls: list[Control], features: dict, overrides: dict, top: int = 10) -> list[dict]:
    """Categories that lose the most points (the 'biggest gaps')."""
    lost: dict[tuple, float] = defaultdict(float)
    for c in controls:
        s = effective_status(c, features, overrides)
        if s in SCORE:
            lost[(c.framework, c.category)] += (1 - SCORE[s]) * c.weight
    ranked = sorted(lost.items(), key=lambda kv: -kv[1])[:top]
    return [{"framework": fw, "category": cat, "points_lost": round(v, 1)} for (fw, cat), v in ranked if v > 0]


def quick_wins(controls: list[Control], features: dict, overrides: dict, top: int = 10) -> list[dict]:
    """Controls a platform feature already covers; finishing the fewest unbuilt features first."""
    wins = []
    for c in controls:
        s = effective_status(c, features, overrides)
        if s in SCORE and SCORE[s] < 1 and c.platform_features:
            missing = [f for f in c.platform_features if features.get(f, "planned") != "built"]
            wins.append({"id": c.id, "status": s, "missing_features": missing})
    wins.sort(key=lambda w: (len(w["missing_features"]), w["id"]))
    return wins[:top]


def save_snapshot(report: dict, directory: Path = DATA / "snapshots") -> Path:
    """Store today's result (one file per day). The team's database can replace this later."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"compliance_{date.today().isoformat()}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def build_report() -> dict:
    controls, features, overrides = load_controls(), load_feature_status(), load_overrides()
    return {
        "date": date.today().isoformat(),
        "frameworks": compute(controls, features, overrides),
        "biggest_gaps": gaps(controls, features, overrides),
        "quick_wins": quick_wins(controls, features, overrides),
    }


if __name__ == "__main__":
    report = build_report()
    for fw, r in report["frameworks"].items():
        print(f"{fw}: {r['percent']}%  {r['counts']}")
    print("Quick wins:", [w["id"] for w in report["quick_wins"][:5]])
    if "--save" in sys.argv:
        print("Saved:", save_snapshot(report))
