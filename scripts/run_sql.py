"""Execute every statement in a .sql file against the project database and print results.

Usage: python scripts/run_sql.py sql/performance_queries.sql [--rows 5]
"""
import argparse
import sqlite3
from pathlib import Path

import _bootstrap  # noqa: F401
from app.core.config import settings

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--rows", type=int, default=5)
    a = ap.parse_args()
    db_path = settings.database_url.replace("sqlite:///", "")
    con = sqlite3.connect(db_path)
    blocks, current, title = [], [], ""
    for line in a.file.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- Q"):
            title = line[3:].strip()
        if line.strip().startswith("--") or not line.strip():
            continue
        current.append(line)
        if line.rstrip().endswith(";"):
            blocks.append((title, "\n".join(current)))
            current = []
    for title, sql in blocks:
        cur = con.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        print(f"\n== {title}  ({len(rows)} rows)")
        print(" | ".join(cols))
        for r in rows[: a.rows]:
            print(" | ".join(str(v) for v in r))
    print(f"\nOK - {len(blocks)} queries executed")
