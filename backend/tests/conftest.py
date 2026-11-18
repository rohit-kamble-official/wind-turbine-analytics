"""Shared fixtures.

A small simulated dataset (4 turbines x 20 days, with injected data errors) is
generated once per test session into a temporary folder, and the full pipeline
loads it into a temporary SQLite database. Tests never touch data/ or the real DB.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics import turbine_model as tm
from app.core.config import settings
from app.database import db as dbm
from app.services.generate_dataset import GeneratorConfig, generate_dataset, write_dataset

SMALL = GeneratorConfig(n_turbines=4, start="2026-04-25", end="2026-05-14", seed=7, inject_errors=True)


@pytest.fixture(scope="session")
def workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("wta")
    settings.data_dir = root / "data"
    settings.reports_dir = root / "reports"
    settings.powerbi_dir = root / "powerbi"
    settings.database_url = f"sqlite:///{(root / 'test.db').as_posix()}"
    settings.ensure_dirs()
    dbm.configure(settings.database_url)
    return root


@pytest.fixture(scope="session")
def small_dataset(workspace):
    ds = generate_dataset(SMALL)
    write_dataset(ds, settings.generated_dir)
    return ds


@pytest.fixture(scope="session")
def loaded_db(small_dataset):
    from app.services.pipeline import run_full_pipeline

    result = run_full_pipeline(reset=True)
    return result


@pytest.fixture()
def db_session(loaded_db):
    s = dbm.get_sessionmaker()()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def client(loaded_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def make_scada(n: int = 6, turbine: str = "WTG01", start: str = "2026-01-01 00:00:00", ws=8.0, power=None,
               status: str = "Running", code: str = "") -> pd.DataFrame:
    """Hand-made, fully valid SCADA rows for unit tests."""
    ts = pd.date_range(start, periods=n, freq="10min")
    ws_arr = np.full(n, ws, dtype=float) if np.isscalar(ws) else np.asarray(ws, dtype=float)
    theo = tm.reference_power_kw(ws_arr)
    p = theo if power is None else (np.full(n, power, dtype=float) if np.isscalar(power) else np.asarray(power, float))
    return pd.DataFrame({
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "turbine_id": turbine,
        "wind_speed_ms": ws_arr + np.arange(n) * 0.01,  # tiny variation so it never looks "stuck"
        "ambient_temperature_c": 10.0, "rotor_speed_rpm": 12.0, "generator_speed_rpm": 1284.0,
        "active_power_kw": p, "theoretical_power_kw": theo, "reactive_power_kvar": 20.0,
        "nacelle_temperature_c": 25.0, "gearbox_temperature_c": 60.0, "generator_temperature_c": 70.0,
        "pitch_angle_deg": 1.0, "yaw_angle_deg": 180.0, "operating_status": status, "fault_code": code,
        "downtime_minutes": 10 if status in ("Fault", "Maintenance") else 0,
    })
