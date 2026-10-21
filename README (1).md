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