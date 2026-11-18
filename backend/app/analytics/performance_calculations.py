"""Core KPI calculations: capacity factor, performance deviation and the daily
per-turbine metric table that feeds the database and the API.

Formulas
--------
Capacity factor (%)  = actual energy / (rated power x eligible hours) x 100
    eligible hours   = hours with a valid power measurement (data gaps are not
                       counted against the turbine; they are reported separately)
Performance deviation (%) = (actual - expected) / expected x 100
    expected = reference power curve at the measured nacelle wind speed.
    Evaluated only while Running and expected >= MIN_EXPECTED_KW; otherwise
    undefined (NaN) - a ratio against ~0 kW expected power is meaningless.
    Aggregated deviation is energy-weighted: (sum actual - sum expected) / sum expected.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics import availability as av
from app.analytics.turbine_model import INTERVAL_MINUTES, RATED_POWER_KW

MIN_EXPECTED_KW = 50.0
MINUTES_PER_DAY = 1440


def capacity_factor_pct(energy_kwh, rated_power_kw: float, eligible_hours):
    energy = np.asarray(energy_kwh, dtype=float)
    hours = np.asarray(eligible_hours, dtype=float)
    max_energy = rated_power_kw * hours
    with np.errstate(divide="ignore", invalid="ignore"):
        cf = np.where(max_energy > 0, energy / max_energy * 100.0, np.nan)
    return float(cf) if cf.ndim == 0 else cf


def performance_deviation_pct(actual_kw, expected_kw, min_expected_kw: float = MIN_EXPECTED_KW):
    """Point-wise deviation. Returns NaN when expected power is below the
    threshold (including zero), so no division by zero or exploding ratios."""
    a = np.asarray(actual_kw, dtype=float)
    e = np.asarray(expected_kw, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        dev = np.where(e >= min_expected_kw, (a - e) / e * 100.0, np.nan)
    return float(dev) if dev.ndim == 0 else dev


def aggregate_deviation_pct(actual_sum, expected_sum):
    """Energy-weighted deviation from summed actual and expected energy."""
    a = np.asarray(actual_sum, dtype=float)
    e = np.asarray(expected_sum, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        dev = np.where(e > 0, (a - e) / e * 100.0, np.nan)
    return float(dev) if dev.ndim == 0 else dev


def enrich_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """Add interval-level derived columns to a validated, record-valid frame."""
    out = df.copy()
    out["interval_category"] = av.classify_intervals(out["operating_status"], out["fault_code"])
    valid = out["is_valid_for_analysis"].astype(bool)
    hours = INTERVAL_MINUTES / 60.0
    out["energy_kwh"] = np.where(valid, out["active_power_kw"] * hours, np.nan)
    running_eval = valid & (out["interval_category"] == "running") & (
        out["theoretical_power_kw"] >= MIN_EXPECTED_KW)
    out["deviation_eligible"] = running_eval
    out["expected_energy_kwh"] = np.where(running_eval, out["theoretical_power_kw"] * hours, np.nan)
    out["running_energy_kwh"] = np.where(running_eval, out["active_power_kw"] * hours, np.nan)
    out["performance_deviation_pct"] = np.where(
        running_eval, performance_deviation_pct(out["active_power_kw"], out["theoretical_power_kw"]), np.nan)
    temp_ok = ~out.get("flag_sensor_range", pd.Series(False, index=out.index)).astype(bool)
    for c in ("gearbox_temperature_c", "generator_temperature_c", "nacelle_temperature_c",
              "ambient_temperature_c"):
        out[f"{c}_clean"] = out[c].where(temp_ok & out[c].between(-40, 180))
    return out


def daily_turbine_metrics(enriched: pd.DataFrame, rated_power_kw: float = RATED_POWER_KW,
                          cfg: av.AvailabilityConfig = av.AvailabilityConfig()) -> pd.DataFrame:
    """One row per turbine per calendar day (the `performance_metrics` table)."""
    df = enriched.copy()
    df["date"] = df["timestamp"].dt.normalize()
    df["_minutes"] = INTERVAL_MINUTES
    df["_wind_valid"] = df["wind_speed_ms"].where(df["is_valid_for_analysis"])

    cat_min = df.pivot_table(index=["turbine_id", "date"], columns="interval_category", values="_minutes",
                             aggfunc="sum", fill_value=0)
    for c in av.CATEGORIES:
        if c not in cat_min:
            cat_min[c] = 0
    cat_min = cat_min[av.CATEGORIES].add_suffix("_minutes")

    g = df.groupby(["turbine_id", "date"])
    agg = g.agg(
        energy_kwh=("energy_kwh", "sum"),
        running_energy_kwh=("running_energy_kwh", "sum"),
        expected_energy_kwh=("expected_energy_kwh", "sum"),
        avg_wind_speed_ms=("_wind_valid", "mean"),
        max_wind_speed_ms=("_wind_valid", "max"),
        avg_power_kw=("energy_kwh", lambda s: s.mean() * 60 / INTERVAL_MINUTES if s.notna().any() else np.nan),
        avg_ambient_temp_c=("ambient_temperature_c_clean", "mean"),
        avg_nacelle_temp_c=("nacelle_temperature_c_clean", "mean"),
        avg_gearbox_temp_c=("gearbox_temperature_c_clean", "mean"),
        max_gearbox_temp_c=("gearbox_temperature_c_clean", "max"),
        avg_generator_temp_c=("generator_temperature_c_clean", "mean"),
        max_generator_temp_c=("generator_temperature_c_clean", "max"),
        valid_records=("is_valid_record", "sum"),
        analysis_records=("is_valid_for_analysis", "sum"),
        flagged_records=("qc_flags", lambda s: int((s != "").sum())),
        downtime_minutes=("downtime_minutes", "sum"),
    )
    m = agg.join(cat_min).reset_index()
    recorded = m[[f"{c}_minutes" for c in av.CATEGORIES if c != "missing"]].sum(axis=1)
    m["missing_minutes"] = (MINUTES_PER_DAY - recorded).clip(lower=0)
    m["energy_data_minutes"] = m["analysis_records"] * INTERVAL_MINUTES
    m["data_coverage_pct"] = (m["analysis_records"] * INTERVAL_MINUTES / MINUTES_PER_DAY * 100).round(2)
    m["availability_pct"] = availability_pct_frame(m, cfg)
    m["capacity_factor_pct"] = capacity_factor_pct(m["energy_kwh"], rated_power_kw, m["energy_data_minutes"] / 60)
    m["performance_deviation_pct"] = aggregate_deviation_pct(m["running_energy_kwh"], m["expected_energy_kwh"])
    m["date"] = m["date"].dt.date
    num = m.select_dtypes("number").columns
    m[num] = m[num].round(3)
    return m


def availability_pct_frame(m: pd.DataFrame, cfg: av.AvailabilityConfig) -> pd.Series:
    return av.availability_pct(m, cfg)


def summarize_period(m: pd.DataFrame, rated_power_kw: float = RATED_POWER_KW,
                     cfg: av.AvailabilityConfig = av.AvailabilityConfig()) -> dict:
    """Roll daily rows up to a single KPI set (sums first, ratios last)."""
    if m.empty:
        return {}
    sums = m[[f"{c}_minutes" for c in av.CATEGORIES] + ["energy_kwh", "running_energy_kwh",
                                                       "expected_energy_kwh", "energy_data_minutes"]].sum()
    avail, elig = av.availability_components(sums, cfg)
    wind_w = (m["avg_wind_speed_ms"] * m["analysis_records"]).sum()
    n_an = m["analysis_records"].sum()
    return {
        "energy_mwh": float(sums["energy_kwh"] / 1000),
        "avg_wind_speed_ms": float(wind_w / n_an) if n_an else None,
        "availability_pct": float(avail / elig * 100) if elig else None,
        "capacity_factor_pct": capacity_factor_pct(sums["energy_kwh"], rated_power_kw,
                                                   sums["energy_data_minutes"] / 60),
        "performance_deviation_pct": aggregate_deviation_pct(sums["running_energy_kwh"],
                                                             sums["expected_energy_kwh"]),
        "downtime_hours": float((sums["planned_maintenance_minutes"] + sums["unplanned_fault_minutes"]
                                 + sums["external_grid_minutes"]) / 60),
    }
