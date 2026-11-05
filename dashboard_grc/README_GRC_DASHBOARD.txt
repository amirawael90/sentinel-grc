GRC pages for the Sentinel dashboard (Amira): Z8 + Z9 in one package

Pages (menu group "GRC"):  Compliance Center, Policy Library, Evidence & Audit, Reports

1) Get Mostafa's repo:  git clone https://github.com/eng-ghalwash/sentinel-task7.git
2) Unzip this folder anywhere (NOT inside the repo), then run:
      python apply_grc_dashboard.py PATH_TO\sentinel-task7
   Safe to run again, also if you already ran the older apply_z8.py: code files are refreshed, but your data
   (api/app/grc/data and sample_sources: feature status, policies, audit log) is never overwritten.
3) Install the new dependency and restart the API:
      cd api  ->  pip install -r requirements.txt  ->  uvicorn app.main:app --reload --port 8000
   Frontend:  cd frontend  ->  npm install  ->  npm run dev
4) API tests:  cd api  ->  pip install pytest httpx  ->  python -m pytest tests     (15 tests)

What it adds
  api/app/routers/grc.py        /api/grc/ compliance, controls, policies, evidence (+verify), audit (+verify, export, import), reports
  api/app/grc/                  copy of the GRC core (github.com/amirawael90/sentinel-grc); set GRC_DIR to use another copy
  frontend/src/pages/           ComplianceCenterPage, PolicyLibraryPage, EvidenceAuditPage, ReportsPage (+ small shared files)
  api/requirements.txt          adds reportlab (PDF reports)
  .gitignore                    ignores generated reports and the evidence store

Roles: Admin, Analyst and Auditor can view and export. Only Admin and Analyst can collect evidence, acknowledge a
policy, import the executor audit or generate reports. Client has no access. Every write is recorded in the audit log.

Audit log: hash-chained (each entry stores the previous entry's hash). "Verify chain" reports the first broken entry.
Limit: deleting the LAST entries cannot be detected from the file alone; keep the head hash and entry count.
Sample data: entries flagged "sample" (and the incidents/risks in reports) are demo data until the other components write real ones.
