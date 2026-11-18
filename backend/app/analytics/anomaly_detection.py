"""Explainable anomaly detection for SCADA data.

An anomaly is an ALERT FOR INVESTIGATION, not a diagnosis. Every rule records
the measured value, the expected range, a plain-language explanation and a
suggested check. Wording deliberately avoids claiming a root cause.

Methods
-------
1. Power drop            - statistical threshold on actual/expected power, smoothed
                           with a rolling median (30 min), sustained >= 30 min.
2. Sustained underperformance - 7-day rolling mean of daily deviation relative to
                           the fleet median for the same day.
3. High temperature      - absolute limits (gearbox, generator) and a fleet-relative
                           residual (turbine minus fleet median at the same timestamp)
                           with a robust z-score.
4. Rotor speed step      - z-score of 10-min rotor-speed change while wind is steady.
5. Operating condition   - rule checks (running above cut-out, producing while in
                           Fault/Maintenance, running with wind but no output,
                           stuck wind sensor).
6. Isolation Forest      - optional multivariate model on wind, power, rotor speed
                           and pitch per turbine; flags rare combinations.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.analytics.turbine_model import (CUT_IN_MS, CUT_OUT_MS, INTERVAL_MINUTES, RATED_POWER_KW,
                                        expected_pitch_deg, expected_rotor_rpm)

logger = logging.getLogger(__name__)


@dataclass
class AnomalyConfig:
    power_ratio_threshold: float = 0.75
    power_min_expected_kw: float = 300.0
    power_min_intervals: int = 3
    gearbox_limit_medium_c: float = 80.0
    gearbox_limit_high_c: float = 90.0
    generator_limit_medium_c: float = 110.0
    generator_limit_high_c: float = 125.0
    temp_residual_c: float = 12.0
    temp_robust_z: float = 5.0
    rotor_step_rpm: float = 4.0
    rotor_step_z: float = 6.0
    underperf_rel_pct: float = -4.0
    underperf_window_days: int = 7
    underperf_min_days: int = 5
    use_isolation_forest: bool = True
    iforest_contamination: float = 0.0003
    random_state: int = 42


ANOMALY_COLUMNS = [
    "anomaly_id", "turbine_id", "timestamp", "end_timestamp", "duration_minutes", "anomaly_type", "severity",
    "metric", "measured_value", "unit", "expected_range", "explanation", "recommended_investigation",
    "detection_method", "status",
]


def _group_events(df: pd.DataFrame, mask: pd.Series, gap_minutes: int = 2 * INTERVAL_MINUTES) -> pd.DataFrame:
    """Collapse consecutive flagged rows (per turbine) into events."""
    sub = df.loc[mask.fillna(False).astype(bool)].sort_values(["turbine_id", "timestamp"])
    if sub.empty:
        return sub.assign(event_id=pd.Series(dtype=int))
    new = (sub["turbine_id"] != sub["turbine_id"].shift()) | (
        sub["timestamp"].diff() > pd.Timedelta(minutes=gap_minutes))
    return sub.assign(event_id=new.cumsum())


def _summarise(events: pd.DataFrame, value_col: str, how: str = "mean") -> pd.DataFrame:
    g = events.groupby("event_id")
    out = g.agg(turbine_id=("turbine_id", "first"), timestamp=("timestamp", "min"),
                end_timestamp=("timestamp", "max"), n=("timestamp", "size"), value=(value_col, how))
    out["end_timestamp"] = out["end_timestamp"] + pd.Timedelta(minutes=INTERVAL_MINUTES)
    out["duration_minutes"] = out["n"] * INTERVAL_MINUTES
    return out.reset_index(drop=True)


def _rows(ev: pd.DataFrame, **fields) -> list[dict]:
    rows = []
    for _, r in ev.iterrows():
        row = {"turbine_id": r["turbine_id"], "timestamp": r["timestamp"], "end_timestamp": r["end_timestamp"],
               "duration_minutes": int(r["duration_minutes"]), "measured_value": round(float(r["value"]), 2)}
        for k, v in fields.items():
            row[k] = v(r) if callable(v) else v
        rows.append(row)
    return rows


def detect_power_drops(df: pd.DataFrame, cfg: AnomalyConfig) -> list[dict]:
    d = df.sort_values(["turbine_id", "timestamp"]).copy()
    eligible = (d["interval_category"] == "running") & d["is_valid_for_analysis"] & (
        d["theoretical_power_kw"] >= cfg.power_min_expected_kw)
    d["ratio"] = np.where(eligible, d["active_power_kw"] / d["theoretical_power_kw"], np.nan)
    d["ratio_roll"] = d.groupby("turbine_id")["ratio"].transform(
        lambda s: s.rolling(3, center=True, min_periods=2).median())
    flag = eligible & (d["ratio_roll"] < cfg.power_ratio_threshold) & (d["ratio"] < cfg.power_ratio_threshold)
    ev = _group_events(d, flag)
    if ev.empty:
        return []
    s = _summarise(ev, "ratio")
    s = s[s["n"] >= cfg.power_min_intervals]
    s["value"] = s["value"] * 100

    def sev(r):
        deficit = 100 - r["value"]
        return "High" if deficit >= 50 else "Medium" if deficit >= 35 else "Low"

    return _rows(
        s, anomaly_type="Unexpected Power Drop", severity=sev, metric="Actual / expected power", unit="%",
        expected_range=f">= {cfg.power_ratio_threshold:.0%} of reference power",
        explanation=lambda r: (f"Output averaged {r['value']:.0f}% of the reference power curve for "
                               f"{int(r['duration_minutes'])} min while the turbine reported Running."),
        recommended_investigation=("Check for active derating/curtailment commands, controller alarms and "
                                   "pitch behaviour in the period; compare with neighbouring turbines."),
        detection_method="Statistical threshold + 30-min rolling median",
    )


def detect_sustained_underperformance(daily: pd.DataFrame, cfg: AnomalyConfig) -> list[dict]:
    if daily is None or daily.empty:
        return []
    m = daily[["turbine_id", "date", "performance_deviation_pct", "expected_energy_kwh"]].copy()
    m["date"] = pd.to_datetime(m["date"])
    m.loc[m["expected_energy_kwh"] < 2000, "performance_deviation_pct"] = np.nan  # too little wind to judge
    fleet = m.groupby("date")["performance_deviation_pct"].transform("median")
    m["rel"] = m["performance_deviation_pct"] - fleet
    m = m.sort_values(["turbine_id", "date"])
    m["rel_roll"] = m.groupby("turbine_id")["rel"].transform(
        lambda s: s.rolling(cfg.underperf_window_days, min_periods=4).mean())
    m = m.rename(columns={"date": "timestamp"})
    ev = _group_events(m, m["rel_roll"] < cfg.underperf_rel_pct, gap_minutes=2 * 1440)
    if ev.empty:
        return []
    g = ev.groupby("event_id")
    s = g.agg(turbine_id=("turbine_id", "first"), timestamp=("timestamp", "min"),
              end_timestamp=("timestamp", "max"), n=("timestamp", "size"), value=("rel_roll", "mean")).reset_index()
    s = s[s["n"] >= cfg.underperf_min_days]
    s["end_timestamp"] = s["end_timestamp"] + pd.Timedelta(days=1)
    s["duration_minutes"] = s["n"] * 1440

    def sev(r):
        return "High" if r["value"] < -8 else "Medium" if r["value"] < -5 else "Low"

    return _rows(
        s, anomaly_type="Sustained Underperformance", severity=sev, metric="Deviation vs fleet median",
        unit="percentage points", expected_range=f">= {cfg.underperf_rel_pct:.0f} pp vs fleet median",
        explanation=lambda r: (f"Energy-weighted performance deviation was on average {r['value']:.1f} pp below "
                               f"the fleet median over {int(r['n'])} days."),
        recommended_investigation=("Review the turbine's measured power curve against its own history, check "
                                   "pitch/yaw calibration records, anemometer condition and blade inspection notes."),
        detection_method="7-day rolling mean of fleet-relative daily deviation",
    )


def detect_high_temperatures(df: pd.DataFrame, cfg: AnomalyConfig) -> list[dict]:
    rows: list[dict] = []
    d = df.sort_values(["turbine_id", "timestamp"])
    specs = [
        ("gearbox_temperature_c_clean", "Gearbox", cfg.gearbox_limit_medium_c, cfg.gearbox_limit_high_c),
        ("generator_temperature_c_clean", "Generator", cfg.generator_limit_medium_c, cfg.generator_limit_high_c),
    ]
    for col, name, lim_med, lim_high in specs:
        # Absolute limit
        ev = _group_events(d, d[col] > lim_med)
        if not ev.empty:
            s = _summarise(ev, col, "max")
            rows += _rows(
                s, anomaly_type="High Temperature", metric=f"{name} temperature (max)", unit="degC",
                severity=lambda r, h=lim_high: "High" if r["value"] >= h else "Medium",
                expected_range=f"< {lim_med:.0f} degC",
                explanation=lambda r, n=name, lm=lim_med: (
                    f"{n} temperature exceeded the {lm:.0f} degC alert limit, peaking at {r['value']:.1f} degC."),
                recommended_investigation=(f"Review {name.lower()} cooling system status, oil/winding temperature "
                                           "trend and load in the period; confirm sensor reading against a "
                                           "second source before any intervention."),
                detection_method="Absolute temperature threshold",
            )
        # Fleet-relative residual (same timestamp)
        # Compare only turbines that are Running at the same timestamp: a stopped
        # turbine cools down, which would make a running neighbour look "hot".
        # "steady" = running for at least the previous hour (6 intervals), so turbines
        # that just restarted after a stop (still cold) do not distort the reference.
        is_run = (d["interval_category"] == "running").astype(int)
        steady = is_run.groupby(d["turbine_id"]).transform(lambda x: x.rolling(6, min_periods=6).sum()) == 6
        running_vals = d[col].where(steady)
        pivot = d.assign(_v=running_vals).pivot_table(index="timestamp", columns="turbine_id", values="_v",
                                                     aggfunc="first")
        if pivot.shape[1] < 3:
            continue
        pivot = pivot[pivot.notna().sum(axis=1) >= 3]  # need a meaningful fleet reference
        resid = pivot.sub(pivot.median(axis=1), axis=0)
        mad = (resid - resid.median()).abs().median() * 1.4826
        z = resid / mad.replace(0, np.nan)
        flag = (resid > cfg.temp_residual_c) & (z > cfg.temp_robust_z)
        long = pd.DataFrame({"resid": resid.stack(), "flag": flag.stack()}).reset_index()
        ev = _group_events(long, long["flag"])
        if ev.empty:
            continue
        s = _summarise(ev, "resid", "max")
        s = s[s["n"] >= 3]
        rows += _rows(
            s, anomaly_type="Abnormal Temperature (fleet-relative)", metric=f"{name} temp. above fleet median",
            unit="degC", severity=lambda r: "High" if r["value"] >= 20 else "Medium",
            expected_range=f"< +{cfg.temp_residual_c:.0f} degC vs fleet median",
            explanation=lambda r, n=name: (
                f"{n} temperature ran up to {r['value']:.1f} degC above the fleet median at the same time "
                f"for {int(r['duration_minutes'])} min."),
            recommended_investigation=(f"Compare {name.lower()} temperature with this turbine's load and ambient "
                                       "conditions; check cooling fans/filters and recent service work."),
            detection_method="Fleet-relative residual + robust z-score (MAD)",
        )
    return rows


def detect_rotor_speed_steps(df: pd.DataFrame, cfg: AnomalyConfig) -> list[dict]:
    d = df.sort_values(["turbine_id", "timestamp"]).copy()
    g = d.groupby("turbine_id")
    contiguous = g["timestamp"].diff() == pd.Timedelta(minutes=INTERVAL_MINUTES)
    both_running = (d["interval_category"] == "running") & (g["interval_category"].shift() == "running")
    d["rotor_diff"] = g["rotor_speed_rpm"].diff()
    d["wind_diff"] = g["wind_speed_ms"].diff().abs()
    ok = contiguous & both_running & d["wind_diff"].lt(2.0)
    sd = d.loc[ok].groupby("turbine_id")["rotor_diff"].transform(
        lambda s: (s - s.median()).abs().median() * 1.4826)
    d["rotor_z"] = np.nan
    d.loc[ok, "rotor_z"] = d.loc[ok, "rotor_diff"] / sd.replace(0, np.nan)
    flag = ok & (d["rotor_diff"].abs() > cfg.rotor_step_rpm) & (d["rotor_z"].abs() > cfg.rotor_step_z)
    d["abs_diff"] = d["rotor_diff"].abs()
    ev = _group_events(d, flag)
    if ev.empty:
        return []
    s = _summarise(ev, "abs_diff", "max")
    return _rows(
        s, anomaly_type="Sudden Rotor Speed Change", severity="Medium", metric="Rotor speed change in 10 min",
        unit="rpm", expected_range=f"< {cfg.rotor_step_rpm:.0f} rpm per 10 min at steady wind",
        explanation=lambda r: (f"Rotor speed changed by {r['value']:.1f} rpm between consecutive 10-min averages "
                               "while wind speed changed by less than 2 m/s."),
        recommended_investigation=("Check controller event log, speed sensor signals and converter events at "
                                   "this time; verify against high-resolution data if available."),
        detection_method="Z-score of 10-min rotor speed change",
    )


def detect_operating_conditions(df: pd.DataFrame, cfg: AnomalyConfig) -> list[dict]:
    d = df.sort_values(["turbine_id", "timestamp"])
    rows: list[dict] = []
    va = d["is_valid_for_analysis"].astype(bool)

    rules = [
        (va & (d["operating_status"] == "Running") & (d["wind_speed_ms"] > CUT_OUT_MS + 1), "wind_speed_ms",
         "Running Above Cut-out", "High", "Wind speed while Running", "m/s", f"<= {CUT_OUT_MS:.0f} m/s",
         "Turbine reported Running at wind speeds above the cut-out limit.",
         "Verify anemometer reading and high-wind shutdown logic/parameters.", 1),
        (va & d["operating_status"].isin(["Fault", "Maintenance"]) & (d["active_power_kw"] > 100),
         "active_power_kw", "Status / Power Mismatch", "Medium", "Active power while stopped", "kW", "<= 0 kW",
         "Active power was recorded while the turbine status was Fault or Maintenance.",
         "Check status signal mapping and timestamps of status changes.", 1),
        (va & (d["operating_status"] == "Running") & (d["wind_speed_ms"] > CUT_IN_MS + 2)
         & (d["active_power_kw"] <= 0), "wind_speed_ms", "Running Without Output", "Medium",
         "Wind speed with zero output", "m/s", "> 0 kW output above 5 m/s",
         "Turbine reported Running with adequate wind but produced no power.",
         "Check for curtailment commands, grid connection status and converter alarms.", 3),
        (d.get("flag_stuck_sensor", pd.Series(False, index=d.index)).astype(bool), "wind_speed_ms",
         "Sensor Irregularity", "Low", "Constant wind speed reading", "m/s", "Varying signal",
         "Wind speed signal was identical for at least one hour, which is physically unlikely.",
         "Inspect anemometer/sensor and data logger; values excluded from power-curve analysis.", 6),
    ]
    for mask, col, typ, sev, metric, unit, rng_txt, expl, check, min_n in rules:
        ev = _group_events(d, mask)
        if ev.empty:
            continue
        s = _summarise(ev, col, "mean")
        s = s[s["n"] >= min_n]
        rows += _rows(s, anomaly_type=typ, severity=sev, metric=metric, unit=unit, expected_range=rng_txt,
                      explanation=lambda r, e=expl: f"{e} Duration {int(r['duration_minutes'])} min.",
                      recommended_investigation=check, detection_method="Rule-based operating check")
    return rows


def detect_isolation_forest(df: pd.DataFrame, cfg: AnomalyConfig, exclude: list[dict]) -> list[dict]:
    try:
        from sklearn.ensemble import IsolationForest
    except (ImportError, OSError) as exc:  # optional advanced model; rules still run
        logger.warning("Isolation Forest skipped - scikit-learn unavailable: %s", exc)
        return []

    # Physics-normalised residual features: a storm at 22 m/s is rare but normal,
    # so raw wind/power would be flagged; residuals vs the reference curves are not.
    base = ["wind_speed_ms", "active_power_kw", "rotor_speed_rpm", "pitch_angle_deg", "theoretical_power_kw"]
    d = df[(df["interval_category"] == "running") & df["is_valid_for_analysis"].astype(bool)].dropna(subset=base)
    d = d.sort_values(["turbine_id", "timestamp"]).copy()
    d["power_resid"] = (d["active_power_kw"] - d["theoretical_power_kw"]) / RATED_POWER_KW
    d["rotor_resid"] = d["rotor_speed_rpm"] - expected_rotor_rpm(d["wind_speed_ms"])
    d["pitch_resid"] = d["pitch_angle_deg"] - expected_pitch_deg(d["wind_speed_ms"])
    feats = ["power_resid", "rotor_resid", "pitch_resid"]
    flagged = []
    for tid, grp in d.groupby("turbine_id"):
        if len(grp) < 500:
            continue
        model = IsolationForest(n_estimators=100, contamination=cfg.iforest_contamination,
                                random_state=cfg.random_state)
        x = grp[feats].to_numpy()
        model.fit(x)
        raw_score = model.score_samples(x)  # computed once; decision = score - offset
        # don't double-report intervals already covered by an explicit rule
        ts = grp["timestamp"].to_numpy()
        covered = np.zeros(len(grp), dtype=bool)
        for e in exclude:
            if e["turbine_id"] == tid:
                lo, hi = np.searchsorted(ts, np.datetime64(e["timestamp"])), np.searchsorted(
                    ts, np.datetime64(e["end_timestamp"]), side="right")
                covered[lo:hi] = True
        flagged.append(grp.assign(_flag=((raw_score - model.offset_) < 0) & ~covered, _score=-raw_score))
    if not flagged:
        return []
    d2 = pd.concat(flagged)
    ev = _group_events(d2, d2["_flag"])
    if ev.empty:
        return []
    s = _summarise(ev, "_score", "max")
    extra = ev.groupby("event_id").agg(ws=("wind_speed_ms", "mean"), p=("active_power_kw", "mean")).reset_index(drop=True)
    s = s.join(extra)
    return _rows(
        s, anomaly_type="Unusual Wind-Power Relationship", metric="Isolation Forest anomaly score", unit="score",
        severity=lambda r: "Medium" if r["value"] > 0.75 else "Low",
        expected_range="Typical combination for this turbine (score < ~0.6)",
        explanation=lambda r: (f"At ~{r['ws']:.1f} m/s and ~{r['p']:.0f} kW, the combination of power, rotor-speed "
                               "and pitch residuals (vs. reference curves) was rare for this turbine's own history."),
        recommended_investigation=("Plot the period against the turbine's power curve and pitch/rotor-speed "
                                   "curves; treat as low-confidence until confirmed by another signal."),
        detection_method="Isolation Forest (multivariate, per turbine)",
    )


def detect_anomalies(enriched: pd.DataFrame, daily: pd.DataFrame | None = None,
                     cfg: AnomalyConfig | None = None) -> pd.DataFrame:
    cfg = cfg or AnomalyConfig()
    df = enriched[enriched["is_valid_record"].astype(bool)] if "is_valid_record" in enriched else enriched
    rows: list[dict] = []
    rows += detect_power_drops(df, cfg)
    rows += detect_sustained_underperformance(daily, cfg)
    rows += detect_high_temperatures(df, cfg)
    rows += detect_rotor_speed_steps(df, cfg)
    rows += detect_operating_conditions(df, cfg)
    if cfg.use_isolation_forest:
        rows += detect_isolation_forest(df, cfg, exclude=rows)
    if not rows:
        return pd.DataFrame(columns=ANOMALY_COLUMNS)
    out = pd.DataFrame(rows).sort_values(["timestamp", "turbine_id"]).reset_index(drop=True)
    out["status"] = "Open"
    out["anomaly_id"] = [_anomaly_id(r) for r in out.itertuples()]
    out = out.drop_duplicates("anomaly_id")
    return out[ANOMALY_COLUMNS].reset_index(drop=True)


def _anomaly_id(r) -> str:
    """Deterministic ID so re-running detection does not create new identities."""
    key = f"{r.turbine_id}|{pd.Timestamp(r.timestamp):%Y%m%d%H%M}|{r.anomaly_type}|{r.metric}"
    return f"ANO-{r.turbine_id}-{pd.Timestamp(r.timestamp):%Y%m%d-%H%M}-{hashlib.sha1(key.encode()).hexdigest()[:4]}"
