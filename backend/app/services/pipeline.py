"""End-to-end orchestration: CSV -> validation -> analytics -> database.

Also handles incremental uploads: validate the upload, insert new records
(duplicates against the database are ignored), then recompute fleet analytics
from the database so KPIs and anomalies stay consistent.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import db as dbm
from app.database import repository as repo
from app.models.models import ImportBatch
from app.services.data_processor import (load_scada_csv, load_service_events, load_turbines, process_scada,
                                         save_processed)
from app.services.data_validator import validate_scada

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    rows_received: int
    rows_inserted: int
    rows_quarantined: int
    metrics_rows: int
    anomalies: int
    quality_score_pct: float
    seconds: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def run_full_pipeline(scada_csv: Path | None = None, turbines_csv: Path | None = None,
                      events_csv: Path | None = None, reset: bool = True, processed_dir: Path | None = None,
                      run_anomalies: bool = True) -> PipelineResult:
    t0 = time.perf_counter()
    gen = settings.generated_dir
    scada_csv = scada_csv or gen / "scada_data.csv"
    turbines_csv = turbines_csv or gen / "turbines.csv"
    events_csv = events_csv or gen / "service_events.csv"
    processed_dir = processed_dir or settings.processed_dir
    for p in (scada_csv, turbines_csv, events_csv):
        if not Path(p).exists():
            raise FileNotFoundError(f"{p} not found - run scripts/generate_data.py first")

    raw = load_scada_csv(scada_csv)
    turbines = load_turbines(turbines_csv)
    events = load_service_events(events_csv)
    logger.info("Processing %s rows", len(raw))
    processed = process_scada(raw, turbines, run_anomalies=run_anomalies)
    save_processed(processed, processed_dir)

    dbm.init_db(drop=reset)
    Session = dbm.get_sessionmaker()
    with Session() as db:
        repo.upsert_turbines(db, turbines)
        repo.replace_service_events(db, events)
        inserted = repo.insert_scada(db, processed.clean)
        n_metrics = repo.replace_metrics(db, processed.daily)
        n_anom = repo.replace_anomalies(db, processed.anomalies)
        batch = ImportBatch(source=str(Path(scada_csv).name), imported_at=datetime.now(),
                            rows_received=len(raw), rows_inserted=inserted,
                            rows_already_present=int(len(processed.clean) - inserted),
                            rows_quarantined=len(processed.quarantine),
                            rows_flagged=int((processed.clean["qc_flags"] != "").sum()),
                            status="completed", message="Initial pipeline load")
        db.add(batch)
        db.commit()
        repo.log_quarantine(db, processed.quarantine, batch.id)
    return PipelineResult(len(raw), inserted, len(processed.quarantine), n_metrics, n_anom,
                          processed.quality["data_quality_score_pct"], round(time.perf_counter() - t0, 1))


def ingest_upload(db: Session, raw: pd.DataFrame, source: str) -> ImportBatch:
    """Validate and insert an uploaded SCADA CSV. Raises SchemaValidationError
    for missing columns. Analytics recompute is done separately (background)."""
    turbines = repo.turbine_ids(db)
    result = validate_scada(raw, known_turbines=turbines, rated_power_kw=repo.rated_power_kw(db))
    v = result.data
    clean = v[v["is_valid_record"]].copy()
    from app.analytics.availability import classify_intervals

    clean["interval_category"] = classify_intervals(clean["operating_status"], clean["fault_code"])
    inserted = repo.insert_scada(db, clean)
    quarantine = v[~v["is_valid_record"]]
    batch = ImportBatch(source=source, imported_at=datetime.now(), rows_received=len(raw),
                        rows_inserted=inserted, rows_already_present=int(len(clean) - inserted),
                        rows_quarantined=len(quarantine), rows_flagged=int((clean["qc_flags"] != "").sum()),
                        status="recomputing" if inserted else "completed",
                        message=None if inserted else "No new records - analytics unchanged")
    db.add(batch)
    db.commit()
    repo.log_quarantine(db, quarantine, batch.id)
    raw_path = settings.raw_dir / f"upload_{batch.id:04d}_{Path(source).name}"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(raw_path, index=False)  # keep the original upload for traceability
    return batch


def recompute_analytics(batch_id: int | None = None) -> None:
    """Re-validate all stored readings and rebuild metrics + anomalies."""
    Session = dbm.get_sessionmaker()
    with Session() as db:
        try:
            raw = repo.load_scada_for_recompute(db)
            turbines = repo.turbines_frame(db)
            processed = process_scada(raw, turbines)
            # refresh per-row flags/categories on stored readings is not needed for KPIs:
            # metrics and anomalies are rebuilt from the re-validated frame.
            repo.replace_metrics(db, processed.daily)
            repo.replace_anomalies(db, processed.anomalies)
            from sqlalchemy import func

            from app.models.models import DataQualityLog
            processed.quality["quarantined_rows"] = int(
                db.scalar(select(func.count()).select_from(DataQualityLog)) or 0)
            processed.quality["note"] = "Recomputed from database after upload; quarantined rows from all imports"
            qpath = settings.processed_dir / "data_quality_report_latest.json"
            qpath.parent.mkdir(parents=True, exist_ok=True)
            qpath.write_text(json.dumps(processed.quality, indent=2, default=str), encoding="utf-8")
            status, msg = "completed", f"Recomputed metrics ({len(processed.daily)} rows) and anomalies " \
                                       f"({len(processed.anomalies)})"
        except Exception as exc:  # pragma: no cover - surfaced through batch status
            logger.exception("Recompute failed")
            status, msg = "failed", str(exc)
        if batch_id is not None:
            batch = db.get(ImportBatch, batch_id)
            if batch:
                batch.status, batch.message = status, msg
                db.commit()


def latest_batches(db: Session, limit: int = 10) -> list[ImportBatch]:
    return list(db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(limit)))
