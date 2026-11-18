"""Generate the monthly report bundle: Excel + PDF + CSV datasets."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import repository as repo
from app.reports.excel_report import build_excel_report
from app.reports.monthly_report import available_months, build_monthly_report, save_report_record
from app.reports.pdf_report import build_pdf_report


def excel_path(month: str) -> Path:
    return settings.reports_dir / "excel" / f"monthly_report_{month}.xlsx"


def pdf_path(month: str) -> Path:
    return settings.reports_dir / "pdf" / f"monthly_report_{month}.pdf"


def write_month_csvs(report: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "turbine_performance.csv": report["turbine_performance"],
        "daily_energy.csv": report["daily_energy"],
        "power_curve.csv": report["power_curve"],
        "downtime_by_turbine.csv": report["downtime"]["by_turbine"],
        "anomalies.csv": report["anomalies"]["items"],
    }
    paths = []
    for name, rows in files.items():
        p = out_dir / name
        pd.DataFrame(rows).to_csv(p, index=False)
        paths.append(p)
    return paths


def generate_month(db: Session, month: str, excel: bool = True, pdf: bool = True, csv: bool = True) -> dict:
    report = build_monthly_report(db, month)
    out = {"month": month}
    if excel:
        out["excel"] = str(build_excel_report(report, excel_path(month), repo.rated_power_kw(db)))
    if pdf:
        out["pdf"] = str(build_pdf_report(report, pdf_path(month)))
    if csv:
        out["csv"] = [str(p) for p in write_month_csvs(report, settings.reports_dir / "csv" / month)]
    save_report_record(db, report, out.get("excel"), out.get("pdf"))
    return out


def generate_all(db: Session) -> list[dict]:
    return [generate_month(db, m) for m in available_months(db)]
