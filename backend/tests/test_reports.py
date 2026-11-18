import pandas as pd
from openpyxl import load_workbook

from app.core.config import settings
from app.reports.monthly_report import available_months, build_monthly_report
from app.reports.powerbi_export import build_dim_date, export_powerbi
from app.reports.report_service import generate_month

SHEETS = ["Executive Summary", "Turbine Performance", "Daily Energy", "Monthly Energy", "Availability", "Downtime",
          "Anomalies", "Data Quality"]


def test_monthly_report_sections(db_session):
    assert available_months(db_session)[:2] == ["2026-04", "2026-05"]
    r = build_monthly_report(db_session, "2026-05")
    for key in ("executive_summary", "kpis", "turbine_performance", "daily_energy", "monthly_energy", "power_curve",
                "downtime", "anomalies", "data_quality", "key_findings", "recommended_investigations"):
        assert key in r and r[key] is not None, key
    assert len(r["turbine_performance"]) == 4
    assert sum(t["energy_mwh"] for t in r["turbine_performance"]) == pert(r["kpis"]["energy_mwh"])


def pert(x):  # tolerant equality helper for floats rounded to 3 dp
    class _A(float):
        def __eq__(self, o):
            return abs(float(self) - o) < 0.01
    return _A(x)


def test_excel_report_structure(db_session):
    out = generate_month(db_session, "2026-05", pdf=False, csv=True)
    wb = load_workbook(out["excel"])
    assert wb.sheetnames == SHEETS
    tp = wb["Turbine Performance"]
    assert str(tp["F5"].value).startswith("=IFERROR(B5/(E5*D5)*100")  # capacity factor formula
    assert str(tp["B9"].value).startswith("=SUM(B5:B8)")                 # fleet total row
    assert len(tp._charts) == 1 and len(wb["Daily Energy"]._charts) == 1
    assert "SIMULATED" in wb["Executive Summary"]["A2"].value
    assert len(out["csv"]) == 5 and all(pd.read_csv(p) is not None for p in out["csv"])


def test_pdf_report(db_session):
    out = generate_month(db_session, "2026-04", excel=False, csv=False)
    data = open(out["pdf"], "rb").read()
    assert data[:4] == b"%PDF" and len(data) > 30_000


def test_powerbi_export(db_session):
    paths = export_powerbi(db_session, settings.powerbi_dir)
    assert set(paths) == {"Dim_Turbine", "Dim_Date", "Fact_Performance", "Fact_Anomalies", "Fact_ServiceEvents",
                          "Fact_SCADA"}
    perf = pd.read_csv(paths["Fact_Performance"])
    dim_date = pd.read_csv(paths["Dim_Date"])
    scada = pd.read_csv(paths["Fact_SCADA"], nrows=1000)
    assert set(perf["date_key"]) <= set(dim_date["date_key"])          # relationship integrity
    assert set(scada["turbine_id"]) <= set(pd.read_csv(paths["Dim_Turbine"])["turbine_id"])
    assert {"energy_kwh", "date_key"} <= set(scada.columns)


def test_dim_date():
    d = build_dim_date("2026-01-30", "2026-02-02")
    assert d["date_key"].tolist() == [20260130, 20260131, 20260201, 20260202]
    assert d["season"].iloc[0] == "Winter" and d["quarter"].iloc[0] == "Q1"
