import numpy as np
import pandas as pd
import pytest

from app.services.data_processor import process_scada
from app.services.data_quality_report import build_quality_report
from app.services.data_validator import SchemaValidationError, validate_scada
from tests.conftest import make_scada

KNOWN = ["WTG01", "WTG02"]


def test_missing_required_columns_raises():
    df = make_scada().drop(columns=["active_power_kw", "yaw_angle_deg"])
    with pytest.raises(SchemaValidationError) as e:
        validate_scada(df, KNOWN)
    assert set(e.value.missing) == {"active_power_kw", "yaw_angle_deg"}


def test_clean_rows_pass():
    v = validate_scada(make_scada(), KNOWN).data
    assert v["is_valid_for_analysis"].all()
    assert (v["qc_flags"] == "").all()


def test_duplicates_flagged_first_kept_nothing_dropped():
    df = make_scada(4)
    dup = df.iloc[[1]].copy()
    conflict = df.iloc[[2]].copy()
    conflict["active_power_kw"] += 100
    data = pd.concat([df, dup, conflict], ignore_index=True)
    v = validate_scada(data, KNOWN).data
    assert len(v) == len(data)  # never silently delete
    assert v["flag_duplicate"].sum() == 2
    assert v.loc[4, "flag_duplicate"] and not v.loc[1, "flag_duplicate"]
    assert v.loc[5, "flag_conflicting_duplicate"]
    assert "duplicate_exact" in v.loc[4, "qc_flags"]
    assert not v.loc[4, "is_valid_record"]


@pytest.mark.parametrize("bad", ["2026-02-30 10:00:00", "", "garbage", "2026-01-01 00:05:00", "01/01/2026 00:00"])
def test_invalid_timestamps(bad):
    df = make_scada(3)
    df.loc[1, "timestamp"] = bad
    v = validate_scada(df, KNOWN).data
    assert v.loc[1, "flag_invalid_timestamp"]
    assert not v.loc[1, "is_valid_record"]
    assert v.loc[0, "is_valid_record"]


def test_negative_wind_and_impossible_power():
    df = make_scada(4)
    df.loc[0, "wind_speed_ms"] = -2.0
    df.loc[1, "active_power_kw"] = 9000.0
    df.loc[2, "active_power_kw"] = -500.0
    df.loc[3, "active_power_kw"] = -5.0  # auxiliary consumption is normal
    v = validate_scada(df, KNOWN).data
    assert v.loc[0, "flag_negative_wind"]
    assert v.loc[1, "flag_impossible_power"] and v.loc[2, "flag_impossible_power"]
    assert not v.loc[3, "flag_impossible_power"]
    assert v["is_valid_record"].all()  # status still usable for availability
    assert v["is_valid_for_analysis"].tolist() == [False, False, False, True]


def test_unknown_turbine_and_missing_values():
    df = make_scada(3)
    df.loc[0, "turbine_id"] = "WTG77"
    df.loc[1, "active_power_kw"] = np.nan
    v = validate_scada(df, KNOWN).data
    assert v.loc[0, "flag_unknown_turbine"] and not v.loc[0, "is_valid_record"]
    assert v.loc[1, "flag_missing_value"] and v.loc[1, "is_valid_record"]
    assert not v.loc[1, "is_valid_for_analysis"]


def test_stuck_sensor_and_temperature_range():
    df = make_scada(8)
    df["wind_speed_ms"] = 7.25  # constant for 80 minutes
    df.loc[0, "gearbox_temperature_c"] = 250.0
    v = validate_scada(df, KNOWN).data
    assert v["flag_stuck_sensor"].all()
    assert v.loc[0, "flag_sensor_range"]
    assert "gearbox_temperature_c_out_of_physical_range" in v.loc[0, "qc_flags"]


def test_quality_report_and_processing(small_dataset):
    p = process_scada(small_dataset.scada, small_dataset.turbines, run_anomalies=False)
    q = p.quality
    assert q["total_rows"] == len(small_dataset.scada)
    assert q["valid_records"] + q["quarantined_rows"] == q["total_rows"]
    assert len(p.clean) + len(p.quarantine) == len(small_dataset.scada)
    assert q["missing_intervals"] > 0  # communication gaps were injected
    assert 90 < q["data_quality_score_pct"] <= 100
    assert len(q["per_turbine"]) == 4
    assert q["flag_counts"]["duplicate"] > 0 and q["flag_counts"]["invalid_timestamp"] > 0


def test_quality_report_empty_safe():
    v = validate_scada(make_scada(2).assign(turbine_id="X"), KNOWN).data
    r = build_quality_report(v, KNOWN)
    assert r["valid_records"] == 0 and r["expected_intervals"] == 0
