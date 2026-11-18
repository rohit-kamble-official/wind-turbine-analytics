"""Monthly performance report content (shared by JSON API, Excel and PDF).

Findings are rule-based and phrased as observations; recommended actions are
investigations, not diagnoses.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.power_curve import bin_power_curve
from app.database import repository as repo
from app.models.models import Anomaly, DataQualityLog, MonthlyReport, ServiceEvent

AVAILABILITY_TARGET_PCT = 97.0
DEVIATION_GAP_PP = 3.0
DISCLAIMER = ("SIMULATED DATA - generated for a portfolio project. Not real operational data and not an "
              "official report of any turbine manufacturer or operator.")
SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def month_bounds(month: str) -> tuple[date, date]:
    try:
        start = datetime.strptime(month, "%Y-%m").date()
    except ValueError as exc:
        raise ValueError("month must be formatted YYYY-MM") from exc
    end = (pd.Timestamp(start) + pd.offsets.MonthEnd(0)).date()
    return start, end


def available_months(db: Session) -> list[str]:
    lo, hi = repo.data_range(db)
    if lo is None:
        return []
    return [p.strftime("%Y-%m") for p in pd.period_range(lo, hi, freq="M")]


def _clean(v):
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 3)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def build_monthly_report(db: Session, month: str) -> dict:
    start, end = month_bounds(month)
    kpi_df = repo.aggregate_metrics(db, None, start, end)
    if kpi_df.empty:
        raise LookupError(f"No data for {month}")
    k = kpi_df.iloc[0]
    by_t = repo.aggregate_metrics(db, "turbine", start, end)
    daily = repo.aggregate_metrics(db, "date", start, end)
    monthly = repo.aggregate_metrics(db, "month")

    anomalies = pd.read_sql(
        select(Anomaly).where(Anomaly.timestamp >= datetime.combine(start, datetime.min.time()),
                              Anomaly.timestamp < datetime.combine(end, datetime.min.time()) + pd.Timedelta(days=1)),
        db.connection())
    events = pd.read_sql(
        select(ServiceEvent).where(ServiceEvent.start_time <= datetime.combine(end, datetime.max.time()),
                                   ServiceEvent.end_time >= datetime.combine(start, datetime.min.time())),
        db.connection())

    pc_raw = repo.scada_query(db, ["wind_speed_ms", "active_power_kw", "operating_status", "is_valid_for_analysis"],
                              start, end, running_valid_only=True)
    pc = bin_power_curve(pc_raw)

    fault_hours = (events[~events["is_planned"]].groupby("fault_code")["duration_hours"].sum()
                   .sort_values(ascending=False) if not events.empty else pd.Series(dtype=float))

    turbine_rows = by_t[["turbine_id", "energy_mwh", "avg_wind_speed_ms", "availability_pct", "capacity_factor_pct",
                         "performance_deviation_pct", "downtime_hours", "planned_downtime_hours",
                         "unplanned_downtime_hours", "external_downtime_hours", "environmental_stop_hours",
                         "energy_data_minutes", "data_coverage_pct"]].copy()
    turbine_rows["data_hours"] = turbine_rows.pop("energy_data_minutes") / 60
    a_counts = anomalies.groupby("turbine_id").size() if not anomalies.empty else pd.Series(dtype=int)
    turbine_rows["anomalies"] = turbine_rows["turbine_id"].map(a_counts).fillna(0).astype(int)

    findings, recs = _findings(k, turbine_rows, anomalies, fault_hours)

    anomalies_sorted = anomalies.assign(_s=anomalies["severity"].map(SEVERITY_ORDER)).sort_values(
        ["_s", "timestamp"]).drop(columns="_s") if not anomalies.empty else anomalies
    quarantined = db.scalar(select(func.count()).select_from(DataQualityLog)) or 0

    exec_summary = (
        f"In {pd.Timestamp(start):%B %Y} the simulated {int(k['turbines'])}-turbine wind farm produced "
        f"{k['energy_mwh']:,.1f} MWh at an average wind speed of {k['avg_wind_speed_ms']:.2f} m/s. "
        f"Fleet time-based availability was {k['availability_pct']:.2f}% and the capacity factor "
        f"{k['capacity_factor_pct']:.1f}%. Measured energy while running was "
        f"{k['performance_deviation_pct']:+.2f}% versus the reference power curve. "
        f"Downtime totalled {k['downtime_hours']:,.1f} h ({k['planned_downtime_hours']:,.1f} h planned, "
        f"{k['unplanned_downtime_hours']:,.1f} h unplanned, {k['external_downtime_hours']:,.1f} h external) and "
        f"{len(anomalies)} anomalies were raised for investigation."
    )
    return {
        "month": month, "period_start": start.isoformat(), "period_end": end.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"), "disclaimer": DISCLAIMER,
        "executive_summary": exec_summary,
        "kpis": {
            "energy_mwh": _clean(k["energy_mwh"]), "avg_wind_speed_ms": _clean(k["avg_wind_speed_ms"]),
            "availability_pct": _clean(k["availability_pct"]), "capacity_factor_pct": _clean(k["capacity_factor_pct"]),
            "performance_deviation_pct": _clean(k["performance_deviation_pct"]),
            "downtime_hours": _clean(k["downtime_hours"]), "planned_downtime_hours": _clean(k["planned_downtime_hours"]),
            "unplanned_downtime_hours": _clean(k["unplanned_downtime_hours"]),
            "external_downtime_hours": _clean(k["external_downtime_hours"]),
            "environmental_stop_hours": _clean(k["environmental_stop_hours"]),
            "anomaly_count": int(len(anomalies)), "turbines": int(k["turbines"]),
            "data_coverage_pct": _clean(k["data_coverage_pct"]),
        },
        "turbine_performance": _records(turbine_rows),
        "daily_energy": _records(daily[["date", "energy_mwh", "avg_wind_speed_ms", "availability_pct",
                                        "capacity_factor_pct"]]),
        "monthly_energy": _records(monthly[["month", "energy_mwh", "avg_wind_speed_ms", "availability_pct",
                                            "capacity_factor_pct", "performance_deviation_pct"]]),
        "power_curve": _records(pc),
        "downtime": {
            "by_turbine": _records(turbine_rows[["turbine_id", "planned_downtime_hours", "unplanned_downtime_hours",
                                                 "external_downtime_hours", "downtime_hours"]]),
            "by_fault_code": [{"fault_code": c, "hours": round(float(h), 2)} for c, h in fault_hours.items()],
            "service_events": _records(events.sort_values("start_time")) if not events.empty else [],
        },
        "anomalies": {
            "total": int(len(anomalies)),
            "by_severity": {s: int(n) for s, n in anomalies["severity"].value_counts().items()} if len(anomalies) else {},
            "by_type": {s: int(n) for s, n in anomalies["anomaly_type"].value_counts().items()} if len(anomalies) else {},
            "items": _records(anomalies_sorted.head(50)) if len(anomalies) else [],
        },
        "data_quality": {
            "valid_records": int(k["valid_records"]), "analysis_records": int(k["analysis_records"]),
            "flagged_records": int(k["flagged_records"]),
            "missing_data_hours": _clean(k["missing_data_hours"]),
            "data_coverage_pct": _clean(k["data_coverage_pct"]),
            "quarantined_rows_all_imports": int(quarantined),
        },
        "key_findings": findings,
        "recommended_investigations": recs,
        "notes": [
            "Availability: time-based, technical basis (faults and planned maintenance count as unavailable; "
            "grid events and data gaps excluded from eligible time; high-wind stops count as available).",
            "Capacity factor uses hours with valid power data as eligible hours.",
            "Performance deviation = (measured - reference) / reference energy while Running with reference "
            "power >= 50 kW; nacelle anemometer, no air-density correction.",
        ],
    }


def _findings(k, t: pd.DataFrame, anomalies: pd.DataFrame, fault_hours: pd.Series) -> tuple[list[str], list[str]]:
    f, r = [], []
    best = t.loc[t["energy_mwh"].idxmax()]
    worst = t.loc[t["energy_mwh"].idxmin()]
    f.append(f"Highest production: {best['turbine_id']} ({best['energy_mwh']:,.1f} MWh, CF "
             f"{best['capacity_factor_pct']:.1f}%); lowest: {worst['turbine_id']} ({worst['energy_mwh']:,.1f} MWh, "
             f"CF {worst['capacity_factor_pct']:.1f}%).")
    low_av = t[t["availability_pct"] < AVAILABILITY_TARGET_PCT].sort_values("availability_pct")
    if low_av.empty:
        f.append(f"All turbines met the {AVAILABILITY_TARGET_PCT:.0f}% availability reference level.")
    else:
        names = ", ".join(f"{x.turbine_id} ({x.availability_pct:.1f}%)" for x in low_av.itertuples())
        f.append(f"Turbines below the {AVAILABILITY_TARGET_PCT:.0f}% availability reference level: {names}.")
        for x in low_av.itertuples():
            r.append(f"Review the fault and maintenance log for {x.turbine_id}: {x.unplanned_downtime_hours:.1f} h "
                     f"unplanned and {x.planned_downtime_hours:.1f} h planned downtime this month.")
    fleet_dev = k["performance_deviation_pct"]
    lag = t[t["performance_deviation_pct"] < fleet_dev - DEVIATION_GAP_PP]
    f.append(f"Fleet energy while running was {fleet_dev:+.2f}% vs the reference power curve.")
    for x in lag.itertuples():
        f.append(f"{x.turbine_id} deviated {x.performance_deviation_pct:+.2f}% - more than {DEVIATION_GAP_PP:.0f} pp "
                 f"below the fleet.")
        r.append(f"Compare the measured power curve of {x.turbine_id} with its previous months and with "
                 "neighbouring turbines; check pitch/yaw calibration records and anemometer condition.")
    if len(fault_hours):
        f.append(f"Largest unplanned downtime contributor: {fault_hours.index[0]} "
                 f"({fault_hours.iloc[0]:.1f} h across the fleet).")
    if len(anomalies):
        sev = anomalies["severity"].value_counts()
        top = anomalies["turbine_id"].value_counts()
        f.append(f"{len(anomalies)} anomalies raised (High {int(sev.get('High', 0))}, Medium "
                 f"{int(sev.get('Medium', 0))}, Low {int(sev.get('Low', 0))}); most on {top.index[0]} ({top.iloc[0]}).")
        for x in anomalies[anomalies["severity"] == "High"].sort_values("timestamp").head(6).itertuples():
            r.append(f"{x.turbine_id} {pd.Timestamp(x.timestamp):%d %b %H:%M} - {x.anomaly_type} "
                     f"({x.anomaly_id}): {x.recommended_investigation}")
    if k["data_coverage_pct"] < 99:
        f.append(f"Data coverage was {k['data_coverage_pct']:.2f}% - KPIs exclude the missing/invalid intervals.")
        r.append("Check SCADA communication and sensor health for intervals with missing or invalid data.")
    if not r:
        r.append("No specific investigation required beyond routine monitoring.")
    return f, r


def save_report_record(db: Session, report: dict, excel_path: str | None = None, pdf_path: str | None = None) -> None:
    k = report["kpis"]
    rec = db.scalar(select(MonthlyReport).where(MonthlyReport.month == report["month"])) or MonthlyReport(
        month=report["month"])
    rec.generated_at = datetime.now()
    rec.energy_mwh = k["energy_mwh"]
    rec.avg_wind_speed_ms = k["avg_wind_speed_ms"]
    rec.availability_pct = k["availability_pct"]
    rec.capacity_factor_pct = k["capacity_factor_pct"]
    rec.performance_deviation_pct = k["performance_deviation_pct"]
    rec.downtime_hours = k["downtime_hours"]
    rec.anomaly_count = k["anomaly_count"]
    rec.data_coverage_pct = k["data_coverage_pct"]
    rec.summary_json = json.dumps({"executive_summary": report["executive_summary"],
                                   "key_findings": report["key_findings"]})
    rec.excel_path = excel_path or rec.excel_path
    rec.pdf_path = pdf_path or rec.pdf_path
    db.add(rec)
    db.commit()
