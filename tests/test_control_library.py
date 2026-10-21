import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from control_library import by_framework, gaps, load_controls  # noqa: E402


@pytest.fixture(scope="module")
def controls():
    return load_controls()


def test_at_least_80_controls(controls):
    assert len(controls) >= 80


def test_ids_are_unique(controls):
    ids = [c.id for c in controls]
    assert len(ids) == len(set(ids))


def test_frameworks_present(controls):
    fw = by_framework(controls)
    assert "NIST_CSF_2.0" in fw
    assert "OWASP_TOP10_2025" in fw


def test_nist_has_106_subcategories(controls):
    assert len(by_framework(controls)["NIST_CSF_2.0"]) == 106


def test_owasp_has_10_categories(controls):
    assert len(by_framework(controls)["OWASP_TOP10_2025"]) == 10


def test_cis_has_153_safeguards(controls):
    assert len(by_framework(controls)["CIS_V8_1"]) == 153


def test_iso_has_93_controls(controls):
    assert len(by_framework(controls)["ISO27001_2022"]) == 93


def test_gaps_are_the_organisational_ones(controls):
    gap_categories = {c.category_id for c in gaps(controls)}
    assert {"GV.OC", "GV.SC", "PR.AT", "A03", "CIS-9", "CIS-12", "CIS-14", "CIS-15"} <= gap_categories