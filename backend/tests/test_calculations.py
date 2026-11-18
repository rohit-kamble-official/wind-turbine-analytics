import math

import numpy as np
import pandas as pd
import pytest

from app.analytics import availability as av
from app.analytics.downtime_analysis import downtime_by_turbine, downtime_summary
from app.analytics.energy_analysis import aggregate_energy, energy_from_power, interval_energy_kwh
from app.analytics.performance_calculations import (aggregate_deviation_pct, capacity_factor_pct,
                                                    daily_turbine_metrics, enrich_intervals,
                                                    performance_deviation_pct, summarize_period)
from app.analytics.turbine_model import reference_power_kw
from app.services.data_validator import validate_scada
from tests.conftest import make_scada


# ------------------------------------------------------------------ energy
def test_interval_energy():
    assert interval_energy_kwh(1000)[()] == pytest.approx(166.6667, rel=1e-4)
    assert math.isnan(interval_energy_kwh(np.nan)[()])  # missing power is not zero energy


def test_energy_from_power():
    assert energy_from_power(2500, 2) == 5000
    with pytest.raises(ValueError):
        energy_from_power(100, -1)


def test_aggregate_energy_daily_and_hourly():
    df = pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=288, freq="10min"),
                       "turbine_id": "WTG01", "energy_kwh": 100.0})
    d = aggregate_energy(df, "daily")
    assert d["energy_kwh"].tolist() == [14400.0, 14400.0]
    assert d["energy_mwh"].iloc[0] == pytest.approx(14.4)
    h = aggregate_energy(df, "hourly", by_turbine=False)
    assert len(h) == 48 and (h["energy_kwh"] == 600).all()
    with pytest.raises(ValueError):
        aggregate_energy(df, "weekly")


# ------------------------------------------------------------------ availability
def test_classify_intervals():
    status = pd.Series(["Running", "Idle", "Idle", "Maintenance", "Fault", "Fault", "Unknown"])
    code = pd.Series(["", "", "ENV-HW", "PM-ANN", "F-101", "F-412", ""])
    assert av.classify_intervals(status, code).tolist() == [
        "running", "idle_low_wind", "environmental_stop", "planned_maintenance", "unplanned_fault",
        "external_grid", "missing"]


MIN = {"running_minutes": 800, "idle_low_wind_minutes": 100, "environmental_stop_minutes": 40,
       "planned_maintenance_minutes": 200, "unplanned_fault_minutes": 100, "external_grid_minutes": 60,
       "missing_minutes": 140}


def test_availability_technical():
    # available 940 / eligible (940 + 100 fault + 200 planned) = 75.806 %
    assert av.availability_pct(MIN) == pytest.approx(940 / 1240 * 100)


def test_availability_contractual_excludes_planned():
    assert av.availability_pct(MIN, av.AvailabilityConfig.from_basis("contractual")) == pytest.approx(940 / 1040 * 100)


def test_availability_strict_counts_everything():
    assert av.availability_pct(MIN, av.AvailabilityConfig.from_basis("strict")) == pytest.approx(940 / 1440 * 100)


def test_availability_environmental_excluded_option():
    cfg = av.AvailabilityConfig(environmental_counts_available=False)
    assert av.availability_pct(MIN, cfg) == pytest.approx(900 / 1200 * 100)


def test_availability_zero_eligible_and_bad_basis():
    assert av.availability_pct({"missing_minutes": 1440}) is None
    with pytest.raises(ValueError):
        av.AvailabilityConfig.from_basis("nope")


# ------------------------------------------------------------------ capacity factor / deviation
def test_capacity_factor():
    # 3 MW for 24 h = 72 MWh max; 18 MWh produced = 25 %
    assert capacity_factor_pct(18000, 3000, 24) == pytest.approx(25.0)
    assert math.isnan(capacity_factor_pct(100, 3000, 0))


def test_performance_deviation_handles_zero_expected():
    dev = performance_deviation_pct([900, 0, 10, 1100], [1000, 0, 20, 1000])
    assert dev[0] == pytest.approx(-10.0)
    assert np.isnan(dev[1]) and np.isnan(dev[2])  # zero / below-threshold expected -> undefined
    assert dev[3] == pytest.approx(10.0)
    assert aggregate_deviation_pct(950, 1000) == pytest.approx(-5.0)
    assert np.isnan(aggregate_deviation_pct(10, 0))


def test_reference_curve_bounds():
    p = reference_power_kw([-1, 0, 2.5, 3, 13.5, 20, 25, 25.5, np.nan])
    assert np.isnan(p[0]) and np.isnan(p[-1])
    assert p[1] == 0 and p[2] == 0 and p[3] > 0
    assert p[4] == 3000 and p[5] == 3000 and p[6] == 3000 and p[7] == 0
    assert np.all(np.diff(reference_power_kw(np.arange(3, 13.5, 0.5))) > 0)  # monotonic below rated


# ------------------------------------------------------------------ daily metrics end-to-end
def _day_frame():
    run = make_scada(120, start="2026-03-01 00:00:00", ws=10.0, power=2000.0)       # 20 h running
    fault = make_scada(12, start="2026-03-01 20:00:00", ws=10.0, power=-3.0, status="Fault", code="F-101")
    maint = make_scada(6, start="2026-03-01 22:00:00", ws=10.0, power=-3.0, status="Maintenance", code="PM-ANN")
    # 6 intervals (1 h) missing at the end of the day
    return pd.concat([run, fault, maint], ignore_index=True)


def test_daily_metrics_known_values():
    v = validate_scada(_day_frame(), ["WTG01"]).data
    e = enrich_intervals(v[v["is_valid_record"]])
    m = daily_turbine_metrics(e, rated_power_kw=3000).iloc[0]
    assert m["running_minutes"] == 1200
    assert m["unplanned_fault_minutes"] == 120
    assert m["planned_maintenance_minutes"] == 60
    assert m["missing_minutes"] == 60
    # energy = 2000 kW x 20 h - 3 kW x 3 h aux
    assert m["energy_kwh"] == pytest.approx(40000 - 9, abs=0.01)
    # availability = 1200 / (1200 + 120 + 60)
    assert m["availability_pct"] == pytest.approx(1200 / 1380 * 100, abs=1e-3)
    # capacity factor over 23 h of valid data
    assert m["capacity_factor_pct"] == pytest.approx(39991 / (3000 * 23) * 100, abs=1e-3)
    # deviation uses the SCADA-reported theoretical power (reference curve at 10.0 m/s = 2190 kW)
    expected_power = float(reference_power_kw(10.0))
    assert m["performance_deviation_pct"] == pytest.approx((2000 - expected_power) / expected_power * 100, abs=0.05)


def test_downtime_and_summary():
    v = validate_scada(_day_frame(), ["WTG01"]).data
    m = daily_turbine_metrics(enrich_intervals(v[v["is_valid_record"]]))
    s = downtime_summary(m)
    assert s == {"total_downtime_hours": 3.0, "planned_hours": 1.0, "unplanned_hours": 2.0,
                 "fault_related_hours": 2.0, "external_hours": 0.0, "environmental_stop_hours": 0.0,
                 "missing_data_hours": 1.0}
    assert downtime_by_turbine(m).iloc[0]["total_downtime_hours"] == 3.0
    k = summarize_period(m)
    assert k["downtime_hours"] == pytest.approx(3.0)
    assert k["availability_pct"] == pytest.approx(1200 / 1380 * 100)
