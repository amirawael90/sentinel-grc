"""Shows that changing a policy changes the REAL playbook engine's behaviour (Mohamed's executor).

Usage:  python policy_demo.py --engine-path "C:\\path\\to\\soar-week1-2"
(clone https://github.com/ELNKLAWEY/soar-week1-2 first). The engine runs in dry-run mode only.
"""
import argparse
import copy
import sys
from pathlib import Path

from policies import load_policies

parser = argparse.ArgumentParser()
parser.add_argument("--engine-path", required=True, help="folder of the soar-week1-2 repo")
engine_root = Path(parser.parse_args().engine_path)
sys.path.insert(0, str(engine_root))

from common.schemas.actions import MAX_TTL_MINUTES  # noqa: E402
from executor.playbook_engine import PlaybookEngine  # noqa: E402

engine = PlaybookEngine()
playbook = engine.load(engine_root / "executor" / "playbooks" / "web_bruteforce_response.yaml")

# The one-line change Mohamed would make in his playbook: take the block time from the policy.
policy_driven = copy.deepcopy(playbook)
for step in policy_driven["steps"]:
    if step["id"] == "contain":
        step["args"]["ttl_minutes"] = "{{ policy.bruteforce_block_ttl_minutes }}"

incident = {"incident": {"src_ip": "203.0.113.7"}, "decide": {"verdict": "true_positive", "target_user": "alice"}}


def run_with(lib, label):
    ctx = {**incident, **lib.playbook_context("web_bruteforce_response")}
    contain = {s.id: s for s in engine.run(policy_driven, ctx, dry_run=True).steps}["contain"]
    ttl = int(contain.args["ttl_minutes"])
    gate = next((g.value for g, m in MAX_TTL_MINUTES.items() if m >= ttl), "none")
    print(f"{label}: block {contain.args['ip']} for {ttl} minutes (needs gate {gate} or higher)")


lib = load_policies()
run_with(lib, "Policy says 24h ")
lib.policies[0].drives[0].value = 720
run_with(lib, "Policy edited 12h")
lib.policies[0].approval_status = "Draft"
ctx = {**incident, **lib.playbook_context("web_bruteforce_response")}
print("Policy back to Draft: parameters ->", ctx["policy"], "(a Draft policy has no effect)")
