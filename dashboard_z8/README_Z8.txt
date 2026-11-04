Z8 - Compliance Center and Policy Library for the Sentinel dashboard (Amira)

1) Get Mostafa's repo:   git clone https://github.com/eng-ghalwash/sentinel-task7.git
2) Unzip this folder anywhere, then run:
      python apply_z8.py PATH_TO\sentinel-task7
   (copies the new files and adds a few lines to api/app/main.py, frontend/src/App.tsx, frontend/src/layout/nav.ts.
    Safe to run twice.)
3) Run the dashboard (see Mostafa's README): the API in /api, the frontend in /frontend.
   New menu group "GRC" -> Compliance Center, Policy Library.
4) API tests:  cd api  ->  pip install pytest httpx  ->  python -m pytest tests

What it adds
  api/app/routers/grc.py      endpoints /api/grc/compliance, /controls, /policies, /policies/{id}/acknowledge, /evidence/collect
  api/app/grc/                copy of the GRC core (github.com/amirawael90/sentinel-grc). Set GRC_DIR to use another copy.
  frontend/src/pages/ComplianceCenterPage.tsx, PolicyLibraryPage.tsx, components/Gauge.tsx, grcTypes.ts, grcUtils.ts
  api/tests/test_grc_api.py   7 tests (login required, roles, paging, filters, evidence collection)

Roles: Admin, Analyst and Auditor can view. Only Admin and Analyst can collect evidence or acknowledge a policy.
Data: read from files on every request, so the pages update when feature status, policies or evidence change.
