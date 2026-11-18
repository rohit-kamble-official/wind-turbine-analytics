-- =====================================================================
-- Wind Turbine Performance Analytics - useful SQL queries (SQLite)
-- Database: data/wind_turbine.db  (SIMULATED data)
-- Run with:  python scripts/run_sql.py sql/performance_queries.sql
-- Every query below is executed by that script, so they are all verified.
-- =====================================================================

-- Q1. Fleet KPIs for a period (ratio of sums, never an average of daily ratios)
--     Availability (technical basis) = available / eligible minutes
SELECT
    ROUND(SUM(energy_kwh) / 1000.0, 1)                                         AS energy_mwh,
    ROUND(SUM(avg_wind_speed_ms * analysis_records) / SUM(analysis_records), 2) AS avg_wind_ms,
    ROUND(100.0 * SUM(running_minutes + idle_low_wind_minutes + environmental_stop_minutes)
          / SUM(running_minutes + idle_low_wind_minutes + environmental_stop_minutes
                + unplanned_fault_minutes + planned_maintenance_minutes), 2)    AS availability_pct,
    ROUND(100.0 * SUM(energy_kwh) / (3000.0 * SUM(energy_data_minutes) / 60.0), 2) AS capacity_factor_pct,
    ROUND(100.0 * (SUM(running_energy_kwh) - SUM(expected_energy_kwh)) / SUM(expected_energy_kwh), 2)
                                                                               AS performance_deviation_pct
FROM performance_metrics
WHERE date BETWEEN '2026-03-01' AND '2026-03-31';

-- Q2. Monthly energy and availability per turbine
SELECT turbine_id,
       strftime('%Y-%m', date)                       AS month,
       ROUND(SUM(energy_kwh) / 1000.0, 1)            AS energy_mwh,
       ROUND(100.0 * SUM(running_minutes + idle_low_wind_minutes + environmental_stop_minutes)
             / SUM(running_minutes + idle_low_wind_minutes + environmental_stop_minutes
                   + unplanned_fault_minutes + planned_maintenance_minutes), 2) AS availability_pct
FROM performance_metrics
GROUP BY turbine_id, month
ORDER BY turbine_id, month;

-- Q3. Turbine ranking by performance deviation vs reference curve
SELECT turbine_id,
       ROUND(SUM(running_energy_kwh) / 1000.0, 1)  AS actual_mwh,
       ROUND(SUM(expected_energy_kwh) / 1000.0, 1) AS expected_mwh,
       ROUND(100.0 * (SUM(running_energy_kwh) - SUM(expected_energy_kwh)) / SUM(expected_energy_kwh), 2) AS deviation_pct
FROM performance_metrics
GROUP BY turbine_id
ORDER BY deviation_pct ASC;

-- Q4. Downtime hours by category and turbine
SELECT turbine_id,
       ROUND(SUM(planned_maintenance_minutes) / 60.0, 1) AS planned_h,
       ROUND(SUM(unplanned_fault_minutes) / 60.0, 1)     AS unplanned_h,
       ROUND(SUM(external_grid_minutes) / 60.0, 1)       AS external_h,
       ROUND(SUM(environmental_stop_minutes) / 60.0, 1)  AS high_wind_stop_h
FROM performance_metrics
GROUP BY turbine_id
ORDER BY unplanned_h DESC;

-- Q5. Downtime by fault code from the 10-minute data (each row = 10 min)
SELECT fault_code, interval_category, COUNT(*) * 10 / 60.0 AS hours
FROM scada_readings
WHERE interval_category IN ('planned_maintenance', 'unplanned_fault', 'external_grid')
GROUP BY fault_code, interval_category
ORDER BY hours DESC;

-- Q6. Measured power curve for one turbine (0.5 m/s bins, valid running data)
SELECT ROUND(wind_speed_ms * 2) / 2.0         AS bin_ms,
       COUNT(*)                               AS n,
       ROUND(AVG(active_power_kw), 1)         AS measured_kw,
       ROUND(AVG(theoretical_power_kw), 1)    AS expected_kw
FROM scada_readings
WHERE turbine_id = 'WTG07'
  AND operating_status = 'Running'
  AND is_valid_for_analysis = 1
GROUP BY bin_ms
ORDER BY bin_ms;

-- Q7. Hourly energy for one day (uses the (turbine_id, timestamp) index)
SELECT strftime('%Y-%m-%d %H:00', timestamp) AS hour,
       ROUND(SUM(active_power_kw) / 6.0, 1)  AS energy_kwh
FROM scada_readings
WHERE turbine_id = 'WTG01'
  AND timestamp >= '2026-02-16 00:00:00' AND timestamp < '2026-02-17 00:00:00'
  AND is_valid_for_analysis = 1
GROUP BY hour
ORDER BY hour;

-- Q8. High-severity anomalies with the recommended check
SELECT anomaly_id, turbine_id, timestamp, anomaly_type, measured_value, unit, recommended_investigation
FROM anomalies
WHERE severity = 'High'
ORDER BY timestamp
LIMIT 20;

-- Q9. Anomalies followed by a service event on the same turbine within 7 days
SELECT a.anomaly_id, a.turbine_id, a.timestamp AS anomaly_time, a.anomaly_type,
       s.event_id, s.start_time, s.fault_code, s.description
FROM anomalies a
JOIN service_events s
  ON s.turbine_id = a.turbine_id
 AND s.start_time BETWEEN a.timestamp AND datetime(a.timestamp, '+7 days')
ORDER BY a.timestamp;

-- Q10. Data-quality: flagged readings per turbine and month
SELECT turbine_id, strftime('%Y-%m', timestamp) AS month,
       COUNT(*)                                            AS readings,
       SUM(CASE WHEN qc_flags <> '' THEN 1 ELSE 0 END)     AS flagged,
       SUM(CASE WHEN is_valid_for_analysis = 0 THEN 1 ELSE 0 END) AS excluded_from_analysis
FROM scada_readings
GROUP BY turbine_id, month
ORDER BY turbine_id, month;

-- Q11. Quarantined rows (could not be stored as records) and why
SELECT issue, COUNT(*) AS rows
FROM data_quality_log
GROUP BY issue
ORDER BY rows DESC;

-- Q12. Daily fleet energy with 7-day moving average (window function)
SELECT date, ROUND(energy_mwh, 1) AS energy_mwh,
       ROUND(AVG(energy_mwh) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS ma7_mwh
FROM (SELECT date, SUM(energy_kwh) / 1000.0 AS energy_mwh FROM performance_metrics GROUP BY date)
ORDER BY date;
