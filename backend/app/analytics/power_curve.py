"""Power curve analysis (method of bins, inspired by IEC 61400-12-1).

Measured power curve: mean active power of valid Running records grouped in
0.5 m/s wind-speed bins.
Theoretical (expected) power curve: the reference curve of the turbine model
evaluated at the bin's mean wind speed.

Important caveats (also shown in reports):
* Wind speed is the nacelle anemometer, which sits behind the rotor; a real
  power performance test uses a met mast or nacelle transfer function.
* No air-density normalisation is applied (standard 1.225 kg/m^3 assumed).
* Bins with fewer than MIN_BIN_COUNT records are marked as low-confidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics.performance_calculations import aggregate_deviation_pct
from app.analytics.turbine_model import CUT_OUT_MS, reference_power_kw

MIN_BIN_COUNT = 10


def filter_for_power_curve(df: pd.DataFrame) -> pd.DataFrame:
    mask = (df["operating_status"] == "Running")
    if "is_valid_for_analysis" in df:
        mask &= df["is_valid_for_analysis"].astype(bool)
    mask &= df["wind_speed_ms"].between(0, CUT_OUT_MS) & df["active_power_kw"].notna()
    return df.loc[mask]


def bin_power_curve(df: pd.DataFrame, bin_width: float = 0.5, max_ws: float = CUT_OUT_MS) -> pd.DataFrame:
    """Return one row per wind-speed bin with measured vs expected power."""
    if bin_width <= 0:
        raise ValueError("bin_width must be positive")
    data = filter_for_power_curve(df)
    cols = ["bin_center_ms", "bin_low_ms", "bin_high_ms", "count", "avg_wind_speed_ms", "avg_power_kw",
            "expected_power_kw", "deviation_pct", "std_power_kw", "low_confidence"]
    if data.empty:
        return pd.DataFrame(columns=cols)
    edges = np.arange(0, max_ws + bin_width, bin_width)
    # bins centred on multiples of bin_width: (c - w/2, c + w/2]
    edges = np.concatenate([[0.0], edges[1:] - bin_width / 2, [max_ws + bin_width / 2]])
    cat = pd.cut(data["wind_speed_ms"], edges, include_lowest=True)
    g = data.groupby(cat, observed=True).agg(
        count=("active_power_kw", "size"), avg_wind_speed_ms=("wind_speed_ms", "mean"),
        avg_power_kw=("active_power_kw", "mean"), std_power_kw=("active_power_kw", "std"),
    )
    g = g[g["count"] > 0].reset_index()
    g["bin_low_ms"] = [float(iv.left) for iv in g["wind_speed_ms"]]
    g["bin_high_ms"] = [float(iv.right) for iv in g["wind_speed_ms"]]
    g["bin_center_ms"] = ((g["bin_low_ms"] + g["bin_high_ms"]) / 2).round(2)
    g.loc[g["bin_low_ms"] <= 0, "bin_center_ms"] = 0.0
    g["expected_power_kw"] = reference_power_kw(g["avg_wind_speed_ms"].to_numpy())
    g["deviation_pct"] = aggregate_deviation_pct(g["avg_power_kw"], g["expected_power_kw"])
    g.loc[g["expected_power_kw"] < 50, "deviation_pct"] = np.nan
    g["low_confidence"] = g["count"] < MIN_BIN_COUNT
    out = g[cols].copy()
    num = ["avg_wind_speed_ms", "avg_power_kw", "expected_power_kw", "deviation_pct", "std_power_kw"]
    out[num] = out[num].astype(float).round(2)
    return out


def power_curve_by_turbine(df: pd.DataFrame, bin_width: float = 0.5) -> pd.DataFrame:
    frames = []
    for tid, grp in df.groupby("turbine_id"):
        b = bin_power_curve(grp, bin_width)
        b.insert(0, "turbine_id", tid)
        frames.append(b)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
