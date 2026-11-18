// Types mirror backend/app/schemas/schemas.py

export interface Health {
  status: string;
  database: string;
  data_source: string;
  turbines: number;
  scada_records: number;
  anomalies: number;
  data_start: string | null;
  data_end: string | null;
  last_import: string | null;
  last_import_status: string | null;
  version: string;
  demo_mode?: boolean;
}

export interface Turbine {
  turbine_id: string;
  turbine_name: string;
  site_name: string;
  model: string;
  rated_power_kw: number;
  rotor_diameter_m: number;
  hub_height_m: number;
  cut_in_ms: number;
  rated_wind_ms: number;
  cut_out_ms: number;
  commissioning_date: string | null;
  data_source: string;
}

export interface PeriodKpis {
  energy_mwh: number | null;
  avg_wind_speed_ms: number | null;
  availability_pct: number | null;
  capacity_factor_pct: number | null;
  performance_deviation_pct: number | null;
  downtime_hours: number | null;
  planned_downtime_hours: number | null;
  unplanned_downtime_hours: number | null;
  external_downtime_hours: number | null;
  data_coverage_pct: number | null;
}

export interface KpiSummary extends PeriodKpis {
  active_turbines: number;
  total_turbines: number;
  anomaly_count: number;
  availability_basis: string;
  availability_definition: string;
}

export interface LatestReading {
  timestamp: string;
  operating_status: "Running" | "Idle" | "Fault" | "Maintenance" | string;
  fault_code: string;
  wind_speed_ms: number | null;
  active_power_kw: number | null;
  gearbox_temperature_c: number | null;
  generator_temperature_c: number | null;
}

export interface TurbineStatusRow extends PeriodKpis {
  turbine_id: string;
  latest: LatestReading | null;
  latest_alert: string | null;
  latest_alert_severity: Severity | null;
  latest_alert_time: string | null;
  anomaly_count: number;
}

export interface DailyMetric {
  date: string;
  turbine_id: string | null;
  energy_mwh: number | null;
  avg_wind_speed_ms: number | null;
  availability_pct: number | null;
  capacity_factor_pct: number | null;
  performance_deviation_pct: number | null;
  downtime_hours: number | null;
  expected_energy_mwh: number | null;
}

export interface MonthlyMetric {
  month: string;
  turbine_id: string | null;
  energy_mwh: number | null;
  avg_wind_speed_ms: number | null;
  availability_pct: number | null;
  capacity_factor_pct: number | null;
  performance_deviation_pct: number | null;
  downtime_hours: number | null;
}

export interface AvailabilityRow {
  turbine_id: string;
  availability_pct: number | null;
  available_hours: number;
  eligible_hours: number;
  running_hours: number;
  idle_low_wind_hours: number;
  environmental_stop_hours: number;
  planned_maintenance_hours: number;
  unplanned_fault_hours: number;
  external_grid_hours: number;
  missing_data_hours: number;
}

export interface AvailabilityResponse {
  basis: string;
  definition: string;
  fleet_availability_pct: number | null;
  turbines: AvailabilityRow[];
}

export interface CapacityFactorResponse {
  rated_power_kw: number;
  fleet_capacity_factor_pct: number | null;
  turbines: { turbine_id: string; energy_mwh: number; eligible_hours: number; max_possible_energy_mwh: number; capacity_factor_pct: number | null }[];
}

export interface PowerCurveBin {
  bin_center_ms: number;
  count: number;
  avg_wind_speed_ms: number;
  avg_power_kw: number;
  expected_power_kw: number;
  deviation_pct: number | null;
  std_power_kw: number | null;
  low_confidence: boolean;
}

export interface PowerCurveResponse {
  bin_width_ms: number;
  records_used: number;
  bins: PowerCurveBin[];
  reference_curve: { wind_speed_ms: number; power_kw: number }[];
  scatter: { wind_speed_ms: number; active_power_kw: number; turbine_id: string }[];
  note: string;
}

export interface DeviationResponse {
  fleet_deviation_pct: number | null;
  definition: string;
  turbines: { turbine_id: string; performance_deviation_pct: number | null; actual_energy_mwh: number; expected_energy_mwh: number; relative_to_fleet_pp: number | null }[];
  daily: DailyMetric[];
}

export type Severity = "High" | "Medium" | "Low";

export interface Anomaly {
  anomaly_id: string;
  turbine_id: string;
  timestamp: string;
  end_timestamp: string;
  duration_minutes: number;
  anomaly_type: string;
  severity: Severity;
  metric: string;
  measured_value: number;
  unit: string;
  expected_range: string;
  explanation: string;
  recommended_investigation: string;
  detection_method: string;
  status: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AnomalyPage extends Page<Anomaly> {
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface ServiceEvent {
  event_id: string;
  turbine_id: string;
  start_time: string;
  end_time: string;
  duration_hours: number;
  event_type: string;
  is_planned: boolean;
  fault_code: string;
  description: string;
}

export interface DowntimeResponse {
  total_downtime_hours: number;
  planned_hours: number;
  unplanned_hours: number;
  fault_related_hours: number;
  external_hours: number;
  environmental_stop_hours: number;
  missing_data_hours: number;
  by_turbine: { turbine_id: string; planned_hours: number; unplanned_hours: number; external_hours: number; environmental_stop_hours: number; total_downtime_hours: number }[];
  by_fault_code: { fault_code: string; category: string; hours: number }[];
  events: ServiceEvent[];
}

export interface TemperaturePoint {
  date: string;
  avg_gearbox_temp_c: number | null;
  max_gearbox_temp_c: number | null;
  avg_generator_temp_c: number | null;
  max_generator_temp_c: number | null;
  avg_nacelle_temp_c: number | null;
  avg_ambient_temp_c: number | null;
}

export interface ScadaRow {
  timestamp: string;
  turbine_id: string;
  wind_speed_ms: number | null;
  active_power_kw: number | null;
  theoretical_power_kw: number | null;
  rotor_speed_rpm: number | null;
  pitch_angle_deg: number | null;
  gearbox_temperature_c: number | null;
  operating_status: string;
  fault_code: string;
  is_valid_for_analysis: boolean;
  qc_flags: string;
}

export interface ImportBatch {
  id: number;
  source: string;
  imported_at: string;
  rows_received: number;
  rows_inserted: number;
  rows_already_present: number;
  rows_quarantined: number;
  rows_flagged: number;
  status: string;
  message: string | null;
}

export interface UploadResponse {
  batch: ImportBatch;
  validation: Record<string, number>;
  recompute: string;
}

export interface QualityReport {
  data_source: string;
  period_start: string;
  period_end: string;
  total_rows: number;
  valid_records: number;
  valid_for_analysis: number;
  quarantined_rows: number;
  missing_intervals: number;
  expected_intervals: number;
  data_quality_score_pct: number;
  flag_counts: Record<string, number>;
  flag_descriptions: Record<string, string>;
  missing_values_by_column: Record<string, number>;
  per_turbine: { turbine_id: string; valid_records: number; missing_intervals: number; completeness_pct: number; analysis_ready_pct: number; flagged_rows: number }[];
}

export interface MonthlyReport {
  month: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  disclaimer: string;
  executive_summary: string;
  kpis: KpiSummary & { anomaly_count: number; turbines: number };
  turbine_performance: (PeriodKpis & { turbine_id: string; anomalies: number; data_hours: number })[];
  key_findings: string[];
  recommended_investigations: string[];
  notes: string[];
  anomalies: { total: number; by_severity: Record<string, number>; by_type: Record<string, number> };
}
