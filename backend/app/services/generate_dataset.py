"""Synthetic wind-farm SCADA generator.

ALL DATA PRODUCED HERE IS SIMULATED. It is not real operational data from any
turbine manufacturer or operator, and must not be presented as such.

Engineering logic (summary - full detail in docs/engineering_assumptions.md):
* Farm wind speed: two superposed AR(1) processes (synoptic + turbulence) mapped
  to a Weibull marginal (k=2.1, seasonal scale 7.4-9.8 m/s) with diurnal
  modulation and three storm events that trigger high-wind shutdowns.
* Each turbine sees the farm wind times a site factor (wake/terrain, 0.95-1.04)
  plus local turbulence.
* Operating state machine: Idle below cut-in, Idle (ENV-HW) above cut-out with
  restart hysteresis at 22 m/s, Fault and Maintenance from generated service events.
* Active power follows the reference power curve with turbine-specific
  efficiency, measurement noise, auxiliary consumption when stopped (small
  negative kW) and injected under-performance scenarios.
* Rotor/generator speed, pitch, temperatures (first-order thermal lag) are
  derived from wind and load, not drawn independently.
* Data-quality problems (gaps, NaNs, negative wind, stuck anemometer, power
  spikes, temperature sensor faults, duplicates, bad timestamps, unknown IDs)
  are injected so the validation pipeline has something real to find.
* A ground-truth `scenario_log.csv` records every injected scenario.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import lfilter, lfilter_zi
from scipy.stats import norm

from app.analytics import turbine_model as tm

STATUS_RUNNING, STATUS_IDLE, STATUS_FAULT, STATUS_MAINT = "Running", "Idle", "Fault", "Maintenance"
STATUS_NAMES = np.array([STATUS_RUNNING, STATUS_IDLE, STATUS_FAULT, STATUS_MAINT])

ENV_HIGH_WIND = "ENV-HW"
# code: (description, probability weight, responsibility)
FAULT_CODES: dict[str, tuple[str, float, str]] = {
    "F-101": ("Pitch system fault", 0.20, "turbine"),
    "F-205": ("Generator over-temperature", 0.10, "turbine"),
    "F-310": ("Converter trip", 0.18, "turbine"),
    "F-412": ("Grid disturbance (external)", 0.12, "external"),
    "F-520": ("Yaw system fault", 0.12, "turbine"),
    "F-601": ("Gearbox oil temperature high", 0.10, "turbine"),
    "F-715": ("Hydraulic pressure low", 0.10, "turbine"),
    "F-830": ("Controller communication reset", 0.08, "turbine"),
}
PLANNED_CODES = {
    "PM-ANN": "Scheduled annual service",
    "PM-GBX": "Scheduled gearbox inspection",
    "PM-BLD": "Scheduled blade inspection",
}
EXTERNAL_CODES = {c for c, (_, _, r) in FAULT_CODES.items() if r == "external"}

SCADA_COLUMNS = [
    "timestamp", "turbine_id", "wind_speed_ms", "ambient_temperature_c", "rotor_speed_rpm",
    "generator_speed_rpm", "active_power_kw", "theoretical_power_kw", "reactive_power_kvar",
    "nacelle_temperature_c", "gearbox_temperature_c", "generator_temperature_c",
    "pitch_angle_deg", "yaw_angle_deg", "operating_status", "fault_code", "downtime_minutes",
]


@dataclass
class GeneratorConfig:
    n_turbines: int = 10
    start: str = "2026-01-01"
    end: str = "2026-06-30"  # inclusive
    seed: int = 42
    inject_errors: bool = True


@dataclass
class GeneratedDataset:
    scada: pd.DataFrame
    turbines: pd.DataFrame
    service_events: pd.DataFrame
    scenarios: pd.DataFrame


def _ar1(n: int, phi: float, rng: np.random.Generator) -> np.ndarray:
    e = rng.standard_normal(n) * np.sqrt(1 - phi**2)
    zi = np.array([phi * rng.standard_normal()])
    out, _ = lfilter([1.0], [1.0, -phi], e, zi=zi)
    return out


def _ewma(x: np.ndarray, alpha: float) -> np.ndarray:
    b, a = [alpha], [1.0, -(1.0 - alpha)]
    out, _ = lfilter(b, a, x, zi=lfilter_zi(b, a) * x[0])
    return out


class _Scenarios:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, turbine: str, kind: str, start, end, description: str) -> None:
        self.rows.append({
            "scenario_id": f"SC{len(self.rows) + 1:04d}", "turbine_id": turbine, "scenario_type": kind,
            "start_time": pd.Timestamp(start), "end_time": pd.Timestamp(end), "description": description,
        })


def _farm_weather(ts: pd.DatetimeIndex, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(ts)
    doy = ts.day_of_year.to_numpy()
    hour = (ts.hour + ts.minute / 60).to_numpy()
    z = 0.92 * _ar1(n, 0.995, rng) + 0.39 * _ar1(n, 0.85, rng)
    z = (z - z.mean()) / z.std()
    u = np.clip(norm.cdf(z), 1e-9, 1 - 1e-9)
    scale = (8.0 + 1.3 * np.cos(2 * np.pi * (doy - 15) / 365.25)) * (1 + 0.05 * np.sin(2 * np.pi * (hour - 10) / 24))
    ws = scale * (-np.log(1 - u)) ** (1 / 2.1)
    # Storm fronts -> high-wind shutdowns (only if inside the simulated window)
    t_hours = (ts - ts[0]).total_seconds().to_numpy() / 3600
    for storm in ("2026-01-22 14:00", "2026-02-16 03:00", "2026-03-09 20:00"):
        st = pd.Timestamp(storm)
        if ts[0] <= st <= ts[-1]:
            c = (st - ts[0]).total_seconds() / 3600
            ws = ws + 14.0 * np.exp(-0.5 * ((t_hours - c) / 5.0) ** 2)
    ambient = (9.5 - 7.5 * np.cos(2 * np.pi * (doy - 20) / 365.25) + 3.5 * np.sin(2 * np.pi * (hour - 9) / 24)
               + 1.5 * _ar1(n, 0.99, rng))
    direction = (250 + np.cumsum(rng.normal(0, 1.5, n))) % 360
    return ws, ambient, direction


def _place_events(n: int, occupied: np.ndarray, count: int, dur_fn, rng, start_fn=None) -> list[tuple[int, int]]:
    events = []
    attempts = 0
    while len(events) < count and attempts < count * 50:
        attempts += 1
        dur = int(dur_fn())
        start = int(start_fn()) if start_fn else int(rng.integers(0, max(1, n - dur)))
        end = min(n, start + dur)
        if end <= start or occupied[max(0, start - 6):min(n, end + 6)].any():
            continue
        occupied[start:end] = True
        events.append((start, end))
    return events


def _generate_turbine(tid: str, idx: int, ts: pd.DatetimeIndex, farm_ws, ambient, direction, rng,
                      scen: _Scenarios, events_out: list[dict]) -> pd.DataFrame:
    n = len(ts)
    rated = tm.RATED_POWER_KW
    site_factor = rng.uniform(0.95, 1.04)
    ws = np.clip(farm_ws * site_factor + 0.4 * _ar1(n, 0.9, rng), 0, None)

    status = np.zeros(n, dtype=np.int8)
    code = np.full(n, "", dtype=object)

    # Weather-driven states with hysteresis for high wind
    stopped_hw = False
    for i in range(n):
        if stopped_hw:
            if ws[i] < tm.RESTART_WIND_MS:
                stopped_hw = False
        elif ws[i] > tm.CUT_OUT_MS:
            stopped_hw = True
        if stopped_hw:
            status[i], code[i] = 1, ENV_HIGH_WIND
        elif ws[i] < tm.CUT_IN_MS:
            status[i] = 1

    occupied = np.zeros(n, dtype=bool)
    day_starts = np.flatnonzero((ts.hour == 7) & (ts.minute == 0))

    def add_event(start, end, st_code, planned, event_code, desc):
        status[start:end] = st_code
        code[start:end] = event_code
        events_out.append({
            "turbine_id": tid, "start_time": ts[start], "end_time": ts[end - 1] + pd.Timedelta(minutes=10),
            "duration_hours": round((end - start) * 10 / 60, 2),
            "event_type": "Planned Maintenance" if planned else (
                "External Grid Event" if event_code in EXTERNAL_CODES else "Unplanned Fault"),
            "is_planned": planned, "fault_code": event_code, "description": desc,
        })

    # Scripted scenario: WTG03 gearbox temperature ramp in May followed by an F-601 trip
    scripted: list[tuple[int, int, str]] = []
    if tid == "WTG03":
        ramp_start = ts.searchsorted(pd.Timestamp("2026-05-10 02:00"))
        if 0 < ramp_start < n - 200:
            trip = ramp_start + 108  # 18 h ramp
            occupied[ramp_start:trip + 60] = True
            scripted.append((trip, trip + 60, "F-601"))

    # Planned maintenance (daytime starts)
    n_pm = 2 if tid == "WTG05" else int(rng.integers(1, 3))
    for k, (s, e) in enumerate(_place_events(
            n, occupied, n_pm, lambda: rng.integers(48, 180), rng,
            start_fn=lambda: rng.choice(day_starts) + rng.integers(0, 12) if len(day_starts) else 0)):
        pm_code = "PM-GBX" if (tid == "WTG05" and k == 0) else str(rng.choice(["PM-ANN", "PM-BLD"]))
        if pm_code == "PM-GBX":
            e = min(n, s + 432)  # 3-day gearbox inspection
            occupied[s:e] = True
        add_event(s, e, 3, True, pm_code, PLANNED_CODES[pm_code])

    # Unplanned faults (WTG08 is simulated as the least reliable unit)
    codes = list(FAULT_CODES)
    weights = np.array([FAULT_CODES[c][1] for c in codes])
    weights = weights / weights.sum()
    n_faults = int(rng.poisson(11 if tid == "WTG08" else 5))
    for s, e in _place_events(n, occupied, n_faults,
                              lambda: max(3, min(432, round(rng.lognormal(np.log(24), 0.9)))), rng):
        fc = str(rng.choice(codes, p=weights))
        add_event(s, e, 2, False, fc, FAULT_CODES[fc][0])
    for s, e, fc in scripted:
        add_event(s, e, 2, False, fc, FAULT_CODES[fc][0])

    running = status == 0
    expected = np.nan_to_num(tm.reference_power_kw(ws))

    # Turbine efficiency and injected under-performance
    perf = np.full(n, rng.uniform(0.985, 1.01))
    if tid == "WTG07":
        deg_start = ts.searchsorted(pd.Timestamp("2026-04-01"))
        if deg_start < n:
            ramp = np.clip((np.arange(n) - deg_start) / (7 * 144), 0, 1)
            perf = perf - 0.07 * ramp
            scen.add(tid, "sustained_underperformance", ts[deg_start], ts[-1],
                     "Simulated ~7% power-curve shortfall from April (e.g. pitch offset / blade condition)")
    run_idx = np.flatnonzero(running & (expected > 300))
    for _ in range(int(rng.integers(2, 5))):
        if len(run_idx) == 0:
            break
        s = int(rng.choice(run_idx))
        e = min(n, s + int(rng.integers(6, 48)))
        f = rng.uniform(0.35, 0.65)
        perf[s:e] *= f
        scen.add(tid, "power_drop", ts[s], ts[e - 1], f"Simulated unexpected power drop to {f:.0%} of expected")

    p_run = expected * perf * (1 + rng.normal(0, 0.035, n)) + rng.normal(0, 12, n)
    p_run = np.clip(p_run, 0, rated * 1.01)
    p_aux = np.clip(rng.normal(-4, 1.5, n), -12, 0)  # auxiliary consumption when not generating
    active = np.where(running, p_run, p_aux)

    idle_low = (status == 1) & (code == "")
    rotor = np.where(running, tm.expected_rotor_rpm(ws) + rng.normal(0, 0.15, n),
                     np.where(idle_low, np.clip(ws * 0.5 + rng.normal(0, 0.2, n), 0, 3),
                              np.abs(rng.normal(0, 0.1, n))))
    run_positions = np.flatnonzero(running)
    for _ in range(int(rng.integers(0, 2))):
        if len(run_positions):
            s = int(rng.choice(run_positions))
            rotor[s] = max(0.0, rotor[s] - rng.uniform(5, 7))
            scen.add(tid, "rotor_speed_step", ts[s], ts[s], "Simulated sudden rotor speed change")
    generator = np.clip(rotor * tm.GEAR_RATIO + rng.normal(0, 4, n), 0, None)
    pitch = np.where(running, np.clip(tm.expected_pitch_deg(ws) + rng.normal(0, 0.3, n), -1, 30),
                     np.where(idle_low, 70 + rng.normal(0, 2, n), 87 + rng.normal(0, 0.8, n)))
    yaw = (direction + rng.normal(0, 4, n)) % 360
    reactive = np.where(running, 0.05 * active + rng.normal(0, 25, n), rng.normal(0, 3, n))

    load_f = _ewma(np.clip(active / rated, 0, 1), 0.08)
    run_f = _ewma(running.astype(float), 0.05)
    nacelle = ambient + 6 + 12 * load_f + rng.normal(0, 0.7, n)
    gearbox = ambient + 8 + 20 * run_f + 32 * load_f + rng.normal(0, 0.9, n)
    gen_temp = ambient + 10 + 22 * run_f + 45 * load_f + rng.normal(0, 1.1, n)

    def temp_event(arr, start_str, hours, delta, kind, desc):
        s = ts.searchsorted(pd.Timestamp(start_str))
        if s >= n - 1:
            return
        L = min(n - s, hours * 6)
        arr[s:s + L] += delta * np.linspace(0, 1, L) ** 1.5
        scen.add(tid, kind, ts[s], ts[s + L - 1], desc)

    if tid == "WTG03":
        drift_start = ts.searchsorted(pd.Timestamp("2026-03-01"))
        days_since = np.clip((np.arange(n) - drift_start) / 144, 0, None)
        gearbox += 0.05 * days_since
        if drift_start < n:
            scen.add(tid, "gearbox_temperature_drift", ts[drift_start], ts[-1],
                     "Simulated slow gearbox temperature drift (+0.05 degC/day)")
        temp_event(gearbox, "2026-05-10 02:00", 18, 26, "gearbox_overtemperature",
                   "Simulated gearbox temperature ramp preceding an F-601 trip")
    if tid == "WTG06":
        temp_event(gen_temp, "2026-02-11 09:00", 8, 24, "generator_overtemperature",
                   "Simulated generator temperature excursion")
    if tid == "WTG09":
        temp_event(gearbox, "2026-06-12 06:00", 12, 19, "gearbox_overtemperature",
                   "Simulated gearbox temperature excursion")

    return pd.DataFrame({
        "timestamp": ts, "turbine_id": tid, "wind_speed_ms": ws, "ambient_temperature_c": ambient,
        "rotor_speed_rpm": rotor, "generator_speed_rpm": generator, "active_power_kw": active,
        "reactive_power_kvar": reactive, "nacelle_temperature_c": nacelle, "gearbox_temperature_c": gearbox,
        "generator_temperature_c": gen_temp, "pitch_angle_deg": pitch, "yaw_angle_deg": yaw,
        "operating_status": STATUS_NAMES[status], "fault_code": code,
        "downtime_minutes": np.where(status >= 2, 10, 0),
    })


def _inject_data_errors(df: pd.DataFrame, rng: np.random.Generator, scen: _Scenarios) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    turbines = df["turbine_id"].unique()

    # 1. Communication outages -> missing readings (rows removed)
    drop = np.zeros(n, dtype=bool)
    for _ in range(4):
        tid = rng.choice(turbines)
        pos = np.flatnonzero(df["turbine_id"].to_numpy() == tid)
        L = int(rng.integers(6, 72))
        s = int(rng.integers(0, len(pos) - L))
        drop[pos[s:s + L]] = True
        scen.add(tid, "communication_outage", df["timestamp"].iloc[pos[s]], df["timestamp"].iloc[pos[s + L - 1]],
                 f"Simulated SCADA communication gap ({L} missing 10-min readings)")

    # 2. Stuck anemometer (constant reading for 2-6 h)
    for _ in range(6):
        tid = rng.choice(turbines)
        pos = np.flatnonzero(df["turbine_id"].to_numpy() == tid)
        L = int(rng.integers(12, 36))
        s = int(rng.integers(0, len(pos) - L))
        val = max(4.0, float(df["wind_speed_ms"].iloc[pos[s]]))
        df.iloc[pos[s:s + L], df.columns.get_loc("wind_speed_ms")] = val
        scen.add(tid, "stuck_anemometer", df["timestamp"].iloc[pos[s]], df["timestamp"].iloc[pos[s + L - 1]],
                 f"Simulated stuck wind sensor at {val:.2f} m/s")

    def pick(k):
        return rng.choice(np.flatnonzero(~drop), size=k, replace=False)

    # 3. Isolated sensor errors
    df.loc[df.index[pick(40)], "wind_speed_ms"] = -rng.uniform(0.5, 5, 40)
    df.loc[df.index[pick(30)], "active_power_kw"] = tm.RATED_POWER_KW * rng.uniform(1.6, 2.5, 30)
    df.loc[df.index[pick(20)], "gearbox_temperature_c"] = rng.choice([-40.0, 250.0], 20)
    df.loc[df.index[pick(8)], "generator_temperature_c"] = 300.0
    # 4. Missing values in individual fields (~0.2 %)
    for col in ("wind_speed_ms", "active_power_kw", "gearbox_temperature_c", "ambient_temperature_c",
                "rotor_speed_rpm"):
        k = int(n * 0.002)
        df.loc[df.index[pick(k)], col] = np.nan

    df["theoretical_power_kw"] = tm.reference_power_kw(df["wind_speed_ms"].to_numpy())
    df = df.loc[~drop].reset_index(drop=True)

    # 5. Timestamp as text, then corrupt a few
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    bad_ts = ["2026-02-30 10:00:00", "", "not_a_timestamp", "2026-13-01 00:00:00", "2026-04-31 12:10:00",
              "31/01/2026 08:00", "2026-03-15 25:00:00", "NaT"]
    bad_rows = rng.choice(len(df), size=len(bad_ts), replace=False)
    df.loc[bad_rows, "timestamp"] = bad_ts

    # 6. Duplicates (exact and conflicting) and unknown turbine ids
    dup = df.iloc[rng.choice(len(df), 60, replace=False)].copy()
    conflict_idx = dup.index[:10]
    dup.loc[conflict_idx, "active_power_kw"] = dup.loc[conflict_idx, "active_power_kw"] + 50
    unknown = df.iloc[rng.choice(len(df), 5, replace=False)].copy()
    unknown["turbine_id"] = "WTG99"
    df = pd.concat([df, dup, unknown], ignore_index=True)
    return df


def generate_dataset(cfg: GeneratorConfig | None = None) -> GeneratedDataset:
    cfg = cfg or GeneratorConfig()
    rng = np.random.default_rng(cfg.seed)
    ts = pd.date_range(cfg.start, pd.Timestamp(cfg.end) + pd.Timedelta(days=1), freq="10min", inclusive="left")
    farm_ws, ambient, direction = _farm_weather(ts, rng)
    scen = _Scenarios()
    events: list[dict] = []
    frames, turbine_rows = [], []
    for i in range(cfg.n_turbines):
        tid = f"WTG{i + 1:02d}"
        frames.append(_generate_turbine(tid, i, ts, farm_ws, ambient, direction, rng, scen, events))
        turbine_rows.append({
            "turbine_id": tid, "turbine_name": f"Turbine {i + 1:02d}", "site_name": "Simulated Wind Farm (Demo)",
            "model": tm.DEFAULT_SPEC.model, "rated_power_kw": tm.RATED_POWER_KW,
            "rotor_diameter_m": tm.ROTOR_DIAMETER_M, "hub_height_m": tm.HUB_HEIGHT_M,
            "cut_in_ms": tm.CUT_IN_MS, "rated_wind_ms": tm.RATED_WIND_MS, "cut_out_ms": tm.CUT_OUT_MS,
            "commissioning_date": str((pd.Timestamp("2016-03-01") + pd.Timedelta(days=int(rng.integers(0, 900)))).date()),
            "layout_x_m": float((i % 5) * 450), "layout_y_m": float((i // 5) * 600), "data_source": "SIMULATED",
        })
    scada = pd.concat(frames, ignore_index=True).sort_values(["timestamp", "turbine_id"], kind="stable")
    scada = scada.reset_index(drop=True)
    for _, ev in pd.DataFrame(events).iterrows():
        kind = "planned_maintenance" if ev["is_planned"] else "fault"
        scen.add(ev["turbine_id"], kind, ev["start_time"], ev["end_time"], f"{ev['fault_code']}: {ev['description']}")
    if cfg.inject_errors:
        scada = _inject_data_errors(scada, rng, scen)
    else:
        scada["theoretical_power_kw"] = tm.reference_power_kw(scada["wind_speed_ms"].to_numpy())
        scada["timestamp"] = scada["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    rounding = {"wind_speed_ms": 2, "ambient_temperature_c": 1, "rotor_speed_rpm": 2, "generator_speed_rpm": 1,
                "active_power_kw": 1, "theoretical_power_kw": 1, "reactive_power_kvar": 1,
                "nacelle_temperature_c": 1, "gearbox_temperature_c": 1, "generator_temperature_c": 1,
                "pitch_angle_deg": 2, "yaw_angle_deg": 1}
    scada = scada.round(rounding)[SCADA_COLUMNS]

    service = pd.DataFrame(events).sort_values("start_time").reset_index(drop=True)
    service.insert(0, "event_id", [f"SE{i + 1:04d}" for i in range(len(service))])
    return GeneratedDataset(scada=scada, turbines=pd.DataFrame(turbine_rows), service_events=service,
                            scenarios=pd.DataFrame(scen.rows))


def write_dataset(ds: GeneratedDataset, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "scada": out_dir / "scada_data.csv",
        "turbines": out_dir / "turbines.csv",
        "service_events": out_dir / "service_events.csv",
        "scenarios": out_dir / "scenario_log.csv",
    }
    ds.scada.to_csv(paths["scada"], index=False)
    ds.turbines.to_csv(paths["turbines"], index=False)
    ds.service_events.to_csv(paths["service_events"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    ds.scenarios.to_csv(paths["scenarios"], index=False, date_format="%Y-%m-%d %H:%M:%S")
    return paths


def main() -> None:
    from app.core.config import settings

    ap = argparse.ArgumentParser(description="Generate SIMULATED wind-farm SCADA data")
    ap.add_argument("--turbines", type=int, default=10)
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--seed", type=int, default=settings.random_seed)
    ap.add_argument("--no-errors", action="store_true", help="Do not inject data-quality problems")
    ap.add_argument("--out", type=Path, default=settings.generated_dir)
    a = ap.parse_args()
    ds = generate_dataset(GeneratorConfig(a.turbines, a.start, a.end, a.seed, not a.no_errors))
    paths = write_dataset(ds, a.out)
    print(f"Generated {len(ds.scada):,} SCADA rows for {a.turbines} turbines (SIMULATED DATA)")
    print(f"{len(ds.service_events)} service events, {len(ds.scenarios)} logged scenarios")
    for k, p in paths.items():
        print(f"  {k:15s} -> {p}")


if __name__ == "__main__":
    main()
