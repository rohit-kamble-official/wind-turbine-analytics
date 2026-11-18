"""Reference turbine model (SIMULATED, generic 3.0 MW class).

This is NOT the power curve of any real commercial turbine. It is a generic,
physically plausible curve for a 3.0 MW, 112 m rotor, pitch-regulated,
variable-speed machine, used only to create and analyse synthetic data.

Assumptions (also documented in docs/engineering_assumptions.md):
* Rated power 3000 kW, cut-in 3.0 m/s, rated wind ~13 m/s, cut-out 25 m/s.
* Air density 1.225 kg/m^3 (standard); no density correction is applied.
* Restart after a high-wind stop when wind drops below 22 m/s (hysteresis).
* Rotor speed 6.5-14.0 rpm, gearbox ratio 1:107.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RATED_POWER_KW = 3000.0
CUT_IN_MS = 3.0
RATED_WIND_MS = 13.0
CUT_OUT_MS = 25.0
RESTART_WIND_MS = 22.0
ROTOR_DIAMETER_M = 112.0
HUB_HEIGHT_M = 94.0
GEAR_RATIO = 107.0
MIN_ROTOR_RPM = 6.5
RATED_ROTOR_RPM = 14.0
INTERVAL_MINUTES = 10
INTERVALS_PER_DAY = 24 * 60 // INTERVAL_MINUTES  # 144

# Reference power curve, 0.5 m/s steps (kW). Linear interpolation between points.
_CURVE_WS = np.array(
    [0.0, 2.99, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0,
     10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 25.0]
)
_CURVE_KW = np.array(
    [0.0, 0.0, 25, 70, 130, 205, 295, 400, 525, 670, 835, 1020, 1225, 1450, 1690, 1940, 2190,
     2430, 2640, 2810, 2920, 2975, 2995, 3000, 3000]
)


@dataclass(frozen=True)
class TurbineSpec:
    rated_power_kw: float = RATED_POWER_KW
    cut_in_ms: float = CUT_IN_MS
    rated_wind_ms: float = RATED_WIND_MS
    cut_out_ms: float = CUT_OUT_MS
    rotor_diameter_m: float = ROTOR_DIAMETER_M
    hub_height_m: float = HUB_HEIGHT_M
    model: str = "Generic 3.0 MW / 112 m (simulated)"


DEFAULT_SPEC = TurbineSpec()


def reference_power_kw(wind_speed_ms, rated_power_kw: float = RATED_POWER_KW) -> np.ndarray:
    """Theoretical (expected) power from the reference curve.

    Returns 0 below cut-in and above cut-out, and NaN where wind speed is NaN.
    Negative wind speeds (sensor errors) return NaN, so they never produce a
    misleading expected value.
    """
    ws = np.asarray(wind_speed_ms, dtype=float)
    p = np.interp(ws, _CURVE_WS, _CURVE_KW * (rated_power_kw / RATED_POWER_KW))
    p = np.where(ws > CUT_OUT_MS, 0.0, p)
    p = np.where((ws < 0) | np.isnan(ws), np.nan, p)
    return p


def reference_curve_table(step: float = 0.5) -> list[dict]:
    ws = np.arange(0, CUT_OUT_MS + step, step)
    return [{"wind_speed_ms": float(w), "power_kw": float(p)} for w, p in zip(ws, reference_power_kw(ws))]


def expected_rotor_rpm(wind_speed_ms) -> np.ndarray:
    ws = np.asarray(wind_speed_ms, dtype=float)
    return np.interp(ws, [CUT_IN_MS, 10.0, CUT_OUT_MS], [MIN_ROTOR_RPM, RATED_ROTOR_RPM, RATED_ROTOR_RPM])


def expected_pitch_deg(wind_speed_ms) -> np.ndarray:
    ws = np.asarray(wind_speed_ms, dtype=float)
    return np.where(ws <= 11.5, 0.5, (ws - 11.5) * 1.6)
