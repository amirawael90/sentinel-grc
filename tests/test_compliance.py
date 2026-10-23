import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from compliance import compute, effective_status, gaps, quick_wins  # noqa: E402
from control_library import Control  # noqa: E402


def make(id, status="Not implemented", features=None, weight=1.0, function="F", category="C", fw="X"):
    return Control(id=id, framework=fw, function=function, category=category, category_id=category,
                   description="d", status=status, maturity=0, weight=weight,
                   platform_features=features or [])


def test_formula_and_weights():
    controls = [make("a", "Implemented", weight=3), make("b", "Partial", weight=1), make("c")]
    # (1*3 + 0.5*1 + 0*1) / 5 = 70%
    assert compute(controls, {}, {})["X"]["percent"] == 70.0


def test_not_applicable_is_excluded():
    controls = [make("a", "Implemented"), make("b", "Not applicable")]
    assert compute(controls, {}, {})["X"]["percent"] == 100.0


def test_status_derived_from_features():
    c = make("a", features=["f1", "f2"])
    assert effective_status(c, {"f1": "built", "f2": "built"}, {}) == "Implemented"
    assert effective_status(c, {"f1": "built", "f2": "planned"}, {}) == "Partial"
    assert effective_status(c, {"f1": "in_progress", "f2": "planned"}, {}) == "Partial"
    assert effective_status(c, {}, {}) == "Not implemented"


def test_manual_status_can_only_raise():
    c = make("a", "Implemented", features=["f1"])
    assert effective_status(c, {"f1": "planned"}, {}) == "Implemented"


def test_override_wins():
    c = make("a", features=["f1"])
    assert effective_status(c, {"f1": "built"}, {"a": "Not applicable"}) == "Not applicable"


def test_per_function_percent():
    controls = [make("a", "Implemented", function="Detect"), make("b", function="Protect")]
    r = compute(controls, {}, {})["X"]["functions"]
    assert r == {"Detect": 100.0, "Protect": 0.0}


def test_gaps_rank_by_points_lost():
    controls = [make("a", category="Big"), make("b", category="Big"), make("c", category="Small"),
                make("d", "Implemented", category="Done")]
    ranked = gaps(controls, {}, {})
    assert ranked[0]["category"] == "Big" and ranked[0]["points_lost"] == 2.0
    assert all(g["category"] != "Done" for g in ranked)


def test_quick_wins_nearest_first():
    controls = [make("far", features=["f1", "f2"]), make("near", features=["f1"]), make("none")]
    wins = quick_wins(controls, {"f1": "planned", "f2": "planned"}, {})
    assert [w["id"] for w in wins] == ["near", "far"]
