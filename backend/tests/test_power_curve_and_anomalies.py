import numpy as np
import pandas as pd
import pytest

from app.analytics.anomaly_detection import AnomalyConfig, detect_anomalies
from app.analytics.performance_calculations import daily_turbine_metrics, enrich_intervals
from app.analytics.power_curve import bin_power_curve
from app.analytics.turbine_model import reference_power_kw
from app.services.data_processor import process_scada
from app.services.data_validator import validate_scada
from tests.conftest import make_scada


def _enriched(df, turbines=("WTG01", "WTG02", "WTG03", "WTG04")):
    v = validate_scada(df, list(turbines)).data
    return enrich_intervals(v[v["is_valid_record"]].sort_values(["turbine_id", "timestamp"]))


# ------------------------------------------------------------------ power curve
def test_power_curve_matches_reference_for_ideal_data():
    ws = np.linspace(3, 24, 2000)
    df = pd.DataFrame({"wind_speed_ms": ws, "active_power_kw": reference_power_kw(ws),
                       "operating_status": "Running", "is_valid_for_analysis": True})
    b = bin_power_curve(df, 0.5)
    assert b["count"].sum() == 2000
    # bin-averaging a convex curve biases the lowest bins slightly upward (Jensen); <3 % and ~0 near rated
    assert b["deviation_pct"].dropna().abs().max() < 3.0
    assert b.loc[b["bin_center_ms"] >= 8, "deviation_pct"].dropna().abs().max() < 0.5
    assert (b["bin_center_ms"].diff().dropna() == 0.5).all()


def test_power_curve_excludes_non_running_and_invalid():
    df = pd.DataFrame({"wind_speed_ms": [8, 8, 8, -1], "active_power_kw": [1200, 0, 5000, 100],
                       "operating_status": ["Running", "Fault", "Running", "Running"],
                       "is_valid_for_analysis": [True, True, False, False]})
    b = bin_power_curve(df)
    assert b["count"].sum() == 1 and b["avg_power_kw"].iloc[0] == 1200


def test_power_curve_empty_and_bad_bin():
    empty = pd.DataFrame({"wind_speed_ms": [], "active_power_kw": [], "operating_status": []})
    assert bin_power_curve(empty).empty
    with pytest.raises(ValueError):
        bin_power_curve(empty, 0)


# ------------------------------------------------------------------ anomalies (unit)
NO_IF = AnomalyConfig(use_isolation_forest=False)


def test_detects_power_drop_with_explanation():
    normal = make_scada(36, ws=10.0)
    p = reference_power_kw(10.0 + np.arange(36) * 0.01)
    p[10:18] *= 0.4  # 80 min at 40 % of expected
    normal["active_power_kw"] = p
    a = detect_anomalies(_enriched(normal), None, NO_IF)
    drops = a[a["anomaly_type"] == "Unexpected Power Drop"]
    assert len(drops) == 1
    r = drops.iloc[0]
    assert r["severity"] == "High" and r["measured_value"] == pytest.approx(40, abs=2)
    assert r["duration_minutes"] >= 60
    assert r["explanation"] and r["recommended_investigation"] and r["expected_range"]
    assert r["status"] == "Open"


def test_short_dip_is_not_an_anomaly():
    df = make_scada(30, ws=10.0)
    df.loc[12, "active_power_kw"] *= 0.3  # one interval only
    a = detect_anomalies(_enriched(df), None, NO_IF)
    assert (a["anomaly_type"] == "Unexpected Power Drop").sum() == 0


def test_detects_high_gearbox_temperature():
    df = make_scada(12)
    df.loc[5:7, "gearbox_temperature_c"] = [85.0, 93.0, 88.0]
    a = detect_anomalies(_enriched(df), None, NO_IF)
    t = a[a["anomaly_type"] == "High Temperature"]
    assert len(t) == 1 and t.iloc[0]["severity"] == "High" and t.iloc[0]["measured_value"] == 93.0


def test_sensor_error_temperature_is_not_an_alarm():
    df = make_scada(12)
    df.loc[5, "gearbox_temperature_c"] = 250.0  # physically impossible -> data quality, not an alarm
    a = detect_anomalies(_enriched(df), None, NO_IF)
    assert (a["anomaly_type"] == "High Temperature").sum() == 0


def test_detects_rotor_speed_step():
    frames = []
    for tid in ("WTG01", "WTG02"):
        d = make_scada(60, turbine=tid)
        d["rotor_speed_rpm"] = 12.0 + np.random.default_rng(1).normal(0, 0.1, 60)
        frames.append(d)
    frames[0].loc[30, "rotor_speed_rpm"] = 5.5
    a = detect_anomalies(_enriched(pd.concat(frames, ignore_index=True)), None, NO_IF)
    steps = a[a["anomaly_type"] == "Sudden Rotor Speed Change"]
    assert len(steps) == 1 and steps.iloc[0]["turbine_id"] == "WTG01"


def test_fleet_relative_temperature():
    frames = []
    for tid in ("WTG01", "WTG02", "WTG03", "WTG04"):
        d = make_scada(48, turbine=tid)
        d["gearbox_temperature_c"] = 60 + np.random.default_rng(hash(tid) % 100).normal(0, 0.5, 48)
        frames.append(d)
    frames[2].loc[20:26, "gearbox_temperature_c"] += 22  # 22 degC above the fleet, below the 80 degC limit
    a = detect_anomalies(_enriched(pd.concat(frames, ignore_index=True)), None, NO_IF)
    fr = a[a["anomaly_type"] == "Abnormal Temperature (fleet-relative)"]
    assert len(fr) == 1 and fr.iloc[0]["turbine_id"] == "WTG03" and fr.iloc[0]["severity"] == "High"


def test_anomaly_ids_are_deterministic():
    df = make_scada(12)
    df.loc[5:7, "gearbox_temperature_c"] = 95.0
    a1 = detect_anomalies(_enriched(df), None, NO_IF)
    a2 = detect_anomalies(_enriched(df), None, NO_IF)
    assert a1["anomaly_id"].tolist() == a2["anomaly_id"].tolist()
    assert a1["anomaly_id"].is_unique


# ------------------------------------------------------------------ anomalies vs injected ground truth
def test_recall_on_injected_scenarios(small_dataset):
    p = process_scada(small_dataset.scada, small_dataset.turbines)
    a, sc = p.anomalies, small_dataset.scenarios
    drops = sc[sc["scenario_type"] == "power_drop"]
    assert len(drops) > 0

    def found(row, types):
        hits = a[(a["turbine_id"] == row.turbine_id) & a["anomaly_type"].isin(types)
                 & (a["timestamp"] <= row.end_time + pd.Timedelta(minutes=20))
                 & (a["end_timestamp"] >= row.start_time - pd.Timedelta(minutes=20))]
        return len(hits) > 0

    recall = np.mean([found(r, ["Unexpected Power Drop", "Unusual Wind-Power Relationship"])
                      for r in drops.itertuples()])
    assert recall >= 0.6, f"power-drop recall {recall:.0%}"
    # the scripted WTG03 gearbox ramp (10 May) must be flagged
    gx = sc[(sc["scenario_type"] == "gearbox_overtemperature") & (sc["turbine_id"] == "WTG03")]
    assert len(gx) == 1 and found(gx.iloc[0], ["High Temperature", "Abnormal Temperature (fleet-relative)"])
    # stuck anemometer scenarios become sensor irregularities
    assert (a["anomaly_type"] == "Sensor Irregularity").sum() >= 1
