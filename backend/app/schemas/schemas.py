"""Pydantic response models (also drive the OpenAPI documentation)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class HealthResponse(BaseModel):
    status: str
    database: str
    data_source: str = "SIMULATED"
    turbines: int
    scada_records: int
    anomalies: int
    data_start: date | None
    data_end: date | None
    last_import: datetime | None = None
    last_import_status: str | None = None
    version: str
    demo_mode: bool = False


class TurbineOut(ORM):
    turbine_id: str
    turbine_name: str
    site_name: str
    model: str
    rated_power_kw: float
    rotor_diameter_m: float
    hub_height_m: float
    cut_in_ms: float
    rated_wind_ms: float
    cut_out_ms: float
    commissioning_date: date | None
    layout_x_m: float | None
    layout_y_m: float | None
    data_source: str


class LatestReading(BaseModel):
    timestamp: datetime
    operating_status: str
    fault_code: str
    wind_speed_ms: float | None
    active_power_kw: float | None
    gearbox_temperature_c: float | None
    generator_temperature_c: float | None


class PeriodKpis(BaseModel):
    energy_mwh: float | None = None
    avg_wind_speed_ms: float | None = None
    availability_pct: float | None = None
    capacity_factor_pct: float | None = None
    performance_deviation_pct: float | None = None
    downtime_hours: float | None = None
    planned_downtime_hours: float | None = None
    unplanned_downtime_hours: float | None = None
    external_downtime_hours: float | None = None
    data_coverage_pct: float | None = None


class TurbineStatusRow(PeriodKpis):
    turbine_id: str
    latest: LatestReading | None
    latest_alert: str | None = None
    latest_alert_severity: str | None = None
    latest_alert_time: datetime | None = None
    anomaly_count: int = 0


class TurbineDetail(BaseModel):
    turbine: TurbineOut
    latest: LatestReading | None
    period: PeriodKpis
    open_anomalies: int


class KpiSummary(PeriodKpis):
    start_date: date | None
    end_date: date | None
    turbine_id: str | None
    active_turbines: int
    total_turbines: int
    anomaly_count: int
    availability_basis: str
    availability_definition: str


class DailyMetric(BaseModel):
    date: date
    turbine_id: str | None = None
    energy_mwh: float | None
    avg_wind_speed_ms: float | None
    availability_pct: float | None
    capacity_factor_pct: float | None
    performance_deviation_pct: float | None
    downtime_hours: float | None
    expected_energy_mwh: float | None = None


class MonthlyMetric(BaseModel):
    month: str
    turbine_id: str | None = None
    energy_mwh: float | None
    avg_wind_speed_ms: float | None
    availability_pct: float | None
    capacity_factor_pct: float | None
    performance_deviation_pct: float | None
    downtime_hours: float | None


class AvailabilityRow(BaseModel):
    turbine_id: str
    availability_pct: float | None
    available_hours: float
    eligible_hours: float
    running_hours: float
    idle_low_wind_hours: float
    environmental_stop_hours: float
    planned_maintenance_hours: float
    unplanned_fault_hours: float
    external_grid_hours: float
    missing_data_hours: float


class AvailabilityResponse(BaseModel):
    basis: str
    definition: str
    fleet_availability_pct: float | None
    turbines: list[AvailabilityRow]


class CapacityFactorRow(BaseModel):
    turbine_id: str
    energy_mwh: float
    eligible_hours: float
    max_possible_energy_mwh: float
    capacity_factor_pct: float | None


class CapacityFactorResponse(BaseModel):
    rated_power_kw: float
    fleet_capacity_factor_pct: float | None
    turbines: list[CapacityFactorRow]


class PowerCurveBin(BaseModel):
    bin_center_ms: float
    count: int
    avg_wind_speed_ms: float
    avg_power_kw: float
    expected_power_kw: float
    deviation_pct: float | None
    std_power_kw: float | None
    low_confidence: bool


class CurvePoint(BaseModel):
    wind_speed_ms: float
    power_kw: float


class ScatterPoint(BaseModel):
    wind_speed_ms: float
    active_power_kw: float
    turbine_id: str


class PowerCurveResponse(BaseModel):
    bin_width_ms: float
    records_used: int
    bins: list[PowerCurveBin]
    reference_curve: list[CurvePoint]
    scatter: list[ScatterPoint]
    note: str


class DeviationRow(BaseModel):
    turbine_id: str
    performance_deviation_pct: float | None
    actual_energy_mwh: float
    expected_energy_mwh: float
    relative_to_fleet_pp: float | None


class DeviationResponse(BaseModel):
    fleet_deviation_pct: float | None
    definition: str
    turbines: list[DeviationRow]
    daily: list[DailyMetric]


class AnomalyOut(ORM):
    anomaly_id: str
    turbine_id: str
    timestamp: datetime
    end_timestamp: datetime
    duration_minutes: int
    anomaly_type: str
    severity: str
    metric: str
    measured_value: float
    unit: str
    expected_range: str
    explanation: str
    recommended_investigation: str
    detection_method: str
    status: str


class AnomalyPage(Page[AnomalyOut]):
    by_type: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)


class ServiceEventOut(ORM):
    event_id: str
    turbine_id: str
    start_time: datetime
    end_time: datetime
    duration_hours: float
    event_type: str
    is_planned: bool
    fault_code: str
    description: str


class DowntimeTurbine(BaseModel):
    turbine_id: str
    planned_hours: float
    unplanned_hours: float
    external_hours: float
    environmental_stop_hours: float
    total_downtime_hours: float


class DowntimeResponse(BaseModel):
    total_downtime_hours: float
    planned_hours: float
    unplanned_hours: float
    fault_related_hours: float
    external_hours: float
    environmental_stop_hours: float
    missing_data_hours: float
    by_turbine: list[DowntimeTurbine]
    by_fault_code: list[dict]
    events: list[ServiceEventOut]


class ScadaOut(ORM):
    timestamp: datetime
    turbine_id: str
    wind_speed_ms: float | None
    ambient_temperature_c: float | None
    rotor_speed_rpm: float | None
    generator_speed_rpm: float | None
    active_power_kw: float | None
    theoretical_power_kw: float | None
    reactive_power_kvar: float | None
    nacelle_temperature_c: float | None
    gearbox_temperature_c: float | None
    generator_temperature_c: float | None
    pitch_angle_deg: float | None
    yaw_angle_deg: float | None
    operating_status: str
    fault_code: str
    downtime_minutes: float
    interval_category: str
    is_valid_for_analysis: bool
    qc_flags: str


class TemperaturePoint(BaseModel):
    date: date
    avg_gearbox_temp_c: float | None
    max_gearbox_temp_c: float | None
    avg_generator_temp_c: float | None
    max_generator_temp_c: float | None
    avg_nacelle_temp_c: float | None
    avg_ambient_temp_c: float | None


class ImportBatchOut(ORM):
    id: int
    source: str
    imported_at: datetime
    rows_received: int
    rows_inserted: int
    rows_already_present: int
    rows_quarantined: int
    rows_flagged: int
    status: str
    message: str | None


class UploadResponse(BaseModel):
    batch: ImportBatchOut
    validation: dict
    recompute: str
