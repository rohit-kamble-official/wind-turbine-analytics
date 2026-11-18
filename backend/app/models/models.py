"""SQLAlchemy ORM models (normalised schema).

turbines 1-* scada_readings, performance_metrics, service_events, anomalies
monthly_reports, data_quality_log and import_batches are farm-level tables.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Turbine(Base):
    __tablename__ = "turbines"
    turbine_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    turbine_name: Mapped[str] = mapped_column(String(64))
    site_name: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(128))
    rated_power_kw: Mapped[float] = mapped_column(Float)
    rotor_diameter_m: Mapped[float] = mapped_column(Float)
    hub_height_m: Mapped[float] = mapped_column(Float)
    cut_in_ms: Mapped[float] = mapped_column(Float)
    rated_wind_ms: Mapped[float] = mapped_column(Float)
    cut_out_ms: Mapped[float] = mapped_column(Float)
    commissioning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    layout_x_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    layout_y_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_source: Mapped[str] = mapped_column(String(32), default="SIMULATED")

    readings = relationship("ScadaReading", back_populates="turbine", lazy="noload")


class ScadaReading(Base):
    __tablename__ = "scada_readings"
    __table_args__ = (
        UniqueConstraint("turbine_id", "timestamp", name="uq_scada_turbine_ts"),
        Index("ix_scada_turbine_ts", "turbine_id", "timestamp"),
        Index("ix_scada_ts", "timestamp"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.turbine_id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float)
    ambient_temperature_c: Mapped[float | None] = mapped_column(Float)
    rotor_speed_rpm: Mapped[float | None] = mapped_column(Float)
    generator_speed_rpm: Mapped[float | None] = mapped_column(Float)
    active_power_kw: Mapped[float | None] = mapped_column(Float)
    theoretical_power_kw: Mapped[float | None] = mapped_column(Float)
    reactive_power_kvar: Mapped[float | None] = mapped_column(Float)
    nacelle_temperature_c: Mapped[float | None] = mapped_column(Float)
    gearbox_temperature_c: Mapped[float | None] = mapped_column(Float)
    generator_temperature_c: Mapped[float | None] = mapped_column(Float)
    pitch_angle_deg: Mapped[float | None] = mapped_column(Float)
    yaw_angle_deg: Mapped[float | None] = mapped_column(Float)
    operating_status: Mapped[str] = mapped_column(String(16))
    fault_code: Mapped[str] = mapped_column(String(16), default="")
    downtime_minutes: Mapped[float] = mapped_column(Float, default=0)
    interval_category: Mapped[str] = mapped_column(String(32))
    is_valid_for_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    qc_flags: Mapped[str] = mapped_column(Text, default="")

    turbine = relationship("Turbine", back_populates="readings")


class PerformanceMetric(Base):
    """Daily per-turbine KPIs. Minutes per category are stored so availability
    can be recomputed for any date range and any basis without raw data."""
    __tablename__ = "performance_metrics"
    __table_args__ = (UniqueConstraint("turbine_id", "date", name="uq_metric_turbine_date"),
                      Index("ix_metric_date", "date"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.turbine_id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0)
    running_energy_kwh: Mapped[float] = mapped_column(Float, default=0)
    expected_energy_kwh: Mapped[float] = mapped_column(Float, default=0)
    avg_wind_speed_ms: Mapped[float | None] = mapped_column(Float)
    max_wind_speed_ms: Mapped[float | None] = mapped_column(Float)
    avg_power_kw: Mapped[float | None] = mapped_column(Float)
    avg_ambient_temp_c: Mapped[float | None] = mapped_column(Float)
    avg_nacelle_temp_c: Mapped[float | None] = mapped_column(Float)
    avg_gearbox_temp_c: Mapped[float | None] = mapped_column(Float)
    max_gearbox_temp_c: Mapped[float | None] = mapped_column(Float)
    avg_generator_temp_c: Mapped[float | None] = mapped_column(Float)
    max_generator_temp_c: Mapped[float | None] = mapped_column(Float)
    valid_records: Mapped[int] = mapped_column(Integer, default=0)
    analysis_records: Mapped[int] = mapped_column(Integer, default=0)
    flagged_records: Mapped[int] = mapped_column(Integer, default=0)
    downtime_minutes: Mapped[float] = mapped_column(Float, default=0)
    running_minutes: Mapped[float] = mapped_column(Float, default=0)
    idle_low_wind_minutes: Mapped[float] = mapped_column(Float, default=0)
    environmental_stop_minutes: Mapped[float] = mapped_column(Float, default=0)
    planned_maintenance_minutes: Mapped[float] = mapped_column(Float, default=0)
    unplanned_fault_minutes: Mapped[float] = mapped_column(Float, default=0)
    external_grid_minutes: Mapped[float] = mapped_column(Float, default=0)
    missing_minutes: Mapped[float] = mapped_column(Float, default=0)
    energy_data_minutes: Mapped[float] = mapped_column(Float, default=0)
    data_coverage_pct: Mapped[float | None] = mapped_column(Float)
    availability_pct: Mapped[float | None] = mapped_column(Float)
    capacity_factor_pct: Mapped[float | None] = mapped_column(Float)
    performance_deviation_pct: Mapped[float | None] = mapped_column(Float)


class ServiceEvent(Base):
    __tablename__ = "service_events"
    __table_args__ = (Index("ix_service_turbine_start", "turbine_id", "start_time"),)
    event_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.turbine_id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    duration_hours: Mapped[float] = mapped_column(Float)
    event_type: Mapped[str] = mapped_column(String(32))
    is_planned: Mapped[bool] = mapped_column(Boolean)
    fault_code: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(256))


class Anomaly(Base):
    __tablename__ = "anomalies"
    __table_args__ = (Index("ix_anomaly_turbine_ts", "turbine_id", "timestamp"),)
    anomaly_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    turbine_id: Mapped[str] = mapped_column(ForeignKey("turbines.turbine_id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    end_timestamp: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    anomaly_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    metric: Mapped[str] = mapped_column(String(64))
    measured_value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    expected_range: Mapped[str] = mapped_column(String(128))
    explanation: Mapped[str] = mapped_column(Text)
    recommended_investigation: Mapped[str] = mapped_column(Text)
    detection_method: Mapped[str] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(24), default="Open")


class MonthlyReport(Base):
    __tablename__ = "monthly_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month: Mapped[str] = mapped_column(String(7), unique=True)  # YYYY-MM
    generated_at: Mapped[datetime] = mapped_column(DateTime)
    energy_mwh: Mapped[float] = mapped_column(Float)
    avg_wind_speed_ms: Mapped[float | None] = mapped_column(Float)
    availability_pct: Mapped[float | None] = mapped_column(Float)
    capacity_factor_pct: Mapped[float | None] = mapped_column(Float)
    performance_deviation_pct: Mapped[float | None] = mapped_column(Float)
    downtime_hours: Mapped[float] = mapped_column(Float)
    anomaly_count: Mapped[int] = mapped_column(Integer)
    data_coverage_pct: Mapped[float | None] = mapped_column(Float)
    summary_json: Mapped[str] = mapped_column(Text)
    excel_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


class DataQualityLog(Base):
    """Rows that could not be stored as records (quarantine) - nothing is dropped silently."""
    __tablename__ = "data_quality_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    source_row: Mapped[int] = mapped_column(Integer)
    timestamp_raw: Mapped[str] = mapped_column(String(64))
    turbine_id: Mapped[str] = mapped_column(String(32))
    issue: Mapped[str] = mapped_column(Text)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(256))
    imported_at: Mapped[datetime] = mapped_column(DateTime)
    rows_received: Mapped[int] = mapped_column(Integer)
    rows_inserted: Mapped[int] = mapped_column(Integer)
    rows_already_present: Mapped[int] = mapped_column(Integer)
    rows_quarantined: Mapped[int] = mapped_column(Integer)
    rows_flagged: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))  # completed | recomputing | failed
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
