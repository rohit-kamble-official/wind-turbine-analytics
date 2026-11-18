from datetime import date

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.analytics.performance_calculations import summarize_period
from app.database import repository as repo
from app.models.models import Anomaly, PerformanceMetric, ScadaReading, ServiceEvent, Turbine


def test_pipeline_loaded_all_tables(loaded_db, db_session):
    assert loaded_db.rows_inserted > 0
    assert db_session.scalar(select(func.count()).select_from(Turbine)) == 4
    # ">=" because the API upload test may have appended a few rows in the same session
    assert db_session.scalar(select(func.count()).select_from(ScadaReading)) >= loaded_db.rows_inserted
    assert db_session.scalar(select(func.count()).select_from(PerformanceMetric)) >= 4 * 20
    assert db_session.scalar(select(func.count()).select_from(ServiceEvent)) > 0
    assert db_session.scalar(select(func.count()).select_from(Anomaly)) > 0


def test_reinsert_is_idempotent(db_session):
    df = repo.scada_query(db_session, repo.SCADA_DB_COLUMNS, turbine_id="WTG01", start=date(2026, 5, 1),
                          end=date(2026, 5, 1))
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    assert len(df) > 100
    assert repo.insert_scada(db_session, df) == 0  # duplicates ignored via unique constraint


def test_unique_constraint_enforced(db_session):
    row = db_session.scalars(select(ScadaReading).limit(1)).first()
    clone = ScadaReading(**{c: getattr(row, c) for c in repo.SCADA_DB_COLUMNS})
    db_session.add(clone)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_indexes_exist():
    idx = {i.name for i in ScadaReading.__table__.indexes}
    assert {"ix_scada_turbine_ts", "ix_scada_ts"} <= idx


def test_sql_aggregation_matches_pandas(db_session):
    m = repo.metrics_frame(db_session)
    k_pd = summarize_period(m)
    k_sql = repo.aggregate_metrics(db_session, None).iloc[0]
    assert k_sql["energy_mwh"] == pytest.approx(k_pd["energy_mwh"], rel=1e-6)
    assert k_sql["availability_pct"] == pytest.approx(k_pd["availability_pct"], rel=1e-6)
    assert k_sql["capacity_factor_pct"] == pytest.approx(k_pd["capacity_factor_pct"], rel=1e-6)
    assert k_sql["downtime_hours"] == pytest.approx(k_pd["downtime_hours"], rel=1e-6)


def test_filters_by_turbine_and_date(db_session):
    by_t = repo.aggregate_metrics(db_session, "turbine")
    total = repo.aggregate_metrics(db_session, None).iloc[0]
    assert by_t["energy_kwh"].sum() == pytest.approx(total["energy_kwh"])
    one = repo.aggregate_metrics(db_session, None, turbine_id="WTG02").iloc[0]
    assert one["energy_kwh"] == pytest.approx(by_t.set_index("turbine_id").loc["WTG02", "energy_kwh"])
    days = repo.aggregate_metrics(db_session, "date", date(2026, 5, 1), date(2026, 5, 3))
    assert [str(d) for d in days["date"]] == ["2026-05-01", "2026-05-02", "2026-05-03"]
    months = repo.aggregate_metrics(db_session, "month")
    assert months["month"].tolist()[:2] == ["2026-04", "2026-05"]
    assert months["energy_kwh"].sum() == pytest.approx(total["energy_kwh"])


def test_quarantine_logged(db_session, loaded_db):
    from app.models.models import DataQualityLog

    assert loaded_db.rows_quarantined > 0
    assert db_session.scalar(select(func.count()).select_from(DataQualityLog)) >= loaded_db.rows_quarantined
