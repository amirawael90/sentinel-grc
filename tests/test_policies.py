import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from policies import Policy, PolicyException, PolicyLibrary, load_policies  # noqa: E402

TODAY = date(2026, 11, 1)


def lib(status="Approved", exceptions=None, review=date(2027, 1, 1)):
    p = Policy(id="P1", title="t", version="1", approval_status=status, review_date=review,
               drives=[{"playbook": "pb", "parameter": "ttl", "value": 1440}])
    return PolicyLibrary(policies=[p], exceptions=exceptions or [])


def test_approved_policy_drives_playbook():
    assert lib().playbook_context("pb", TODAY) == {"policy": {"ttl": 1440}}


def test_draft_policy_has_no_effect():
    assert lib("Draft").parameters("pb", TODAY) == {}


def test_other_playbook_not_affected():
    assert lib().parameters("other", TODAY) == {}


def test_changing_policy_changes_parameter():
    library = lib()
    library.policies[0].drives[0].value = 720
    assert library.parameters("pb", TODAY)["ttl"] == 720


def test_exception_overrides_until_it_expires():
    exc = PolicyException(id="E1", policy_id="P1", parameter="ttl", value=60, reason="pentest",
                          approver="x", expires_on=date(2026, 11, 5))
    library = lib(exceptions=[exc])
    assert library.parameters("pb", TODAY)["ttl"] == 60
    assert library.parameters("pb", date(2026, 11, 6))["ttl"] == 1440
    assert library.expired_exceptions(date(2026, 11, 6)) == [exc]


def test_overdue_reviews():
    assert lib(review=date(2026, 10, 1)).overdue_reviews(TODAY)[0].id == "P1"
    assert lib().overdue_reviews(TODAY) == []


def test_acknowledgement_is_recorded_once():
    library = lib()
    library.acknowledge("P1", "amira", TODAY)
    library.acknowledge("P1", "amira", TODAY)
    assert len(library.policies[0].acknowledgements) == 1


def test_real_file_is_valid_and_links_existing_controls():
    from control_library import load_controls
    library = load_policies(known_controls={c.id for c in load_controls()})
    assert library.parameters("web_bruteforce_response")["bruteforce_block_ttl_minutes"] == 1440


def test_unknown_policy_in_exception_is_rejected(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("policies: []\nexceptions:\n  - {id: E, policy_id: NOPE, parameter: x, value: 1, reason: r, approver: a, expires_on: 2027-01-01}\n")
    with pytest.raises(ValueError):
        load_policies(f)
