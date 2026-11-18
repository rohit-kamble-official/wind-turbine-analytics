# DAX measures

Create these in a dedicated measure table (Home → Enter data → name it `_Measures`).
They assume the star schema described in [powerbi_guide.md](powerbi_guide.md).
Ratios are built from summed components so they stay correct for any slicer selection.

```DAX
-- 1. Total Energy (MWh)
Total Energy (MWh) =
DIVIDE ( SUM ( Fact_Performance[energy_kwh] ), 1000 )

-- 2. Average Availability (%)  - time-based, technical basis
Available Minutes =
SUM ( Fact_Performance[running_minutes] )
    + SUM ( Fact_Performance[idle_low_wind_minutes] )
    + SUM ( Fact_Performance[environmental_stop_minutes] )

Eligible Minutes =
[Available Minutes]
    + SUM ( Fact_Performance[unplanned_fault_minutes] )
    + SUM ( Fact_Performance[planned_maintenance_minutes] )

Average Availability (%) =
DIVIDE ( [Available Minutes], [Eligible Minutes] ) * 100

-- optional: contractual basis (planned maintenance excluded from eligible time)
Contractual Availability (%) =
DIVIDE ( [Available Minutes],
         [Eligible Minutes] - SUM ( Fact_Performance[planned_maintenance_minutes] ) ) * 100

-- 3. Capacity Factor (%)
Capacity Factor (%) =
DIVIDE (
    SUM ( Fact_Performance[energy_kwh] ),
    SUM ( Fact_Performance[max_possible_energy_kwh] )
) * 100

-- 4. Total Downtime (Hours)
Total Downtime (Hours) =
SUM ( Fact_Performance[downtime_hours] )

Unplanned Downtime (Hours) =
DIVIDE ( SUM ( Fact_Performance[unplanned_fault_minutes] ), 60 )

-- 5. Average Wind Speed (record-weighted, not an average of daily averages)
Average Wind Speed (m/s) =
DIVIDE (
    SUMX ( Fact_Performance, Fact_Performance[avg_wind_speed_ms] * Fact_Performance[analysis_records] ),
    SUM ( Fact_Performance[analysis_records] )
)

-- 6. Total Turbines (in the current filter context)
Total Turbines =
DISTINCTCOUNT ( Fact_Performance[turbine_id] )

-- 7. Performance Deviation (%) - energy-weighted vs reference power curve
Performance Deviation (%) =
VAR Actual   = SUM ( Fact_Performance[running_energy_kwh] )
VAR Expected = SUM ( Fact_Performance[expected_energy_kwh] )
RETURN DIVIDE ( Actual - Expected, Expected ) * 100

-- 8. Anomaly Count
Anomaly Count =
COUNTROWS ( Fact_Anomalies )

High Severity Anomalies =
CALCULATE ( [Anomaly Count], Fact_Anomalies[severity] = "High" )

-- Helpers
Data Coverage (%) =
DIVIDE ( SUM ( Fact_Performance[energy_data_minutes] ),
         [Eligible Minutes] + SUM ( Fact_Performance[external_grid_minutes] )
           + SUM ( Fact_Performance[missing_minutes] ) ) * 100

Energy MTD (MWh) =
TOTALMTD ( [Total Energy (MWh)], Dim_Date[date] )

Deviation vs Fleet (pp) =
[Performance Deviation (%)]
    - CALCULATE ( [Performance Deviation (%)], ALL ( Dim_Turbine ) )
```

Format: energy `#,0.0`, percentages `0.00`, hours `#,0.0`.

### Cross-check against the application

With no slicers and the default dataset, the measures should return the same values as
`GET /api/metrics/summary`: Total Energy ≈ 45 626 MWh, Availability ≈ 98.34 %,
Capacity Factor ≈ 35.21 %, Performance Deviation ≈ −1.23 %, Downtime ≈ 776 h, 76 anomalies.
