"""Downtime analysis.

Downtime = time a turbine is not available to generate for a turbine- or
grid-related reason. Categories:
* planned   - status Maintenance (PM-* codes)
* unplanned - status Fault with a turbine-side fault code
* external  - status Fault with an external code (grid disturbance)
Environmental stops (high wind) and data gaps are reported separately and are
NOT downtime.
"""
from __future__ import annotations

import pandas as pd

from app.analytics.availability import CATEGORIES

DOWNTIME_CATEGORIES = {
    "planned_maintenance": "Planned maintenance",
    "unplanned_fault": "Unplanned fault",
    "external_grid": "External / grid",
}


def downtime_summary(daily: pd.DataFrame) -> dict:
    """Totals (hours) from daily metric rows."""
    sums = daily[[f"{c}_minutes" for c in CATEGORIES]].sum() / 60
    planned = float(sums["planned_maintenance_minutes"])
    unplanned = float(sums["unplanned_fault_minutes"])
    external = float(sums["external_grid_minutes"])
    return {
        "total_downtime_hours": round(planned + unplanned + external, 2),
        "planned_hours": round(planned, 2),
        "unplanned_hours": round(unplanned, 2),
        "fault_related_hours": round(unplanned + external, 2),
        "external_hours": round(external, 2),
        "environmental_stop_hours": round(float(sums["environmental_stop_minutes"]), 2),
        "missing_data_hours": round(float(sums["missing_minutes"]), 2),
    }


def downtime_by_turbine(daily: pd.DataFrame) -> pd.DataFrame:
    cols = [f"{c}_minutes" for c in DOWNTIME_CATEGORIES] + ["environmental_stop_minutes"]
    g = daily.groupby("turbine_id")[cols].sum() / 60
    g.columns = [c.replace("_minutes", "_hours") for c in g.columns]
    g["total_downtime_hours"] = g[[f"{c}_hours" for c in DOWNTIME_CATEGORIES]].sum(axis=1)
    return g.round(2).reset_index()


def downtime_by_fault_code(intervals: pd.DataFrame) -> pd.DataFrame:
    """Hours per fault code from interval-level data (10 min each)."""
    d = intervals[intervals["interval_category"].isin(DOWNTIME_CATEGORIES)]
    g = d.groupby(["fault_code", "interval_category"]).size().rename("intervals").reset_index()
    g["hours"] = g["intervals"] * 10 / 60
    return g.sort_values("hours", ascending=False).reset_index(drop=True)


def service_event_stats(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["fault_code", "event_type", "events", "total_hours", "mean_hours"])
    g = events.groupby(["fault_code", "event_type"])["duration_hours"].agg(
        events="count", total_hours="sum", mean_hours="mean").reset_index()
    return g.round(2).sort_values("total_hours", ascending=False)
