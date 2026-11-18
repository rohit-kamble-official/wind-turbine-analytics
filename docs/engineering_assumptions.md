# Engineering assumptions

> **All data in this project is simulated.** The turbine model, power curve, fault codes and
> operating scenarios are generic and invented for a portfolio project. They are not taken from,
> and must not be presented as, any manufacturer's or operator's real data or products.

## 1. Reference turbine (generic 3.0 MW class)

| Parameter | Value | Note |
|---|---|---|
| Rated power | 3 000 kW | |
| Rotor diameter / hub height | 112 m / 94 m | |
| Cut-in wind speed | 3.0 m/s | below → `Idle` |
| Rated wind speed | ≈13 m/s | curve reaches 3 000 kW at 13.5 m/s |
| Cut-out wind speed | 25 m/s | above → `Idle` with code `ENV-HW` |
| Restart after high-wind stop | < 22 m/s | hysteresis prevents on/off cycling |
| Rotor speed | 6.5 → 14.0 rpm | linear from cut-in to 10 m/s, constant above |
| Gearbox ratio | 1 : 107 | generator ≈ 700–1 500 rpm |
| Pitch | ≈0.5° below 11.5 m/s, +1.6°/(m/s) above | 70° idling, 87° feathered when stopped |
| Air density | 1.225 kg/m³ | **no density correction** applied |

Reference power curve (kW, linear interpolation between 0.5 m/s points):

| m/s | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | ≥13.5–25 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| kW | 25 | 130 | 295 | 525 | 835 | 1 225 | 1 690 | 2 190 | 2 640 | 2 920 | 2 995 | 3 000 |

The shape is consistent with a pitch-regulated, variable-speed machine of this size
(≈0.42 overall power coefficient in the partial-load region). Source: `backend/app/analytics/turbine_model.py`.

## 2. Wind and weather model

* **Farm wind speed:** two AR(1) processes (synoptic φ=0.995, turbulence φ=0.85 per 10 min),
  mapped through the normal CDF to a **Weibull** marginal with k = 2.1 and a seasonal scale
  parameter of 6.7–9.3 m/s (windier in January), plus ±5 % diurnal modulation.
* **Storms:** three Gaussian wind bumps (+14 m/s peak, σ=5 h) on 22 Jan, 16 Feb and 9 Mar push
  wind above cut-out → high-wind shutdowns.
* **Per turbine:** farm wind × site factor (0.95–1.04, representing wake/terrain) + local AR(1) turbulence.
* **Ambient temperature:** seasonal (≈2 °C Jan → ≈17 °C Jun) + diurnal ±3.5 °C + AR noise.

## 3. Operating states

| State | Rule | Power | Downtime |
|---|---|---|---|
| Running | wind between cut-in and cut-out, no event | curve × efficiency × noise | 0 |
| Idle (low wind) | wind < 3 m/s | −12…0 kW (auxiliary consumption) | 0 |
| Idle `ENV-HW` | wind > 25 m/s until < 22 m/s | auxiliary | 0 (environmental) |
| Maintenance `PM-*` | 1–2 planned events/turbine, 8–30 h, start 07:00–09:00; WTG05 has a 3-day gearbox inspection | auxiliary | 10 min/record |
| Fault `F-xxx` | Poisson ≈5 events/turbine (WTG08 ≈11), lognormal duration (median 24 intervals ≈ 4 h, max 72 h) | auxiliary | 10 min/record |

Fault codes (generic, invented): F-101 pitch system, F-205 generator over-temperature, F-310 converter
trip, **F-412 grid disturbance (external)**, F-520 yaw system, F-601 gearbox oil temperature,
F-715 hydraulic pressure, F-830 controller communication reset.

## 4. Derived signals

* `theoretical_power_kw` = reference curve at the **recorded** wind speed (so a faulty anemometer
  produces a wrong expected value – as in real SCADA).
* Temperatures use a first-order thermal lag (EWMA) of load and running state:
  gearbox ≈ ambient + 8 + 20·running + 32·load; generator ≈ ambient + 10 + 22·running + 45·load;
  nacelle ≈ ambient + 6 + 12·load.
* Reactive power ≈ 5 % of active power ± noise while running.

## 5. Injected scenarios (ground truth in `data/generated/scenario_log.csv`)

| Scenario | Where |
|---|---|
| Sustained ~7 % under-performance from April | WTG07 |
| Unexpected power drops to 35–65 % for 1–8 h | 2–4 per turbine |
| Slow gearbox temperature drift (+0.05 °C/day from March) and an 18 h ramp before an F-601 trip on 10 May | WTG03 |
| Generator temperature excursion (+24 °C) | WTG06, 11 Feb |
| Gearbox temperature excursion (+19 °C) | WTG09, 12 Jun |
| Sudden rotor speed steps | random |
| Low reliability (many faults) | WTG08 |
| Data problems: 4 comms gaps, 6 stuck anemometers, 40 negative wind speeds, 30 power spikes, 28 temperature sensor errors, ~0.2 % NaNs per field, 60 duplicates (10 conflicting), 8 bad timestamps, 5 unknown turbine IDs | fleet |

## 6. KPI definitions

| KPI | Formula | Choices made |
|---|---|---|
| Energy | Σ P̄₁₀ₘᵢₙ × 10/60 h | Invalid/missing power is **not** gap-filled (conservative measured figure) |
| Availability (technical, default) | available ÷ eligible minutes × 100 | available = running + idle low wind + high-wind stops; eligible = available + faults + planned maintenance; grid events & data gaps excluded |
| Availability (contractual) | same | planned maintenance also excluded from eligible time |
| Availability (strict) | same | grid events and data gaps count against availability |
| Capacity factor | energy ÷ (rated power × eligible hours) × 100 | eligible hours = hours with valid power data |
| Performance deviation | (actual − expected) ÷ expected × 100 | only Running records with expected ≥ 50 kW; aggregated **energy-weighted** (ratio of sums) |
| Downtime | planned + unplanned + external | high-wind stops and data gaps reported separately, not as downtime |

Range KPIs are always computed as **ratios of summed components**, never by averaging daily
percentages (which would weight a calm day the same as a stormy one).

## 7. Known simplifications

* Nacelle anemometer, no nacelle transfer function, no air-density or turbulence normalisation
  (a real IEC 61400-12-1 power performance test would include these).
* Wake effects are a static factor per turbine; no wind-direction dependency.
* Thermal model is first-order; no cooling-system dynamics.
* Curtailment/derating is not modelled explicitly; injected power drops stand in for it.
