"""Power BI star-schema CSV exports.

Facts: Fact_SCADA (10-min), Fact_Performance (daily), Fact_Anomalies, Fact_ServiceEvents
Dimensions: Dim_Turbine, Dim_Date
All facts carry `turbine_id` and an integer `date_key` (yyyymmdd) for relationships.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import repository as repo
from app.models.models import Anomaly, ScadaReading, ServiceEvent


def _date_key(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.strftime("%Y%m%d").astype(int)


def build_dim_date(start, end) -> pd.DataFrame:
    d = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    d["date_key"] = _date_key(d["date"])
    d["year"] = d["date"].dt.year
    d["quarter"] = "Q" + d["date"].dt.quarter.astype(str)
    d["month_number"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.strftime("%B")
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["iso_week"] = d["date"].dt.isocalendar().week.astype(int)
    d["day_of_month"] = d["date"].dt.day
    d["day_name"] = d["date"].dt.strftime("%A")
    d["is_weekend"] = d["date"].dt.dayofweek >= 5
    d["season"] = d["month_number"].map({12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring",
                                         5: "Spring", 6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn",
                                         10: "Autumn", 11: "Autumn"})
    d["date"] = d["date"].dt.date
    return d[["date_key", "date", "year", "quarter", "month_number", "month_name", "year_month", "iso_week",
              "day_of_month", "day_name", "is_weekend", "season"]]


def export_powerbi(db: Session, out_dir: Path, include_scada: bool = True) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    lo, hi = repo.data_range(db)
    if lo is None:
        raise LookupError("Database is empty - run the pipeline first")

    turbines = repo.turbines_frame(db)
    turbines.to_csv(out_dir / "Dim_Turbine.csv", index=False)
    paths["Dim_Turbine"] = out_dir / "Dim_Turbine.csv"

    build_dim_date(lo, hi).to_csv(out_dir / "Dim_Date.csv", index=False)
    paths["Dim_Date"] = out_dir / "Dim_Date.csv"

    perf = repo.metrics_frame(db)
    perf.insert(1, "date_key", _date_key(perf["date"]))
    perf["downtime_hours"] = (perf["planned_maintenance_minutes"] + perf["unplanned_fault_minutes"]
                              + perf["external_grid_minutes"]) / 60
    perf["available_minutes"] = perf["running_minutes"] + perf["idle_low_wind_minutes"] + perf[
        "environmental_stop_minutes"]
    perf["eligible_minutes"] = perf["available_minutes"] + perf["unplanned_fault_minutes"] + perf[
        "planned_maintenance_minutes"]
    perf["max_possible_energy_kwh"] = turbines["rated_power_kw"].max() * perf["energy_data_minutes"] / 60
    perf = perf.drop(columns=["id"])
    perf.to_csv(out_dir / "Fact_Performance.csv", index=False)
    paths["Fact_Performance"] = out_dir / "Fact_Performance.csv"

    an = pd.read_sql(select(Anomaly), db.connection())
    an.insert(1, "date_key", _date_key(an["timestamp"]) if len(an) else pd.Series(dtype=int))
    an.to_csv(out_dir / "Fact_Anomalies.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    paths["Fact_Anomalies"] = out_dir / "Fact_Anomalies.csv"

    ev = pd.read_sql(select(ServiceEvent), db.connection())
    ev.insert(1, "date_key", _date_key(ev["start_time"]) if len(ev) else pd.Series(dtype=int))
    ev.to_csv(out_dir / "Fact_ServiceEvents.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    paths["Fact_ServiceEvents"] = out_dir / "Fact_ServiceEvents.csv"

    if include_scada:
        cols = ["timestamp", "turbine_id", "wind_speed_ms", "active_power_kw", "theoretical_power_kw",
                "rotor_speed_rpm", "pitch_angle_deg", "ambient_temperature_c", "nacelle_temperature_c",
                "gearbox_temperature_c", "generator_temperature_c", "operating_status", "fault_code",
                "interval_category", "is_valid_for_analysis"]
        sc = pd.read_sql(select(*[getattr(ScadaReading, c) for c in cols]), db.connection())
        sc.insert(0, "date_key", _date_key(sc["timestamp"]))
        sc["energy_kwh"] = sc["active_power_kw"].where(sc["is_valid_for_analysis"].astype(bool)) / 6
        sc.to_csv(out_dir / "Fact_SCADA.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
        paths["Fact_SCADA"] = out_dir / "Fact_SCADA.csv"
    return paths
