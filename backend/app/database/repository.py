"""Data access layer: inserts (idempotent) and aggregation queries.

Aggregations are done in SQL (SUM/GROUP BY over daily metric rows); ratios
(availability, capacity factor, deviation) are computed afterwards from the
summed components so that they are mathematically correct for any range
(a ratio of sums, never an average of daily ratios).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

import numpy as np
import pandas as pd
from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.analytics import availability as av
from app.analytics.performance_calculations import aggregate_deviation_pct, capacity_factor_pct
from app.models.models import (Anomaly, DataQualityLog, PerformanceMetric, ScadaReading, ServiceEvent,
                               Turbine)

SCADA_DB_COLUMNS = [c.name for c in ScadaReading.__table__.columns if c.name != "id"]
METRIC_DB_COLUMNS = [c.name for c in PerformanceMetric.__table__.columns if c.name != "id"]
CHUNK = 5000


def _none(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if v is pd.NaT:
        return None
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    sub = df[cols].astype(object).where(df[cols].notna(), None)
    return [{k: _none(v) for k, v in zip(cols, row)} for row in sub.itertuples(index=False, name=None)]


# --------------------------------------------------------------------- writes
def upsert_turbines(db: Session, turbines: pd.DataFrame) -> int:
    t = turbines.copy()
    t["commissioning_date"] = pd.to_datetime(t["commissioning_date"], errors="coerce").dt.date
    cols = [c.name for c in Turbine.__table__.columns]
    rows = _records(t, [c for c in cols if c in t])
    stmt = sqlite_insert(Turbine).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=["turbine_id"],
                                      set_={c: stmt.excluded[c] for c in cols if c != "turbine_id" and c in t})
    db.execute(stmt)
    db.commit()
    return len(rows)


def replace_service_events(db: Session, events: pd.DataFrame) -> int:
    db.execute(delete(ServiceEvent))
    e = events.copy()
    for c in ("start_time", "end_time"):
        e[c] = pd.to_datetime(e[c])
    rows = _records(e, [c.name for c in ServiceEvent.__table__.columns])
    for i in range(0, len(rows), CHUNK):
        db.execute(sqlite_insert(ServiceEvent), rows[i:i + CHUNK])
    db.commit()
    return len(rows)


def insert_scada(db: Session, clean: pd.DataFrame) -> int:
    """Insert record-valid rows; existing (turbine_id, timestamp) pairs are ignored.
    Returns the number of rows actually inserted."""
    if clean.empty:
        return 0
    before = db.scalar(select(func.count()).select_from(ScadaReading))
    df = clean.copy()
    df["fault_code"] = df["fault_code"].fillna("")
    df["qc_flags"] = df["qc_flags"].fillna("")
    rows = _records(df, SCADA_DB_COLUMNS)
    stmt = sqlite_insert(ScadaReading).on_conflict_do_nothing(index_elements=["turbine_id", "timestamp"])
    for i in range(0, len(rows), CHUNK):
        db.execute(stmt, rows[i:i + CHUNK])
    db.commit()
    after = db.scalar(select(func.count()).select_from(ScadaReading))
    return int(after - before)


def replace_metrics(db: Session, daily: pd.DataFrame, turbine_ids: Iterable[str] | None = None) -> int:
    q = delete(PerformanceMetric)
    if turbine_ids is not None:
        q = q.where(PerformanceMetric.turbine_id.in_(list(turbine_ids)))
    db.execute(q)
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.date
    rows = _records(d, [c for c in METRIC_DB_COLUMNS if c in d])
    for i in range(0, len(rows), CHUNK):
        db.execute(sqlite_insert(PerformanceMetric), rows[i:i + CHUNK])
    db.commit()
    return len(rows)


def replace_anomalies(db: Session, anomalies: pd.DataFrame) -> int:
    db.execute(delete(Anomaly))
    if anomalies.empty:
        db.commit()
        return 0
    rows = _records(anomalies, [c.name for c in Anomaly.__table__.columns])
    db.execute(sqlite_insert(Anomaly).on_conflict_do_nothing(index_elements=["anomaly_id"]), rows)
    db.commit()
    return len(rows)


def log_quarantine(db: Session, quarantine: pd.DataFrame, batch_id: int | None = None) -> int:
    if quarantine.empty:
        return 0
    q = pd.DataFrame({
        "batch_id": batch_id, "source_row": quarantine["source_row"].astype(int),
        "timestamp_raw": quarantine["timestamp_raw"].astype(str),
        "turbine_id": quarantine["turbine_id"].astype(str), "issue": quarantine["qc_flags"].astype(str),
    })
    db.execute(sqlite_insert(DataQualityLog), _records(q, list(q.columns)))
    db.commit()
    return len(q)


# ---------------------------------------------------------------------- reads
def turbine_ids(db: Session) -> list[str]:
    return list(db.scalars(select(Turbine.turbine_id).order_by(Turbine.turbine_id)))


def rated_power_kw(db: Session) -> float:
    return float(db.scalar(select(func.max(Turbine.rated_power_kw))) or 3000.0)


def data_range(db: Session) -> tuple[date | None, date | None]:
    lo, hi = db.execute(select(func.min(PerformanceMetric.date), func.max(PerformanceMetric.date))).one()
    return lo, hi


def _filter(stmt: Select, col_date, col_turbine, start: date | None, end: date | None,
            turbine_id: str | None) -> Select:
    if start is not None:
        stmt = stmt.where(col_date >= start)
    if end is not None:
        stmt = stmt.where(col_date <= end)
    if turbine_id:
        stmt = stmt.where(col_turbine == turbine_id)
    return stmt


def _ts_filter(stmt: Select, model, start: date | None, end: date | None, turbine_id: str | None) -> Select:
    if start is not None:
        stmt = stmt.where(model.timestamp >= datetime.combine(start, datetime.min.time()))
    if end is not None:
        stmt = stmt.where(model.timestamp < datetime.combine(end, datetime.min.time()) + pd.Timedelta(days=1))
    if turbine_id:
        stmt = stmt.where(model.turbine_id == turbine_id)
    return stmt


_CATEGORY_COLS = [f"{c}_minutes" for c in av.CATEGORIES]


def aggregate_metrics(db: Session, group_by: str | None, start: date | None = None, end: date | None = None,
                      turbine_id: str | None = None,
                      cfg: av.AvailabilityConfig = av.AvailabilityConfig()) -> pd.DataFrame:
    """SQL aggregation of daily metrics. group_by: None | 'date' | 'month' | 'turbine' | 'turbine_month'."""
    M = PerformanceMetric
    keys = {
        None: [],
        "date": [M.date.label("date")],
        "month": [func.strftime("%Y-%m", M.date).label("month")],
        "turbine": [M.turbine_id.label("turbine_id")],
        "turbine_month": [M.turbine_id.label("turbine_id"), func.strftime("%Y-%m", M.date).label("month")],
    }[group_by]
    measures = [
        func.sum(M.energy_kwh).label("energy_kwh"),
        func.sum(M.running_energy_kwh).label("running_energy_kwh"),
        func.sum(M.expected_energy_kwh).label("expected_energy_kwh"),
        func.sum(M.energy_data_minutes).label("energy_data_minutes"),
        func.sum(M.avg_wind_speed_ms * M.analysis_records).label("wind_weighted"),
        func.sum(M.analysis_records).label("analysis_records"),
        func.sum(M.valid_records).label("valid_records"),
        func.sum(M.flagged_records).label("flagged_records"),
        func.avg(M.avg_gearbox_temp_c).label("avg_gearbox_temp_c"),
        func.max(M.max_gearbox_temp_c).label("max_gearbox_temp_c"),
        func.avg(M.avg_generator_temp_c).label("avg_generator_temp_c"),
        func.max(M.max_generator_temp_c).label("max_generator_temp_c"),
        func.avg(M.avg_nacelle_temp_c).label("avg_nacelle_temp_c"),
        func.avg(M.avg_ambient_temp_c).label("avg_ambient_temp_c"),
        func.count(func.distinct(M.turbine_id)).label("turbines"),
        func.count().label("turbine_days"),
    ] + [func.sum(getattr(M, c)).label(c) for c in _CATEGORY_COLS]
    stmt = select(*keys, *measures)
    stmt = _filter(stmt, M.date, M.turbine_id, start, end, turbine_id)
    if keys:
        stmt = stmt.group_by(*keys).order_by(*keys)
    rows = db.execute(stmt).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty or (group_by is None and df["turbine_days"].iloc[0] == 0):
        return pd.DataFrame()
    return finalize_kpis(df, rated_power_kw(db), cfg)


def finalize_kpis(df: pd.DataFrame, rated_kw: float, cfg: av.AvailabilityConfig = av.AvailabilityConfig()
                  ) -> pd.DataFrame:
    out = df.copy()
    for c in _CATEGORY_COLS + ["energy_kwh", "running_energy_kwh", "expected_energy_kwh", "energy_data_minutes",
                               "wind_weighted", "analysis_records"]:
        out[c] = pd.to_numeric(out[c]).fillna(0.0)
    out["energy_mwh"] = out["energy_kwh"] / 1000
    out["avg_wind_speed_ms"] = np.where(out["analysis_records"] > 0,
                                        out["wind_weighted"] / out["analysis_records"].replace(0, np.nan), np.nan)
    out["availability_pct"] = av.availability_pct(out, cfg).to_numpy()
    out["capacity_factor_pct"] = capacity_factor_pct(out["energy_kwh"], rated_kw, out["energy_data_minutes"] / 60)
    out["performance_deviation_pct"] = aggregate_deviation_pct(out["running_energy_kwh"], out["expected_energy_kwh"])
    out["planned_downtime_hours"] = out["planned_maintenance_minutes"] / 60
    out["unplanned_downtime_hours"] = out["unplanned_fault_minutes"] / 60
    out["external_downtime_hours"] = out["external_grid_minutes"] / 60
    out["downtime_hours"] = out[["planned_downtime_hours", "unplanned_downtime_hours",
                                 "external_downtime_hours"]].sum(axis=1)
    out["environmental_stop_hours"] = out["environmental_stop_minutes"] / 60
    out["missing_data_hours"] = out["missing_minutes"] / 60
    total_min = out[_CATEGORY_COLS].sum(axis=1)
    out["data_coverage_pct"] = np.where(total_min > 0, out["energy_data_minutes"] / total_min * 100, np.nan)
    return out.drop(columns=["wind_weighted"])


def metrics_frame(db: Session, start=None, end=None, turbine_id=None) -> pd.DataFrame:
    stmt = _filter(select(PerformanceMetric), PerformanceMetric.date, PerformanceMetric.turbine_id, start, end,
                   turbine_id).order_by(PerformanceMetric.date, PerformanceMetric.turbine_id)
    return pd.read_sql(stmt, db.connection())


def scada_query(db: Session, columns: list[str], start=None, end=None, turbine_id=None,
                running_valid_only: bool = False, sample: int | None = None) -> pd.DataFrame:
    cols = [getattr(ScadaReading, c) for c in columns]
    stmt = _ts_filter(select(*cols), ScadaReading, start, end, turbine_id)
    if running_valid_only:
        stmt = stmt.where(ScadaReading.operating_status == "Running",
                          ScadaReading.is_valid_for_analysis.is_(True))
    if sample:
        stmt = stmt.order_by(func.random()).limit(sample)
    return pd.read_sql(stmt, db.connection())


def load_scada_for_recompute(db: Session) -> pd.DataFrame:
    """All stored readings in the raw CSV layout (for re-validation after uploads)."""
    from app.services.data_validator import REQUIRED_COLUMNS

    df = pd.read_sql(select(*[getattr(ScadaReading, c) for c in REQUIRED_COLUMNS]), db.connection())
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def turbines_frame(db: Session) -> pd.DataFrame:
    return pd.read_sql(select(Turbine).order_by(Turbine.turbine_id), db.connection())
