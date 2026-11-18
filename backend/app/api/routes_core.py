"""Health and turbine endpoints."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import Filters, clean, get_date_range, get_filters
from app.core.config import settings
from app.database import repository as repo
from app.database.db import get_db
from app.models.models import Anomaly, ImportBatch, ScadaReading, Turbine
from app.schemas.schemas import (HealthResponse, LatestReading, PeriodKpis, TurbineDetail, TurbineOut,
                                 TurbineStatusRow)

router = APIRouter(prefix="/api", tags=["core"])
VERSION = "1.0.0"
KPI_FIELDS = list(PeriodKpis.model_fields)


@router.get("/health", response_model=HealthResponse, summary="Service and data status")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Database unavailable: {exc}") from exc
    lo, hi = repo.data_range(db)
    last = db.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
    return HealthResponse(
        status="ok" if lo else "empty", database="connected",
        turbines=db.scalar(select(func.count()).select_from(Turbine)) or 0,
        scada_records=db.scalar(select(func.count()).select_from(ScadaReading)) or 0,
        anomalies=db.scalar(select(func.count()).select_from(Anomaly)) or 0,
        data_start=lo, data_end=hi, last_import=last.imported_at if last else None,
        last_import_status=last.status if last else None, version=VERSION,
        demo_mode=settings.demo_mode,
    )


@router.get("/turbines", response_model=list[TurbineOut], summary="Turbine register")
def list_turbines(db: Session = Depends(get_db)):
    return db.scalars(select(Turbine).order_by(Turbine.turbine_id)).all()


def _latest_readings(db: Session, before: datetime | None, turbine_id: str | None = None) -> dict[str, LatestReading]:
    """Most recent reading per turbine at or before `before` (end of selected range)."""
    sub = select(ScadaReading.turbine_id, func.max(ScadaReading.timestamp).label("ts"))
    if before is not None:
        sub = sub.where(ScadaReading.timestamp <= before)
    if turbine_id:
        sub = sub.where(ScadaReading.turbine_id == turbine_id)
    sub = sub.group_by(ScadaReading.turbine_id).subquery()
    rows = db.execute(select(ScadaReading).join(
        sub, (ScadaReading.turbine_id == sub.c.turbine_id) & (ScadaReading.timestamp == sub.c.ts))).scalars()
    return {r.turbine_id: LatestReading(timestamp=r.timestamp, operating_status=r.operating_status,
                                        fault_code=r.fault_code or "", wind_speed_ms=r.wind_speed_ms,
                                        active_power_kw=r.active_power_kw,
                                        gearbox_temperature_c=r.gearbox_temperature_c,
                                        generator_temperature_c=r.generator_temperature_c) for r in rows}


def _end_dt(f: Filters) -> datetime | None:
    return datetime.combine(f.end, datetime.max.time()) if f.end else None


def _kpis(row: pd.Series | None) -> dict:
    if row is None:
        return {}
    return {k: clean(row.get(k)) for k in KPI_FIELDS}


@router.get("/turbines/status", response_model=list[TurbineStatusRow],
            summary="Per-turbine status table: latest reading + KPIs for the selected period")
def turbine_status(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    agg = repo.aggregate_metrics(db, "turbine", f.start, f.end, f.turbine_id)
    agg = agg.set_index("turbine_id") if not agg.empty else agg
    latest = _latest_readings(db, _end_dt(f), f.turbine_id)
    q = select(Anomaly)
    if f.start:
        q = q.where(Anomaly.timestamp >= datetime.combine(f.start, datetime.min.time()))
    if f.end:
        q = q.where(Anomaly.timestamp <= _end_dt(f))
    anomalies = pd.read_sql(q, db.connection())
    ids = [f.turbine_id] if f.turbine_id else repo.turbine_ids(db)
    out = []
    for tid in ids:
        a = anomalies[anomalies["turbine_id"] == tid].sort_values("timestamp")
        last = a.iloc[-1] if len(a) else None
        out.append(TurbineStatusRow(
            turbine_id=tid, latest=latest.get(tid),
            **_kpis(agg.loc[tid] if not agg.empty and tid in agg.index else None),
            latest_alert=last["anomaly_type"] if last is not None else None,
            latest_alert_severity=last["severity"] if last is not None else None,
            latest_alert_time=last["timestamp"] if last is not None else None,
            anomaly_count=int(len(a)),
        ))
    return out


@router.get("/turbines/{turbine_id}", response_model=TurbineDetail, summary="Turbine details and period KPIs")
def turbine_detail(turbine_id: str, f: Filters = Depends(get_date_range), db: Session = Depends(get_db)):
    t = db.get(Turbine, turbine_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Turbine '{turbine_id}' not found")
    agg = repo.aggregate_metrics(db, None, f.start, f.end, turbine_id)
    open_anom = db.scalar(select(func.count()).select_from(Anomaly).where(
        Anomaly.turbine_id == turbine_id, Anomaly.status == "Open")) or 0
    return TurbineDetail(turbine=TurbineOut.model_validate(t),
                         latest=_latest_readings(db, _end_dt(f), turbine_id).get(turbine_id),
                         period=PeriodKpis(**_kpis(agg.iloc[0] if not agg.empty else None)),
                         open_anomalies=open_anom)
