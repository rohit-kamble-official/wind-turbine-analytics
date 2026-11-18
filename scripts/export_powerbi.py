"""Export the Power BI star-schema CSVs to powerbi/datasets/.

Usage: python scripts/export_powerbi.py [--no-scada]
"""
import argparse

import _bootstrap  # noqa: F401
from app.core.config import settings
from app.database.db import get_sessionmaker
from app.reports.powerbi_export import export_powerbi

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scada", action="store_true", help="skip the large 10-min Fact_SCADA table")
    a = ap.parse_args()
    settings.ensure_dirs()
    with get_sessionmaker()() as db:
        paths = export_powerbi(db, settings.powerbi_dir, include_scada=not a.no_scada)
    for name, p in paths.items():
        print(f"{name:20s} -> {p}")
