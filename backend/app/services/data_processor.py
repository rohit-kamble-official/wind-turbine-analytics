"""SCADA processing pipeline: load -> validate -> split (clean / quarantine)
-> enrich with derived KPIs -> daily metrics -> anomalies.

Raw input files are never modified. Outputs go to data/processed/.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.analytics.anomaly_detection import AnomalyConfig, detect_anomalies
from app.analytics.performance_calculations import daily_turbine_metrics, enrich_intervals
from app.analytics.turbine_model import RATED_POWER_KW
from app.services.data_quality_report import build_quality_report, write_quality_report
from app.services.data_validator import validate_scada

QUARANTINE_COLUMNS = ["source_row", "timestamp_raw", "turbine_id", "qc_flags"]


@dataclass
class ProcessedData:
    clean: pd.DataFrame        # record-valid rows, flags retained, KPIs added
    quarantine: pd.DataFrame   # rows that cannot be used as records, with reasons
    daily: pd.DataFrame        # performance_metrics rows
    anomalies: pd.DataFrame
    quality: dict


def load_scada_csv(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"timestamp": "string", "turbine_id": "string", "fault_code": "string",
                                    "operating_status": "string"}, keep_default_na=True)


def load_turbines(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path)


def load_service_events(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["start_time", "end_time"])


def process_scada(raw: pd.DataFrame, turbines: pd.DataFrame, run_anomalies: bool = True,
                  anomaly_cfg: AnomalyConfig | None = None) -> ProcessedData:
    known = turbines["turbine_id"].astype(str).tolist()
    rated = float(turbines["rated_power_kw"].iloc[0]) if len(turbines) else RATED_POWER_KW
    result = validate_scada(raw, known_turbines=known, rated_power_kw=rated)
    v = result.data
    quality = build_quality_report(v, known)
    quarantine = v.loc[~v["is_valid_record"]].copy()
    clean = v.loc[v["is_valid_record"]].sort_values(["turbine_id", "timestamp"]).reset_index(drop=True)
    clean = enrich_intervals(clean)
    daily = daily_turbine_metrics(clean, rated_power_kw=rated)
    anomalies = detect_anomalies(clean, daily, anomaly_cfg) if run_anomalies else pd.DataFrame()
    quality["anomalies_detected"] = int(len(anomalies))
    return ProcessedData(clean=clean, quarantine=quarantine, daily=daily, anomalies=anomalies, quality=quality)


def save_processed(p: ProcessedData, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "clean": out_dir / "scada_clean.csv",
        "quarantine": out_dir / "scada_quarantine.csv",
        "daily": out_dir / "daily_turbine_metrics.csv",
        "anomalies": out_dir / "anomalies.csv",
    }
    p.clean.to_csv(paths["clean"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    q_cols = [c for c in QUARANTINE_COLUMNS if c in p.quarantine] + [
        c for c in p.quarantine.columns if c not in QUARANTINE_COLUMNS and not c.startswith("flag_")]
    p.quarantine[q_cols].to_csv(paths["quarantine"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    p.daily.to_csv(paths["daily"], index=False)
    p.anomalies.to_csv(paths["anomalies"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    jp, mp = write_quality_report(p.quality, out_dir)
    paths["quality_json"], paths["quality_md"] = jp, mp
    return paths
