"""Anomalies, downtime, SCADA browsing, data upload and data quality."""
from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.downtime_analysis import downtime_summary
from app.api.deps import Filters, Pagination, get_filters, get_pagination
from app.core.config import settings
from app.database import repository as repo
from app.database.db import get_db
from app.models.models import Anomaly, ImportBatch, ScadaReading, ServiceEvent
from app.schemas.schemas import (AnomalyOut, AnomalyPage, DowntimeResponse, DowntimeTurbine, ImportBatchOut, Page,
                                 ScadaOut, ServiceEventOut, UploadResponse)
from app.services.data_validator import SchemaValidationError
from app.services.pipeline import ingest_upload, latest_batches, recompute_analytics

router = APIRouter(prefix="/api", tags=["operations"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _dt_range(q, col, f: Filters):
    if f.start:
        q = q.where(col >= datetime.combine(f.start, datetime.min.time()))
    if f.end:
        q = q.where(col <= datetime.combine(f.end, datetime.max.time()))
    return q


@router.get("/anomalies", response_model=AnomalyPage, summary="Detected anomalies (paginated, filterable)")
def anomalies(f: Filters = Depends(get_filters), p: Pagination = Depends(get_pagination),
              severity: str | None = Query(None, pattern="^(High|Medium|Low)$"),
              anomaly_type: str | None = Query(None, max_length=64),
              db: Session = Depends(get_db)):
    base = _dt_range(select(Anomaly), Anomaly.timestamp, f)
    if f.turbine_id:
        base = base.where(Anomaly.turbine_id == f.turbine_id)
    # facet counts use date/turbine filters only, so the UI can show what each filter would give
    facets = pd.read_sql(base.with_only_columns(Anomaly.anomaly_type, Anomaly.severity), db.connection())
    q = base
    if severity:
        q = q.where(Anomaly.severity == severity)
    if anomaly_type:
        q = q.where(Anomaly.anomaly_type == anomaly_type)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = db.scalars(q.order_by(Anomaly.timestamp.desc()).offset(p.offset).limit(p.page_size)).all()
    return AnomalyPage(items=[AnomalyOut.model_validate(a) for a in items], total=total, page=p.page,
                       page_size=p.page_size, pages=p.pages(total),
                       by_type={k: int(v) for k, v in facets["anomaly_type"].value_counts().items()},
                       by_severity={k: int(v) for k, v in facets["severity"].value_counts().items()})


@router.get("/downtime", response_model=DowntimeResponse, summary="Downtime totals, per turbine and per fault code")
def downtime(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    m = repo.metrics_frame(db, f.start, f.end, f.turbine_id)
    if m.empty:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No data for the selected filters")
    s = downtime_summary(m)
    by_t = m.groupby("turbine_id")[["planned_maintenance_minutes", "unplanned_fault_minutes", "external_grid_minutes",
                                    "environmental_stop_minutes"]].sum() / 60
    turbines = [DowntimeTurbine(turbine_id=t, planned_hours=round(r.planned_maintenance_minutes, 2),
                                unplanned_hours=round(r.unplanned_fault_minutes, 2),
                                external_hours=round(r.external_grid_minutes, 2),
                                environmental_stop_hours=round(r.environmental_stop_minutes, 2),
                                total_downtime_hours=round(r.planned_maintenance_minutes + r.unplanned_fault_minutes
                                                           + r.external_grid_minutes, 2))
                for t, r in by_t.iterrows()]
    # Fault-code hours from the interval data (exact overlap with the selected range)
    q = _dt_range(select(ScadaReading.fault_code, ScadaReading.interval_category, func.count().label("n")),
                  ScadaReading.timestamp, f).where(
        ScadaReading.interval_category.in_(["planned_maintenance", "unplanned_fault", "external_grid"]))
    if f.turbine_id:
        q = q.where(ScadaReading.turbine_id == f.turbine_id)
    codes = db.execute(q.group_by(ScadaReading.fault_code, ScadaReading.interval_category)).all()
    by_code = sorted([{"fault_code": c or "(none)", "category": cat, "hours": round(n * 10 / 60, 2)}
                      for c, cat, n in codes], key=lambda x: -x["hours"])
    ev = select(ServiceEvent)
    if f.start:
        ev = ev.where(ServiceEvent.end_time >= datetime.combine(f.start, datetime.min.time()))
    if f.end:
        ev = ev.where(ServiceEvent.start_time <= datetime.combine(f.end, datetime.max.time()))
    if f.turbine_id:
        ev = ev.where(ServiceEvent.turbine_id == f.turbine_id)
    events = db.scalars(ev.order_by(ServiceEvent.start_time.desc())).all()
    return DowntimeResponse(**s, by_turbine=turbines, by_fault_code=by_code,
                            events=[ServiceEventOut.model_validate(e) for e in events])


@router.get("/scada", response_model=Page[ScadaOut], summary="Browse 10-min SCADA readings (paginated)")
def scada(f: Filters = Depends(get_filters), p: Pagination = Depends(get_pagination),
          operating_status: str | None = Query(None, pattern="^(Running|Idle|Fault|Maintenance)$"),
          flagged_only: bool = Query(False, description="Only rows with validation flags"),
          db: Session = Depends(get_db)):
    q = _dt_range(select(ScadaReading), ScadaReading.timestamp, f)
    if f.turbine_id:
        q = q.where(ScadaReading.turbine_id == f.turbine_id)
    if operating_status:
        q = q.where(ScadaReading.operating_status == operating_status)
    if flagged_only:
        q = q.where(ScadaReading.qc_flags != "")
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(ScadaReading.timestamp.desc(), ScadaReading.turbine_id)
                      .offset(p.offset).limit(p.page_size)).all()
    return Page[ScadaOut](items=[ScadaOut.model_validate(r) for r in rows], total=total, page=p.page,
                          page_size=p.page_size, pages=p.pages(total))


@router.post("/data/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Upload a SCADA CSV (same columns as scada_data.csv)")
async def upload(background: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if settings.demo_mode:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Uploads are disabled on this public demo. Run the project locally to upload data.")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only .csv files are accepted")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File larger than 50 MB")
    if not content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty")
    try:
        raw = pd.read_csv(io.BytesIO(content), dtype={"timestamp": "string", "turbine_id": "string",
                                                      "fault_code": "string", "operating_status": "string"})
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse CSV: {exc}") from exc
    try:
        batch = ingest_upload(db, raw, file.filename or "upload.csv")
    except SchemaValidationError as exc:
        raise HTTPException(422,
                            {"message": str(exc), "missing_columns": exc.missing}) from exc
    if batch.status == "recomputing":
        background.add_task(recompute_analytics, batch.id)
    return UploadResponse(
        batch=ImportBatchOut.model_validate(batch),
        validation={"rows_received": batch.rows_received, "inserted": batch.rows_inserted,
                    "already_in_database": batch.rows_already_present, "quarantined": batch.rows_quarantined,
                    "flagged": batch.rows_flagged},
        recompute="scheduled" if batch.status == "recomputing" else "not needed")


@router.get("/data/imports", response_model=list[ImportBatchOut], summary="Recent import batches")
def imports(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    return [ImportBatchOut.model_validate(b) for b in latest_batches(db, limit)]


@router.get("/data/imports/{batch_id}", response_model=ImportBatchOut, summary="Import batch status")
def import_status(batch_id: int, db: Session = Depends(get_db)):
    b = db.get(ImportBatch, batch_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch not found")
    return ImportBatchOut.model_validate(b)


@router.get("/data/quality", summary="Latest data-quality report (validation flags, completeness)")
def data_quality():
    for name in ("data_quality_report_latest.json", "data_quality_report.json"):
        p = settings.processed_dir / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No data-quality report yet - run the pipeline")
