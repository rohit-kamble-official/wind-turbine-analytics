"""Generate monthly Excel + PDF + CSV reports.

Usage: python scripts/generate_reports.py            (all months)
       python scripts/generate_reports.py --month 2026-03
"""
import argparse

import _bootstrap  # noqa: F401
from app.core.config import settings
from app.database.db import get_sessionmaker
from app.reports.report_service import generate_all, generate_month

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM (default: all months in the database)")
    a = ap.parse_args()
    settings.ensure_dirs()
    with get_sessionmaker()() as db:
        results = [generate_month(db, a.month)] if a.month else generate_all(db)
    for r in results:
        print(f"{r['month']}: {r['excel']}\n         {r['pdf']}\n         {len(r['csv'])} CSV files")
