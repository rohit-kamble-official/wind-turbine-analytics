"""KPI and analytics endpoints. All accept start_date, end_date and turbine_id."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.availability import AvailabilityConfig
from app.analytics.power_curve import bin_power_curve
from app.analytics.turbine_model import reference_curve_table
from app.api.deps import Filters, clean, get_filters
from app.database import repository as repo
from app.database.db import get_db
from app.models.models import Anomaly
from app.schemas.schemas import (AvailabilityResponse, AvailabilityRow, CapacityFactorResponse, CapacityFactorRow,
                                 DailyMetric, DeviationResponse, DeviationRow, KpiSummary, MonthlyMetric,
                                 PowerCurveResponse, TemperaturePoint)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])
Basis = Literal["technical", "contractual", "strict"]


def _anomaly_count(db: Session, f: Filters) -> int:
    q = select(func.count()).select_from(Anomaly)
    if f.start:
        q = q.where(Anomaly.timestamp >= datetime.combine(f.start, datetime.min.time()))
    if f.end:
        q = q.where(Anomaly.timestamp <= datetime.combine(f.end, datetime.max.time()))
    if f.turbine_id:
        q = q.where(Anomaly.turbine_id == f.turbine_id)
    return db.scalar(q) or 0


@router.get("/summary", response_model=KpiSummary, summary="Headline KPIs for the selected period")
def summary(f: Filters = Depends(get_filters), basis: Basis = "technical", db: Session = Depends(get_db)):
    cfg = AvailabilityConfig.from_basis(basis)
    agg = repo.aggregate_metrics(db, None, f.start, f.end, f.turbine_id, cfg)
    total_turbines = 1 if f.turbine_id else len(repo.turbine_ids(db))
    base = dict(start_date=f.start, end_date=f.end, turbine_id=f.turbine_id, total_turbines=total_turbines,
                anomaly_count=_anomaly_count(db, f), availability_basis=basis,
                availability_definition=cfg.describe())
    if agg.empty:
        return KpiSummary(active_turbines=0, **base)
    r = agg.iloc[0]
    # "Active" = turbines that produced energy while running in the period
    by_t = repo.aggregate_metrics(db, "turbine", f.start, f.end, f.turbine_id, cfg)
    active = int((by_t["running_minutes"] > 0).sum()) if not by_t.empty else 0
    return KpiSummary(
        energy_mwh=clean(r["energy_mwh"]), avg_wind_speed_ms=clean(r["avg_wind_speed_ms"]),
        availability_pct=clean(r["availability_pct"]), capacity_factor_pct=clean(r["capacity_factor_pct"]),
        performance_deviation_pct=clean(r["performance_deviation_pct"]), downtime_hours=clean(r["downtime_hours"]),
        planned_downtime_hours=clean(r["planned_downtime_hours"]),
        unplanned_downtime_hours=clean(r["unplanned_downtime_hours"]),
        external_downtime_hours=clean(r["external_downtime_hours"]), data_coverage_pct=clean(r["data_coverage_pct"]),
        active_turbines=active, **base)


def _daily_rows(df, with_turbine: bool) -> list[DailyMetric]:
    return [DailyMetric(
        date=r["date"], turbine_id=r.get("turbine_id") if with_turbine else None, energy_mwh=clean(r["energy_mwh"]),
        avg_wind_speed_ms=clean(r["avg_wind_speed_ms"]), availability_pct=clean(r["availability_pct"]),
        capacity_factor_pct=clean(r["capacity_factor_pct"]),
        performance_deviation_pct=clean(r["performance_deviation_pct"]), downtime_hours=clean(r["downtime_hours"]),
        expected_energy_mwh=clean(r["expected_energy_kwh"] / 1000),
    ) for r in df.to_dict("records")]


@router.get("/daily", response_model=list[DailyMetric], summary="Daily KPIs (farm total or one turbine)")
def daily(f: Filters = Depends(get_filters), by_turbine: bool = Query(False, description="One row per turbine"),
          db: Session = Depends(get_db)):
    if by_turbine:
        df = repo.metrics_frame(db, f.start, f.end, f.turbine_id)
        if df.empty:
            return []
        df = repo.finalize_kpis(df.assign(wind_weighted=df["avg_wind_speed_ms"] * df["analysis_records"]),
                                repo.rated_power_kw(db))
        return _daily_rows(df, True)
    df = repo.aggregate_metrics(db, "date", f.start, f.end, f.turbine_id)
    return [] if df.empty else _daily_rows(df, False)


@router.get("/monthly", response_model=list[MonthlyMetric], summary="Monthly KPIs (farm, or per turbine)")
def monthly(f: Filters = Depends(get_filters), by_turbine: bool = False, db: Session = Depends(get_db)):
    df = repo.aggregate_metrics(db, "turbine_month" if by_turbine else "month", f.start, f.end, f.turbine_id)
    if df.empty:
        return []
    return [MonthlyMetric(month=r["month"], turbine_id=r.get("turbine_id"), energy_mwh=clean(r["energy_mwh"]),
                          avg_wind_speed_ms=clean(r["avg_wind_speed_ms"]), availability_pct=clean(r["availability_pct"]),
                          capacity_factor_pct=clean(r["capacity_factor_pct"]),
                          performance_deviation_pct=clean(r["performance_deviation_pct"]),
                          downtime_hours=clean(r["downtime_hours"])) for r in df.to_dict("records")]


@router.get("/availability", response_model=AvailabilityResponse,
            summary="Time-based availability per turbine with category breakdown")
def availability(f: Filters = Depends(get_filters), basis: Basis = Query(
        "technical", description="technical: planned maintenance counts as unavailable; contractual: planned "
                                 "maintenance excluded from eligible time; strict: grid events and data gaps "
                                 "also count against availability"), db: Session = Depends(get_db)):
    cfg = AvailabilityConfig.from_basis(basis)
    df = repo.aggregate_metrics(db, "turbine", f.start, f.end, f.turbine_id, cfg)
    fleet = repo.aggregate_metrics(db, None, f.start, f.end, f.turbine_id, cfg)
    rows = []
    from app.analytics.availability import availability_components
    for r in df.to_dict("records"):
        avail, elig = availability_components(r, cfg)
        rows.append(AvailabilityRow(
            turbine_id=r["turbine_id"], availability_pct=clean(r["availability_pct"]), available_hours=avail / 60,
            eligible_hours=elig / 60, running_hours=r["running_minutes"] / 60,
            idle_low_wind_hours=r["idle_low_wind_minutes"] / 60,
            environmental_stop_hours=r["environmental_stop_minutes"] / 60,
            planned_maintenance_hours=r["planned_maintenance_minutes"] / 60,
            unplanned_fault_hours=r["unplanned_fault_minutes"] / 60, external_grid_hours=r["external_grid_minutes"] / 60,
            missing_data_hours=r["missing_minutes"] / 60))
    return AvailabilityResponse(basis=basis, definition=cfg.describe(),
                                fleet_availability_pct=clean(fleet["availability_pct"].iloc[0]) if not fleet.empty else None,
                                turbines=rows)


@router.get("/capacity-factor", response_model=CapacityFactorResponse, summary="Capacity factor per turbine")
def capacity_factor(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    rated = repo.rated_power_kw(db)
    df = repo.aggregate_metrics(db, "turbine", f.start, f.end, f.turbine_id)
    fleet = repo.aggregate_metrics(db, None, f.start, f.end, f.turbine_id)
    rows = [CapacityFactorRow(turbine_id=r["turbine_id"], energy_mwh=r["energy_mwh"],
                              eligible_hours=r["energy_data_minutes"] / 60,
                              max_possible_energy_mwh=rated * r["energy_data_minutes"] / 60 / 1000,
                              capacity_factor_pct=clean(r["capacity_factor_pct"])) for r in df.to_dict("records")]
    return CapacityFactorResponse(rated_power_kw=rated, turbines=rows, fleet_capacity_factor_pct=clean(
        fleet["capacity_factor_pct"].iloc[0]) if not fleet.empty else None)


@router.get("/power-curve", response_model=PowerCurveResponse, summary="Binned measured vs reference power curve")
def power_curve(f: Filters = Depends(get_filters), bin_width: float = Query(0.5, gt=0.1, le=2.0),
                scatter_points: int = Query(1500, ge=0, le=5000, description="Random sample for scatter plot"),
                db: Session = Depends(get_db)):
    cols = ["wind_speed_ms", "active_power_kw", "operating_status", "is_valid_for_analysis", "turbine_id"]
    data = repo.scada_query(db, cols, f.start, f.end, f.turbine_id, running_valid_only=True)
    bins = bin_power_curve(data, bin_width)
    scatter = data.sample(min(scatter_points, len(data)), random_state=1) if len(data) else data
    bins = bins.replace({np.nan: None})
    return PowerCurveResponse(
        bin_width_ms=bin_width, records_used=int(len(data)), bins=bins.to_dict("records"),
        reference_curve=reference_curve_table(0.5),
        scatter=[{"wind_speed_ms": float(r.wind_speed_ms), "active_power_kw": float(r.active_power_kw),
                  "turbine_id": r.turbine_id} for r in scatter.itertuples()],
        note=("Measured: mean active power of valid Running 10-min records per wind-speed bin. Reference: "
              "theoretical curve of the simulated turbine model at the bin mean wind speed. Nacelle anemometer, "
              "no air-density correction."))


@router.get("/performance-deviation", response_model=DeviationResponse,
            summary="Energy-weighted deviation vs the reference power curve")
def performance_deviation(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    df = repo.aggregate_metrics(db, "turbine", f.start, f.end, f.turbine_id)
    fleet = repo.aggregate_metrics(db, None, f.start, f.end, f.turbine_id)
    if df.empty:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No data for the selected filters")
    fleet_dev = clean(fleet["performance_deviation_pct"].iloc[0])
    rows = [DeviationRow(turbine_id=r["turbine_id"], performance_deviation_pct=clean(r["performance_deviation_pct"]),
                         actual_energy_mwh=r["running_energy_kwh"] / 1000,
                         expected_energy_mwh=r["expected_energy_kwh"] / 1000,
                         relative_to_fleet_pp=clean(r["performance_deviation_pct"] - fleet_dev)
                         if fleet_dev is not None else None) for r in df.to_dict("records")]
    d = repo.aggregate_metrics(db, "date", f.start, f.end, f.turbine_id)
    return DeviationResponse(
        fleet_deviation_pct=fleet_dev, turbines=rows, daily=_daily_rows(d, False),
        definition=("(actual - expected) / expected x 100 over Running intervals with expected power >= 50 kW; "
                    "energy-weighted. Zero/low expected power is excluded instead of dividing by ~0."))


@router.get("/temperature", response_model=list[TemperaturePoint], summary="Daily component temperature trends")
def temperature(f: Filters = Depends(get_filters), db: Session = Depends(get_db)):
    df = repo.aggregate_metrics(db, "date", f.start, f.end, f.turbine_id)
    if df.empty:
        return []
    cols = ["avg_gearbox_temp_c", "max_gearbox_temp_c", "avg_generator_temp_c", "max_generator_temp_c",
            "avg_nacelle_temp_c", "avg_ambient_temp_c"]
    return [TemperaturePoint(date=r["date"], **{c: clean(r[c]) for c in cols}) for r in df.to_dict("records")]
