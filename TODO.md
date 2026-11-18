# Project checklist

## Phases
- [x] 1. Workspace inspection and project structure
- [x] 2. Synthetic SCADA dataset (10 turbines, 181 days, 260 534 rows, scenario log)
- [x] 3. Data processing & validation (12 checks, quarantine, quality report JSON/MD)
- [x] 4. Engineering calculations (energy, availability ×3 bases, CF, deviation, downtime, power curve)
- [x] 5. Anomaly detection (6 methods incl. Isolation Forest, explainable records)
- [x] 6. SQL database (8 tables, unique constraints, indexes, idempotent inserts, 12 verified queries)
- [x] 7. FastAPI backend (all 18 required endpoints + status, temperature, imports, quality, months)
- [x] 8. React dashboard (8 pages, filters, loading/empty/error states, live API data)
- [x] 9. Excel / PDF / CSV monthly reporting
- [x] 10. Power BI datasets, DAX measures, import + layout guide
- [x] 11. Automated tests – 90 passed (docs/test_results.txt)
- [x] 12. README, assumptions, data dictionary, Windows setup scripts (setup script executed)

## Acceptance criteria
- [x] Synthetic dataset generated
- [x] Validation pipeline works (nothing silently deleted)
- [x] Calculations unit-tested
- [x] SQL database works
- [x] FastAPI endpoints work (TestClient + manual check)
- [x] Dashboard shows live backend data; date and turbine filters verified in the browser
- [x] Anomalies are explainable (measured value, expected range, explanation, suggested check)
- [x] Excel and PDF reports generate
- [x] Power BI datasets export
- [x] Documentation complete
- [x] Windows setup script executed successfully on a fresh venv (C:\PowerBI, 121 s)
- [x] Automated tests executed

## Not verified / open
- [ ] `docker compose up --build` – Docker Desktop was not running on the dev machine
- [ ] Native `.pbix` file – must be built manually in Power BI Desktop (guide provided)
- [ ] Setup script on a different machine (verified here with a fresh venv and fresh data)
