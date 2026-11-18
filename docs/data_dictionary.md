# Data dictionary

All datasets are **simulated**. Units are SI unless stated.

## 1. `scada_data.csv` (raw, 10-minute averages) → table `scada_readings`

| Column | Type | Unit | Description |
|---|---|---|---|
| timestamp | text → datetime | local time | Start of the 10-min averaging interval, `YYYY-MM-DD HH:MM:SS` |
| turbine_id | text | – | `WTG01` … `WTG10` |
| wind_speed_ms | float | m/s | Nacelle anemometer mean wind speed |
| ambient_temperature_c | float | °C | Outside air temperature |
| rotor_speed_rpm | float | rpm | Main rotor speed |
| generator_speed_rpm | float | rpm | Generator shaft speed (≈ rotor × 107) |
| active_power_kw | float | kW | Mean exported active power (small negatives = auxiliary consumption) |
| theoretical_power_kw | float | kW | Reference power curve at the recorded wind speed |
| reactive_power_kvar | float | kvar | Mean reactive power |
| nacelle_temperature_c | float | °C | Nacelle air temperature |
| gearbox_temperature_c | float | °C | Gearbox oil/bearing temperature |
| generator_temperature_c | float | °C | Generator winding temperature |
| pitch_angle_deg | float | ° | Mean blade pitch angle |
| yaw_angle_deg | float | ° | Nacelle direction (0–360) |
| operating_status | text | – | `Running`, `Idle`, `Fault`, `Maintenance` |
| fault_code | text | – | `F-xxx` fault, `PM-xxx` planned maintenance, `ENV-HW` high-wind stop, empty otherwise |
| downtime_minutes | int | min | 10 when status is Fault or Maintenance, else 0 |

Columns added by the pipeline (stored in `scada_readings` and `scada_clean.csv`):

| Column | Description |
|---|---|
| interval_category | `running`, `idle_low_wind`, `environmental_stop`, `planned_maintenance`, `unplanned_fault`, `external_grid` |
| is_valid_for_analysis | Wind and power plausible → used for energy, power curve and deviation |
| qc_flags | Semicolon-separated validation reasons (empty = clean) |

`scada_clean.csv` additionally carries every `flag_*` boolean, `energy_kwh`, `expected_energy_kwh`,
`performance_deviation_pct` and cleaned temperature columns.

## 2. `turbines.csv` → table `turbines`

turbine_id (PK), turbine_name, site_name, model, rated_power_kw, rotor_diameter_m, hub_height_m,
cut_in_ms, rated_wind_ms, cut_out_ms, commissioning_date, layout_x_m, layout_y_m, data_source (`SIMULATED`).

## 3. `service_events.csv` → table `service_events`

| Column | Description |
|---|---|
| event_id | `SE0001` … (PK) |
| turbine_id | FK → turbines |
| start_time / end_time | Event window |
| duration_hours | end − start |
| event_type | `Planned Maintenance`, `Unplanned Fault`, `External Grid Event` |
| is_planned | boolean |
| fault_code / description | Code and plain-text description |

## 4. `performance_metrics` (daily per turbine)

| Column | Unit | Description |
|---|---|---|
| turbine_id, date | – | Unique together |
| energy_kwh | kWh | Σ valid interval energy |
| running_energy_kwh / expected_energy_kwh | kWh | Actual vs reference energy over deviation-eligible Running intervals |
| avg_wind_speed_ms, max_wind_speed_ms | m/s | Over valid records |
| avg/max gearbox, generator; avg nacelle, ambient temperature | °C | Sensor errors excluded |
| running / idle_low_wind / environmental_stop / planned_maintenance / unplanned_fault / external_grid / missing _minutes | min | Time per availability category (sum = 1 440) |
| energy_data_minutes | min | Minutes with valid power (capacity-factor denominator) |
| valid_records, analysis_records, flagged_records | count | Data-quality counters |
| availability_pct, capacity_factor_pct, performance_deviation_pct, data_coverage_pct | % | Daily values (range KPIs are recomputed from the components) |

## 5. `anomalies`

anomaly_id (deterministic: `ANO-<turbine>-<yyyymmdd-hhmm>-<hash>`), turbine_id, timestamp, end_timestamp,
duration_minutes, anomaly_type, severity (`High`/`Medium`/`Low`), metric, measured_value, unit,
expected_range, explanation, recommended_investigation, detection_method, status (`Open`).

## 6. Other tables

* `monthly_reports` – one row per generated month with headline KPIs, summary JSON and file paths.
* `data_quality_log` – quarantined rows (bad timestamp, duplicate, unknown turbine) with reasons.
* `import_batches` – every load/upload: rows received, inserted, already present, quarantined, flagged, status.

## 7. Power BI files (`powerbi/datasets/`)

| File | Grain | Keys |
|---|---|---|
| Fact_SCADA.csv | turbine × 10 min | date_key, turbine_id |
| Fact_Performance.csv | turbine × day | date_key, turbine_id |
| Fact_Anomalies.csv | anomaly event | date_key, turbine_id |
| Fact_ServiceEvents.csv | service event | date_key (start), turbine_id |
| Dim_Turbine.csv | turbine | turbine_id |
| Dim_Date.csv | day | date_key (yyyymmdd) |
