"""Validate + process the generated SCADA data and (re)build the SQLite database.

Usage: python scripts/run_pipeline.py [--scada path.csv] [--keep]   (--keep = do not drop existing tables)
"""
import argparse
import logging
from pathlib import Path

import _bootstrap  # noqa: F401
from app.core.config import settings
from app.services.pipeline import run_full_pipeline

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--scada", type=Path, default=None)
    ap.add_argument("--turbines", type=Path, default=None)
    ap.add_argument("--events", type=Path, default=None)
    ap.add_argument("--keep", action="store_true", help="keep existing tables (insert new rows only)")
    a = ap.parse_args()
    settings.ensure_dirs()
    r = run_full_pipeline(a.scada, a.turbines, a.events, reset=not a.keep)
    print("Pipeline finished:")
    for k, v in r.as_dict().items():
        print(f"  {k:20s} {v}")
    print(f"Database: {settings.database_url}")
