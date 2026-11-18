"""SCADA data validation.

Principle: never silently delete. Every rule adds a boolean flag column and a
human-readable reason to `qc_flags`. Two derived masks drive downstream use:

* `is_valid_record`  - the row is a usable 10-min record (parseable timestamp,
  known turbine, first occurrence of turbine+timestamp). Used for availability
  and downtime because the operating status is still trustworthy.
* `is_valid_for_analysis` - additionally the wind and power measurements are
  plausible. Used for energy, power-curve and performance-deviation work.

Statistical outliers (`flag_outlier`) are flagged for investigation but do NOT
invalidate the row, because an unusual value may be a genuine event.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.analytics import turbine_model as tm

REQUIRED_COLUMNS = [
    "timestamp", "turbine_id", "wind_speed_ms", "ambient_temperature_c", "rotor_speed_rpm",
    "generator_speed_rpm", "active_power_kw", "theoretical_power_kw", "reactive_power_kvar",
    "nacelle_temperature_c", "gearbox_temperature_c", "generator_temperature_c", "pitch_angle_deg",
    "yaw_angle_deg", "operating_status", "fault_code", "downtime_minutes",
]
NUMERIC_COLUMNS = [c for c in REQUIRED_COLUMNS if c not in ("timestamp", "turbine_id", "operating_status", "fault_code")]
CRITICAL_COLUMNS = ["wind_speed_ms", "active_power_kw"]
VALID_STATUSES = {"Running", "Idle", "Fault", "Maintenance"}
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# Physical plausibility limits (beyond these the sensor value is treated as invalid)
LIMITS = {
    "wind_speed_ms": (0.0, 40.0),
    "ambient_temperature_c": (-40.0, 50.0),
    "rotor_speed_rpm": (0.0, 20.0),
    "nacelle_temperature_c": (-40.0, 80.0),
    "gearbox_temperature_c": (-35.0, 130.0),
    "generator_temperature_c": (-35.0, 180.0),
    "pitch_angle_deg": (-5.0, 95.0),
    "yaw_angle_deg": (0.0, 360.0),
}
TEMPERATURE_COLUMNS = ["ambient_temperature_c", "nacelle_temperature_c", "gearbox_temperature_c",
                       "generator_temperature_c"]
# Auxiliary consumption makes small negative power normal; below this is impossible
MIN_POWER_KW = -100.0
MAX_POWER_FACTOR = 1.15  # x rated power
STUCK_SENSOR_INTERVALS = 6  # identical wind reading for >= 1 hour


class SchemaValidationError(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing required columns: {', '.join(missing)}")


@dataclass
class ValidationResult:
    data: pd.DataFrame
    summary: dict = field(default_factory=dict)


def check_required_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def _add_reason(reasons: pd.Series, mask: pd.Series, text: str) -> pd.Series:
    return reasons.where(~mask, reasons + np.where(reasons == "", "", ";") + text)


def validate_scada(df: pd.DataFrame, known_turbines: list[str] | None = None,
                   rated_power_kw: float = tm.RATED_POWER_KW) -> ValidationResult:
    missing_cols = check_required_columns(df)
    if missing_cols:
        raise SchemaValidationError(missing_cols)

    out = df.copy()
    out["source_row"] = np.arange(len(out))
    raw_ts = out["timestamp"].astype("string")
    out["timestamp_raw"] = raw_ts.fillna("")
    for c in NUMERIC_COLUMNS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["turbine_id"] = out["turbine_id"].astype("string").str.strip()
    out["operating_status"] = out["operating_status"].astype("string").str.strip()
    out["fault_code"] = out["fault_code"].astype("string").fillna("").str.strip()

    reasons = pd.Series("", index=out.index, dtype=object)

    # 1. Timestamps: strict format, real calendar date, on the 10-minute grid
    ts = pd.to_datetime(raw_ts, format=TIMESTAMP_FORMAT, errors="coerce")
    off_grid = ts.notna() & ((ts.dt.minute % tm.INTERVAL_MINUTES != 0) | (ts.dt.second != 0))
    out["timestamp"] = ts
    out["flag_invalid_timestamp"] = ts.isna() | off_grid
    reasons = _add_reason(reasons, out["flag_invalid_timestamp"], "invalid_timestamp")

    # 2. Turbine identifiers
    if known_turbines is not None:
        out["flag_unknown_turbine"] = ~out["turbine_id"].isin(known_turbines).fillna(False).astype(bool)
    else:
        out["flag_unknown_turbine"] = ~out["turbine_id"].str.fullmatch(r"WTG\d{2}").fillna(False).astype(bool)
    reasons = _add_reason(reasons, out["flag_unknown_turbine"], "unknown_turbine_id")

    # 3. Duplicates on the natural key; first occurrence kept as the record
    key_ok = ~out["flag_invalid_timestamp"]
    dup = out.duplicated(subset=["turbine_id", "timestamp"], keep="first") & key_ok
    first_of_group = out.duplicated(subset=["turbine_id", "timestamp"], keep=False) & key_ok & ~dup
    out["flag_duplicate"] = dup
    exact_dup = out.duplicated(subset=REQUIRED_COLUMNS, keep="first") & key_ok
    out["flag_conflicting_duplicate"] = dup & ~exact_dup
    reasons = _add_reason(reasons, dup & exact_dup, "duplicate_exact")
    reasons = _add_reason(reasons, out["flag_conflicting_duplicate"], "duplicate_conflicting_values")
    out["has_duplicates"] = first_of_group

    # 4. Status values
    out["flag_invalid_status"] = ~out["operating_status"].isin(VALID_STATUSES).fillna(False).astype(bool)
    reasons = _add_reason(reasons, out["flag_invalid_status"], "invalid_operating_status")

    # 5. Missing values in critical fields
    out["flag_missing_value"] = out[CRITICAL_COLUMNS].isna().any(axis=1)
    reasons = _add_reason(reasons, out["wind_speed_ms"].isna(), "missing_wind_speed")
    reasons = _add_reason(reasons, out["active_power_kw"].isna(), "missing_active_power")

    # 6. Wind speed plausibility
    out["flag_negative_wind"] = out["wind_speed_ms"] < 0
    out["flag_wind_out_of_range"] = out["wind_speed_ms"] > LIMITS["wind_speed_ms"][1]
    reasons = _add_reason(reasons, out["flag_negative_wind"], "negative_wind_speed")
    reasons = _add_reason(reasons, out["flag_wind_out_of_range"], "wind_speed_above_40ms")

    # 7. Impossible power values
    out["flag_impossible_power"] = (out["active_power_kw"] > rated_power_kw * MAX_POWER_FACTOR) | (
        out["active_power_kw"] < MIN_POWER_KW)
    reasons = _add_reason(reasons, out["flag_impossible_power"], "impossible_active_power")

    # 8. Temperature / rotor sensor plausibility (value-level, row stays usable)
    temp_bad = pd.Series(False, index=out.index)
    for c in TEMPERATURE_COLUMNS + ["rotor_speed_rpm"]:
        lo, hi = LIMITS[c]
        bad = (out[c] < lo) | (out[c] > hi)
        temp_bad |= bad
        reasons = _add_reason(reasons, bad, f"{c}_out_of_physical_range")
    out["flag_sensor_range"] = temp_bad

    # 9. Stuck wind sensor (identical non-zero value for >= 1 h, per turbine)
    out["flag_stuck_sensor"] = False
    valid_order = out[key_ok & ~dup].sort_values(["turbine_id", "timestamp"])
    if len(valid_order):
        ws = valid_order["wind_speed_ms"]
        same = ws.eq(ws.shift()) & valid_order["turbine_id"].eq(valid_order["turbine_id"].shift())
        run_id = (~same).cumsum()
        run_len = run_id.map(run_id.value_counts())
        stuck_idx = valid_order.index[(run_len >= STUCK_SENSOR_INTERVALS) & (ws > 0)]
        out.loc[stuck_idx, "flag_stuck_sensor"] = True
    reasons = _add_reason(reasons, out["flag_stuck_sensor"], "stuck_wind_sensor")

    # 10. Statistical outliers on temperatures (robust: median +/- 6 * MAD per turbine)
    out["flag_outlier"] = False
    for c in ("gearbox_temperature_c", "generator_temperature_c", "nacelle_temperature_c"):
        plausible = out[c].where(~((out[c] < LIMITS[c][0]) | (out[c] > LIMITS[c][1])))
        grp = plausible.groupby(out["turbine_id"])
        med = grp.transform("median")
        mad = grp.transform(lambda s: (s - s.median()).abs().median()) * 1.4826
        z = (plausible - med) / mad.replace(0, np.nan)
        o = z.abs() > 6
        out.loc[o.fillna(False), "flag_outlier"] = True
        reasons = _add_reason(reasons, o.fillna(False), f"{c}_statistical_outlier")

    out["qc_flags"] = reasons
    out["is_valid_record"] = ~(out["flag_invalid_timestamp"] | out["flag_unknown_turbine"]
                               | out["flag_duplicate"] | out["flag_invalid_status"])
    out["is_valid_for_analysis"] = out["is_valid_record"] & ~(
        out["flag_missing_value"] | out["flag_negative_wind"] | out["flag_wind_out_of_range"]
        | out["flag_impossible_power"] | out["flag_stuck_sensor"])

    summary = summarize_flags(out)
    return ValidationResult(out, summary)


FLAG_COLUMNS = [
    "flag_invalid_timestamp", "flag_unknown_turbine", "flag_duplicate", "flag_conflicting_duplicate",
    "flag_invalid_status", "flag_missing_value", "flag_negative_wind", "flag_wind_out_of_range",
    "flag_impossible_power", "flag_sensor_range", "flag_stuck_sensor", "flag_outlier",
]


def summarize_flags(df: pd.DataFrame) -> dict:
    total = int(len(df))
    counts = {c.removeprefix("flag_"): int(df[c].sum()) for c in FLAG_COLUMNS if c in df}
    return {
        "total_rows": total,
        "valid_records": int(df["is_valid_record"].sum()),
        "valid_for_analysis": int(df["is_valid_for_analysis"].sum()),
        "rows_with_any_flag": int((df["qc_flags"] != "").sum()),
        "flag_counts": counts,
        "missing_values_by_column": {c: int(df[c].isna().sum()) for c in NUMERIC_COLUMNS if c in df},
    }
