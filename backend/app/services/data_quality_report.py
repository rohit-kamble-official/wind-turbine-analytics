"""Data-quality report built from a validated SCADA frame."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.analytics.turbine_model import INTERVALS_PER_DAY
from app.services.data_validator import FLAG_COLUMNS, summarize_flags

FLAG_DESCRIPTIONS = {
    "invalid_timestamp": "Timestamp missing, unparseable, not a real date or off the 10-min grid (quarantined)",
    "unknown_turbine": "Turbine ID not in the turbine register (quarantined)",
    "duplicate": "Repeated turbine+timestamp; first occurrence kept, repeats quarantined",
    "conflicting_duplicate": "Duplicate whose values differ from the kept record",
    "invalid_status": "Operating status not one of Running/Idle/Fault/Maintenance (quarantined)",
    "missing_value": "Wind speed or active power missing (excluded from energy/power-curve analysis)",
    "negative_wind": "Negative wind speed (excluded from analysis)",
    "wind_out_of_range": "Wind speed above 40 m/s (excluded from analysis)",
    "impossible_power": "Active power > 115% rated or < -100 kW (excluded from analysis)",
    "sensor_range": "Temperature/rotor value outside physical range (value ignored, row kept)",
    "stuck_sensor": "Wind speed constant for >= 1 h (excluded from analysis)",
    "outlier": "Statistical temperature outlier (kept, flagged for investigation)",
}


def build_quality_report(validated: pd.DataFrame, known_turbines: list[str]) -> dict:
    s = summarize_flags(validated)
    rec = validated[validated["is_valid_record"]]
    if rec.empty:
        period_start = period_end = None
        expected_per_turbine = 0
    else:
        period_start = rec["timestamp"].min().normalize()
        period_end = rec["timestamp"].max().normalize()
        expected_per_turbine = ((period_end - period_start).days + 1) * INTERVALS_PER_DAY

    per_turbine = []
    for tid in known_turbines:
        t = rec[rec["turbine_id"] == tid]
        present = int(len(t))
        analysis = int(t["is_valid_for_analysis"].sum())
        per_turbine.append({
            "turbine_id": tid,
            "expected_intervals": expected_per_turbine,
            "valid_records": present,
            "missing_intervals": max(0, expected_per_turbine - present),
            "valid_for_analysis": analysis,
            "completeness_pct": round(present / expected_per_turbine * 100, 2) if expected_per_turbine else 0.0,
            "analysis_ready_pct": round(analysis / expected_per_turbine * 100, 2) if expected_per_turbine else 0.0,
            "flagged_rows": int((t["qc_flags"] != "").sum()),
        })
    expected_total = expected_per_turbine * len(known_turbines)
    missing_total = sum(p["missing_intervals"] for p in per_turbine)
    score = s["valid_for_analysis"] / expected_total * 100 if expected_total else 0.0
    return {
        "data_source": "SIMULATED SCADA data (synthetic, not real operational data)",
        "period_start": str(period_start.date()) if period_start is not None else None,
        "period_end": str(period_end.date()) if period_end is not None else None,
        "turbines": len(known_turbines),
        "expected_intervals": expected_total,
        "missing_intervals": missing_total,
        "quarantined_rows": int((~validated["is_valid_record"]).sum()),
        "data_quality_score_pct": round(score, 2),
        **s,
        "flag_descriptions": {k: FLAG_DESCRIPTIONS.get(k, "") for k in s["flag_counts"]},
        "per_turbine": per_turbine,
    }


def quality_report_markdown(r: dict) -> str:
    lines = [
        "# SCADA Data Quality Report",
        "",
        f"> {r['data_source']}",
        "",
        f"* Period: {r['period_start']} to {r['period_end']}",
        f"* Rows received: {r['total_rows']:,}",
        f"* Valid records: {r['valid_records']:,}",
        f"* Valid for analysis: {r['valid_for_analysis']:,}",
        f"* Quarantined rows: {r['quarantined_rows']:,}",
        f"* Missing 10-min intervals (no record): {r['missing_intervals']:,} of {r['expected_intervals']:,}",
        f"* Data quality score (analysis-ready / expected): **{r['data_quality_score_pct']:.2f}%**",
        "",
        "## Validation flags",
        "",
        "| Flag | Rows | Meaning |",
        "|---|---:|---|",
    ]
    for k, v in r["flag_counts"].items():
        lines.append(f"| {k} | {v:,} | {r['flag_descriptions'].get(k, '')} |")
    lines += ["", "## Completeness by turbine", "",
              "| Turbine | Valid records | Missing intervals | Completeness % | Analysis-ready % | Flagged rows |",
              "|---|---:|---:|---:|---:|---:|"]
    for p in r["per_turbine"]:
        lines.append(f"| {p['turbine_id']} | {p['valid_records']:,} | {p['missing_intervals']:,} | "
                     f"{p['completeness_pct']:.2f} | {p['analysis_ready_pct']:.2f} | {p['flagged_rows']:,} |")
    lines += ["", "## Missing values by column", "", "| Column | Missing |", "|---|---:|"]
    for c, v in r["missing_values_by_column"].items():
        lines.append(f"| {c} | {v:,} |")
    lines += ["", "No record was deleted silently: quarantined rows are in `scada_quarantine.csv` "
              "with their reasons, and flagged rows remain in `scada_clean.csv` with `qc_flags`."]
    return "\n".join(lines) + "\n"


def write_quality_report(r: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "data_quality_report.json", out_dir / "data_quality_report.md"
    jp.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    mp.write_text(quality_report_markdown(r), encoding="utf-8")
    return jp, mp


__all__ = ["build_quality_report", "quality_report_markdown", "write_quality_report", "FLAG_COLUMNS"]
