"""Energy production.

Energy (kWh) = average power (kW) x time (h). Each SCADA record is a 10-minute
average, so its energy is P_avg x 10/60 h. Intervals with invalid or missing
power are NOT gap-filled; they are reported as data loss instead, so energy
totals are a conservative "measured" figure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics.turbine_model import INTERVAL_MINUTES


def interval_energy_kwh(power_kw, interval_minutes: float = INTERVAL_MINUTES):
    """Energy of one averaging interval. NaN power -> NaN energy (not zero)."""
    return np.asarray(power_kw, dtype=float) * (interval_minutes / 60.0)


def energy_from_power(power_kw, hours: float) -> float:
    """Energy for a constant average power over `hours` (kWh)."""
    if hours < 0:
        raise ValueError("hours must be non-negative")
    return float(power_kw) * float(hours)


_FREQ = {"hourly": "h", "daily": "D", "monthly": "MS"}


def aggregate_energy(df: pd.DataFrame, freq: str = "daily", by_turbine: bool = True,
                     energy_col: str = "energy_kwh") -> pd.DataFrame:
    """Aggregate interval energy to hourly / daily / monthly totals (kWh and MWh)."""
    if freq not in _FREQ:
        raise ValueError(f"freq must be one of {list(_FREQ)}")
    keys = [pd.Grouper(key="timestamp", freq=_FREQ[freq])]
    if by_turbine:
        keys.append("turbine_id")
    g = df.groupby(keys)[energy_col].agg(energy_kwh="sum", intervals="count").reset_index()
    g = g.rename(columns={"timestamp": "period_start"})
    g["energy_mwh"] = g["energy_kwh"] / 1000.0
    return g


def turbine_energy(df: pd.DataFrame, energy_col: str = "energy_kwh") -> pd.DataFrame:
    g = df.groupby("turbine_id")[energy_col].sum().rename("energy_kwh").reset_index()
    g["energy_mwh"] = g["energy_kwh"] / 1000.0
    return g


def farm_total_energy_mwh(df: pd.DataFrame, energy_col: str = "energy_kwh") -> float:
    return float(df[energy_col].sum() / 1000.0)
