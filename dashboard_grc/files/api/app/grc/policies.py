"""Policy library (task Z4): policies that execute.

A policy is a governance document (owner, version, approval, review date) that also
carries the value of one or more playbook parameters. The playbook reads it as
{{ policy.<parameter> }}, so changing the policy changes what the platform does.
Only APPROVED policies take effect; exceptions override a value until they expire.

Usage: python policies.py     print policy status and the parameters per playbook
"""
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel

POLICIES_FILE = Path(__file__).parent / "data" / "policies.yaml"


class Drive(BaseModel):
    playbook: str
    parameter: str
    value: Any


class Acknowledgement(BaseModel):
    user: str
    date: date


class Policy(BaseModel):
    id: str
    title: str
    version: str
    owner: str = "TBD"
    approval_status: Literal["Draft", "Approved", "Retired"]
    approved_by: Optional[str] = None
    approved_on: Optional[date] = None
    review_date: date
    acknowledgements: list[Acknowledgement] = []
    drives: list[Drive] = []
    linked_controls: list[str] = []


class PolicyException(BaseModel):
    id: str
    policy_id: str
    parameter: str
    value: Any
    reason: str
    approver: str
    expires_on: date


class PolicyLibrary(BaseModel):
    policies: list[Policy]
    exceptions: list[PolicyException] = []

    def parameters(self, playbook: str, today: Optional[date] = None) -> dict[str, Any]:
        """Parameter values for a playbook: approved policies first, active exceptions on top."""
        today = today or date.today()
        params: dict[str, Any] = {}
        for p in self.policies:
            if p.approval_status == "Approved":
                for d in p.drives:
                    if d.playbook == playbook:
                        params[d.parameter] = d.value
        for e in self.exceptions:
            if e.expires_on >= today and e.parameter in params:
                params[e.parameter] = e.value
        return params

    def playbook_context(self, playbook: str, today: Optional[date] = None) -> dict[str, Any]:
        """The extra context for the playbook engine: {{ policy.xxx }}."""
        return {"policy": self.parameters(playbook, today)}

    def overdue_reviews(self, today: Optional[date] = None) -> list[Policy]:
        today = today or date.today()
        return [p for p in self.policies if p.approval_status != "Retired" and p.review_date < today]

    def expired_exceptions(self, today: Optional[date] = None) -> list[PolicyException]:
        today = today or date.today()
        return [e for e in self.exceptions if e.expires_on < today]

    def acknowledge(self, policy_id: str, user: str, today: Optional[date] = None) -> None:
        policy = next(p for p in self.policies if p.id == policy_id)
        if not any(a.user == user for a in policy.acknowledgements):
            policy.acknowledgements.append(Acknowledgement(user=user, date=today or date.today()))


def load_policies(path: Path = POLICIES_FILE, known_controls: Optional[set[str]] = None) -> PolicyLibrary:
    lib = PolicyLibrary(**yaml.safe_load(path.read_text(encoding="utf-8")))
    ids = [p.id for p in lib.policies]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate policy ids")
    for e in lib.exceptions:
        if e.policy_id not in ids:
            raise ValueError(f"Exception {e.id} refers to unknown policy {e.policy_id}")
    if known_controls is not None:
        for p in lib.policies:
            unknown = [c for c in p.linked_controls if c not in known_controls]
            if unknown:
                raise ValueError(f"Policy {p.id} links unknown control(s): {unknown}")
    return lib


def save_policies(lib: PolicyLibrary, path: Path = POLICIES_FILE) -> None:
    data = yaml.safe_load(lib.model_dump_json())  # JSON round-trip turns dates into strings
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


if __name__ == "__main__":
    from control_library import load_controls

    lib = load_policies(known_controls={c.id for c in load_controls()})
    for p in lib.policies:
        print(f"{p.id} v{p.version} [{p.approval_status}] review {p.review_date}: {p.title}")
    for pb in sorted({d.playbook for p in lib.policies for d in p.drives}):
        print(f"  {pb}: {lib.parameters(pb)}")
    print("Overdue reviews:", len(lib.overdue_reviews()), "| expired exceptions:", len(lib.expired_exceptions()))
