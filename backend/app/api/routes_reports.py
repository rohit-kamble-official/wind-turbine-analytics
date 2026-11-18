"""Monthly reports and data exports (CSV / Excel / PDF)."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Filters, get_filters
from app.database import repository as repo
from app.database.db import get_db
from app.models.models import Anomaly, MonthlyReport, ScadaReading
from app.reports.monthly_report import available_months, build_monthly_report
from app.reports.report_service import excel_path, generate_month, pdf_path

router = APIRouter(prefix="/api", tags=["reports"])
MONTH = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM (default: latest month with data)")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SCADA_EXPORT_LIMIT = 300_000


def _resolve_month(db: Session, month: str | None) -> str:
    months = available_months(db)
    if not months:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No data available")
    if month is None:
        return months[-1]
    if month not in months:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No data for {month}. Available: {', '.join(months)}")
    return month


@router.get("/reports/months", summary="Months available for reporting")
def report_months(db: Session = Depends(get_db)):
    generated = {r.month: r for r in db.scalars(select(MonthlyReport))}
    return [{"month": m, "generated_at": generated[m].generated_at if m in generated else None}
            for m in available_months(db)]


@router.get("/reports/monthly", summary="Monthly performance report content (JSON)")
def monthly_report(month: str | None = MONTH, db: Session = Depends(get_db)):
    m = _resolve_month(db, month)
    try:
        return build_monthly_report(db, m)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/reports/pdf", summary="Download the monthly PDF report (generated on demand)",
            response_class=FileResponse)
def report_pdf(month: str | None = MONTH, regenerate: bool = False, db: Session = Depends(get_db)):
    m = _resolve_month(db, month)
    p = pdf_path(m)
    if regenerate or not p.exists():
        generate_month(db, m, excel=False, pdf=True, csv=False)
    return FileResponse(p, media_type="application/pdf", filename=p.name)


@router.get("/export/excel", summary="Download the monthly Excel report (generated on demand)",
            response_class=FileResponse)
def export_excel(month: str | None = MONTH, regenerate: bool = False, db: Session = Depends(get_db)):
    m = _resolve_month(db, month)
    p = excel_path(m)
    if regenerate or not p.exists():
        generate_month(db, m, excel=True, pdf=False, csv=False)
    return FileResponse(p, media_type=XLSX, filename=p.name)


Dataset = Literal["daily", "monthly", "turbine_summary", "anomalies", "scada"]


@router.get("/export/csv", summary="Download a filtered dataset as CSV (Power BI compatible)")
def export_csv(dataset: Dataset = "daily", f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    if dataset == "daily":
        df = repo.metrics_frame(db, f.start, f.end, f.turbine_id).drop(columns=["id"], errors="ignore")
    elif dataset == "monthly":
        df = repo.aggregate_metrics(db, "turbine_month", f.start, f.end, f.turbine_id)
    elif dataset == "turbine_summary":
        df = repo.aggregate_metrics(db, "turbine", f.start, f.end, f.turbine_id)
    elif dataset == "anomalies":
        q = select(Anomaly)
        if f.start:
            q = q.where(Anomaly.timestamp >= datetime.combine(f.start, datetime.min.time()))
        if f.end:
            q = q.where(Anomaly.timestamp <= datetime.combine(f.end, datetime.max.time()))
        if f.turbine_id:
            q = q.where(Anomaly.turbine_id == f.turbine_id)
        df = pd.read_sql(q, db.connection())
    else:
        cols = [c.name for c in ScadaReading.__table__.columns if c.name != "id"]
        df = repo.scada_query(db, cols, f.start, f.end, f.turbine_id)
        if len(df) > SCADA_EXPORT_LIMIT:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"{len(df):,} rows - narrow the date range or select a turbine")
    if df.empty:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No rows for the selected filters")
    buf = io.StringIO()
    df.to_csv(buf, index=False, date_format="%Y-%m-%d %H:%M:%S")
    parts = [dataset, f.turbine_id or "all", str(f.start or "start"), str(f.end or "end")]
    name = "_".join(parts) + ".csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
