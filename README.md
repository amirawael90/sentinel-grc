# grc/ - Compliance (Amira, tasks Z1-Z10)

## Z1 Control library
- Data: `data/controls/*.yaml` (NIST CSF 2.0 = 106 controls, OWASP Top 10:2025 = 10, CIS v8.1.2 = 153, ISO 27001 = 93).
- Loader: `control_library.py` (validates every control with pydantic).
- Run: `pip install pydantic pyyaml pytest` then `python control_library.py`
- Test: `python -m pytest`
- NIST data source: official CSF 2.0 Reference Tool export (JSON); withdrawn subcategories excluded.
- `platform_features` mapping is by category and still needs team review.
- CIS Controls v8.1.2 (March 2025), 153 safeguards: text copied unchanged from the official CIS workbook (CC BY-NC-ND 4.0, cite "CIS Controls v8.1, Center for Internet Security").
- ISO/IEC 27001:2022 Annex A, 93 controls: titles only (official text is paid). Titles must be verified against the standard before the final report.

## Z2 Compliance scoring
- `compliance.py`: percent per framework and per function, biggest gaps, quick wins, daily snapshot (`--save`).
- Formula: sum(score x weight) / sum(weight) x 100 (Implemented 1, Partial 0.5, Not implemented 0, Not applicable excluded).
- A control's status comes from the build state of its platform features: `data/feature_status.yaml` (planned / in_progress / built). Update it as teammates finish components.
- Manual decisions go in `data/status_overrides.yaml`.
- Run: `python compliance.py` and `python -m pytest`

## Z3 Automatic evidence collector
- `evidence.py`: hashes (SHA-256) the files listed in `data/evidence_sources.yaml`, stores timestamps, source and linked controls in `data/evidence/evidence.json`.
- Stale detection: evidence older than the source's `max_age_days` is "stale"; controls show fresh / stale / no_evidence counts.
- `python evidence.py` collects; `python evidence.py --verify` re-hashes every file to detect tampering.
- `sample_sources/` is SAMPLE data. Point `data/evidence_sources.yaml` at the real outputs of the rule engine, HAProxy, audit stream, executor and pentest module.

## Z4 Policy library
- `data/policies.yaml`: policies with version, owner, approval status, review date, acknowledgements, linked controls and the playbook parameters they drive. Exceptions override one parameter until they expire.
- `policies.py`: loads and validates; `playbook_context(name)` returns `{"policy": {...}}` for the playbook engine, so a playbook reads `{{ policy.<parameter> }}`. Only Approved policies take effect.
- `policy_demo.py --engine-path <soar-week1-2 folder>`: runs Mohamed's real playbook engine (dry-run) and shows that editing the policy changes the block time.
- Needs from Mohamed (M1): in `web_bruteforce_response.yaml` use `ttl_minutes: "{{ policy.bruteforce_block_ttl_minutes }}"` and pass `PolicyLibrary.playbook_context(...)` into the run context.

## Z5 Remediation tracker
- `remediation.py`: tasks from pentest findings (due date by severity) and from the biggest compliance gaps; owner, priority, due date, status (Open / In progress / Awaiting retest / Closed).
- A finding task closes ONLY when a retest confirms the fix (`process_retest`): fixed -> Closed, remaining -> back to In progress, new -> new task. Gap tasks close when the compliance score no longer loses points in that category.
- Overdue tasks: `risk_signals()` gives per-asset overdue counts for the risk job (Rawda W4); `metrics()` gives open / overdue / closed / mean days to remediate for the KRI endpoint (Rawda W5).
- Input contract (Finding record, Omar): id, title, endpoint, cwe, severity, status, evidence, optional asset. Today it reads `data/mock/findings.json` (SAMPLE); replace `load_findings()` with the real source.
- Rules (due days, default owner) are in `data/remediation_config.yaml`.
- Run: `python remediation.py --reset`, then `python remediation.py --retest data/mock/retest.json`