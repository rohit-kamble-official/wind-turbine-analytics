"""Time-based availability.

Every 10-minute record is put into exactly one category:

| category             | source                                   | default treatment       |
|----------------------|------------------------------------------|-------------------------|
| running              | status Running                           | available               |
| idle_low_wind        | status Idle, no code (wind < cut-in)     | available               |
| environmental_stop   | status Idle, code ENV-HW (wind > cut-out)| available (configurable)|
| planned_maintenance  | status Maintenance                       | unavailable (configurable: excluded) |
| unplanned_fault      | status Fault, turbine-side code          | unavailable             |
| external_grid        | status Fault, external code (F-412)      | excluded (configurable) |
| missing              | expected interval with no valid record   | excluded (configurable) |

Availability (%) = available minutes / eligible minutes x 100
eligible minutes = all minutes - excluded minutes

The default ("technical") basis therefore penalises turbine faults and planned
maintenance, but not grid events or data gaps. The "contractual" basis also
excludes planned maintenance from the denominator.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CATEGORIES = ["running", "idle_low_wind", "environmental_stop", "planned_maintenance",
              "unplanned_fault", "external_grid", "missing"]
ENV_HIGH_WIND = "ENV-HW"
EXTERNAL_CODES = {"F-412"}


@dataclass(frozen=True)
class AvailabilityConfig:
    exclude_planned_maintenance: bool = False
    environmental_counts_available: bool = True
    exclude_external: bool = True
    exclude_missing: bool = True

    @classmethod
    def from_basis(cls, basis: str) -> "AvailabilityConfig":
        if basis == "technical":
            return cls()
        if basis == "contractual":
            return cls(exclude_planned_maintenance=True)
        if basis == "strict":
            return cls(exclude_external=False, exclude_missing=False)
        raise ValueError(f"Unknown availability basis '{basis}' (use technical, contractual or strict)")

    def describe(self) -> str:
        parts = ["available = running + idle (low wind)"]
        parts.append("+ environmental stops" if self.environmental_counts_available else
                     "; environmental stops excluded")
        excl = [n for n, flag in (("planned maintenance", self.exclude_planned_maintenance),
                                  ("external grid events", self.exclude_external),
                                  ("missing data", self.exclude_missing)) if flag]
        if not self.environmental_counts_available:
            excl.append("environmental stops")
        return "; ".join(parts) + (f"; excluded from eligible time: {', '.join(excl)}" if excl else "")


def classify_intervals(status: pd.Series, fault_code: pd.Series) -> pd.Series:
    status = status.astype("string").fillna("")
    code = fault_code.astype("string").fillna("")
    cat = np.select(
        [
            (status == "Fault") & code.isin(EXTERNAL_CODES),
            status == "Fault",
            status == "Maintenance",
            (status == "Idle") & (code == ENV_HIGH_WIND),
            status == "Idle",
            status == "Running",
        ],
        ["external_grid", "unplanned_fault", "planned_maintenance", "environmental_stop", "idle_low_wind",
         "running"],
        default="missing",
    )
    return pd.Series(cat, index=status.index, name="interval_category")


def _col(m, name):
    return m[f"{name}_minutes"] if f"{name}_minutes" in m else m.get(name, 0)


def availability_components(minutes, cfg: AvailabilityConfig = AvailabilityConfig()):
    """Return (available, eligible) minutes. Works with dicts, Series rows or DataFrames
    whose keys/columns are `<category>_minutes`."""
    running = _col(minutes, "running")
    idle = _col(minutes, "idle_low_wind")
    env = _col(minutes, "environmental_stop")
    planned = _col(minutes, "planned_maintenance")
    fault = _col(minutes, "unplanned_fault")
    external = _col(minutes, "external_grid")
    missing = _col(minutes, "missing")

    available = running + idle + (env if cfg.environmental_counts_available else 0)
    eligible = running + idle + fault
    eligible = eligible + (env if cfg.environmental_counts_available else 0)
    eligible = eligible + (0 if cfg.exclude_planned_maintenance else planned)
    eligible = eligible + (0 if cfg.exclude_external else external)
    eligible = eligible + (0 if cfg.exclude_missing else missing)
    return available, eligible


def availability_pct(minutes, cfg: AvailabilityConfig = AvailabilityConfig()):
    available, eligible = availability_components(minutes, cfg)
    if np.isscalar(eligible):
        return float(available / eligible * 100) if eligible > 0 else None
    eligible = pd.Series(eligible, dtype=float)
    return (pd.Series(available, dtype=float) / eligible.replace(0, np.nan) * 100).round(3)
