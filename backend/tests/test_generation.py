import numpy as np
import pandas as pd

from app.analytics import turbine_model as tm
from app.services.generate_dataset import SCADA_COLUMNS, GeneratorConfig, generate_dataset


def test_columns_and_size(small_dataset):
    s = small_dataset.scada
    assert list(s.columns) == SCADA_COLUMNS
    expected = 4 * 20 * 144
    # gaps remove rows, duplicates/unknown IDs add a few - stay within 2 %
    assert abs(len(s) - expected) / expected < 0.02


def test_full_default_config_scale():
    cfg = GeneratorConfig()
    days = (pd.Timestamp(cfg.end) - pd.Timestamp(cfg.start)).days + 1
    assert cfg.n_turbines * days * 144 >= 259_200  # >= the brief's ~259,200 records


def test_valid_statuses_and_turbines(small_dataset):
    s = small_dataset.scada
    assert set(s["operating_status"]) <= {"Running", "Idle", "Fault", "Maintenance"}
    assert set(s["turbine_id"]) - {"WTG99"} == {"WTG01", "WTG02", "WTG03", "WTG04"}
    assert len(small_dataset.turbines) == 4


def test_engineering_relationships_clean_data():
    ds = generate_dataset(GeneratorConfig(n_turbines=2, start="2026-01-01", end="2026-01-10", seed=3,
                                          inject_errors=False))
    s = ds.scada
    run = s[s["operating_status"] == "Running"]
    stopped = s[s["operating_status"].isin(["Fault", "Maintenance"])]
    # power never exceeds rated (+1 % tolerance) and follows the reference curve
    assert run["active_power_kw"].max() <= tm.RATED_POWER_KW * 1.01 + 1
    corr = np.corrcoef(run["active_power_kw"], run["theoretical_power_kw"])[0, 1]
    assert corr > 0.95
    # below cut-in the turbine is not Running; above cut-out it is stopped
    assert (s.loc[s["wind_speed_ms"] < tm.CUT_IN_MS, "operating_status"] != "Running").all()
    assert (s.loc[s["wind_speed_ms"] > tm.CUT_OUT_MS, "operating_status"] != "Running").all()
    # stopped turbines draw only auxiliary power and log downtime
    assert stopped["active_power_kw"].max() <= 0
    assert (stopped["downtime_minutes"] == 10).all()
    # generator speed = rotor speed x gearbox ratio
    ratio = (run["generator_speed_rpm"] / run["rotor_speed_rpm"]).median()
    assert abs(ratio - tm.GEAR_RATIO) < 1
    assert (s["wind_speed_ms"] >= 0).all()


def test_deterministic_seed():
    a = generate_dataset(GeneratorConfig(n_turbines=1, start="2026-02-01", end="2026-02-02", seed=11))
    b = generate_dataset(GeneratorConfig(n_turbines=1, start="2026-02-01", end="2026-02-02", seed=11))
    pd.testing.assert_frame_equal(a.scada, b.scada)


def test_injected_errors_present(small_dataset):
    s = small_dataset.scada
    assert (s["wind_speed_ms"] < 0).sum() > 0
    assert (s["active_power_kw"] > tm.RATED_POWER_KW * 1.15).sum() > 0
    assert s.duplicated(["turbine_id", "timestamp"]).sum() > 0
    assert (s["turbine_id"] == "WTG99").sum() > 0
    assert pd.to_datetime(s["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce").isna().sum() > 0
    assert len(small_dataset.scenarios) > 0
    assert len(small_dataset.service_events) > 0
