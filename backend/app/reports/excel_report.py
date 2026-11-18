"""Monthly Excel report (OpenPyXL) with formulas, charts and labelled units."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

NAVY = "0B2545"
GREEN = "1B998B"
LIGHT = "F1F5F9"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color=NAVY)
SUB_FONT = Font(italic=True, size=9, color="64748B")
THIN = Side(style="thin", color="CBD5E1")
BORDER = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
TOTAL_FILL = PatternFill("solid", fgColor=LIGHT)


def _title(ws: Worksheet, title: str, disclaimer: str) -> None:
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A2"] = disclaimer
    ws["A2"].font = SUB_FONT


def _table(ws: Worksheet, start_row: int, headers: list[str], rows: list[list], formats: dict[int, str] | None = None
           ) -> tuple[int, int]:
    """Write a formatted table; returns (first_data_row, last_data_row)."""
    formats = formats or {}
    for j, h in enumerate(headers, 1):
        c = ws.cell(row=start_row, column=j, value=h)
        c.fill, c.font, c.border = HEADER_FILL, HEADER_FONT, BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[start_row].height = 32
    for i, row in enumerate(rows, start_row + 1):
        for j, v in enumerate(row, 1):
            c = ws.cell(row=i, column=j, value=v)
            c.border = BORDER
            if j in formats:
                c.number_format = formats[j]
    for j, h in enumerate(headers, 1):
        width = max([len(str(h))] + [len(str(r[j - 1])) for r in rows[:200] if j - 1 < len(r)]) + 2
        ws.column_dimensions[get_column_letter(j)].width = min(max(width, 10), 60)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    return start_row + 1, start_row + len(rows)


def _n(v, default=0.0):
    return default if v is None else v


def build_excel_report(report: dict, out_path: Path, rated_power_kw: float = 3000.0) -> Path:
    wb = Workbook()
    disc = report["disclaimer"]
    k = report["kpis"]
    tp = report["turbine_performance"]

    # ---------------------------------------------------------- Turbine Performance (formulas)
    ws_tp = wb.active
    ws_tp.title = "Turbine Performance"
    _title(ws_tp, f"Turbine Performance - {report['month']}", disc)
    headers = ["Turbine", "Energy (MWh)", "Avg wind (m/s)", "Valid data hours (h)", "Rated power (MW)",
               "Capacity factor (%)", "Availability (%)", "Perf. deviation (%)", "Downtime (h)", "Anomalies"]
    rows = []
    first = 5
    for i, t in enumerate(tp):
        r = first + i
        rows.append([t["turbine_id"], _n(t["energy_mwh"]), t["avg_wind_speed_ms"], _n(t["data_hours"]),
                     rated_power_kw / 1000, f"=IFERROR(B{r}/(E{r}*D{r})*100,\"\")", t["availability_pct"],
                     t["performance_deviation_pct"], _n(t["downtime_hours"]), t["anomalies"]])
    fmt = {2: "#,##0.0", 3: "0.00", 4: "#,##0.0", 5: "0.0", 6: "0.0", 7: "0.00", 8: "+0.00;-0.00", 9: "#,##0.0"}
    f_row, l_row = _table(ws_tp, first - 1, headers, rows, fmt)
    tr = l_row + 1
    totals = ["Fleet total / mean", f"=SUM(B{f_row}:B{l_row})", f"=AVERAGE(C{f_row}:C{l_row})",
              f"=SUM(D{f_row}:D{l_row})", rated_power_kw / 1000, f"=IFERROR(B{tr}/(E{tr}*D{tr})*100,\"\")",
              k["availability_pct"], k["performance_deviation_pct"], f"=SUM(I{f_row}:I{l_row})",
              f"=SUM(J{f_row}:J{l_row})"]
    for j, v in enumerate(totals, 1):
        c = ws_tp.cell(row=tr, column=j, value=v)
        c.font, c.fill, c.border = Font(bold=True), TOTAL_FILL, BORDER
        if j in fmt:
            c.number_format = fmt[j]
    ws_tp.cell(row=tr + 2, column=1, value="Capacity factor = Energy / (Rated power x valid data hours) x 100 "
               "(Excel formula). Fleet availability and deviation are computed from summed components, "
               "not averaged.").font = SUB_FONT
    ch = BarChart()
    ch.title, ch.y_axis.title, ch.height, ch.width = "Energy by turbine (MWh)", "MWh", 7.5, 16
    ch.add_data(Reference(ws_tp, min_col=2, min_row=first - 1, max_row=l_row), titles_from_data=True)
    ch.set_categories(Reference(ws_tp, min_col=1, min_row=f_row, max_row=l_row))
    ch.legend = None
    ws_tp.add_chart(ch, f"L{first}")

    # ---------------------------------------------------------- Executive Summary
    ws = wb.create_sheet("Executive Summary", 0)
    _title(ws, f"Wind Farm Monthly Performance Report - {report['month']}", disc)
    ws["A4"] = "Period"
    ws["B4"] = f"{report['period_start']} to {report['period_end']}"
    ws["A5"] = "Generated"
    ws["B5"] = report["generated_at"]
    ws["A7"] = "Executive summary"
    ws["A7"].font = Font(bold=True, size=12, color=NAVY)
    ws["A8"] = report["executive_summary"]
    ws.merge_cells("A8:F12")
    ws["A8"].alignment = Alignment(wrap_text=True, vertical="top")
    kpi_rows = [
        ["Total energy production", f"='Turbine Performance'!B{tr}", "MWh"],
        ["Average wind speed", k["avg_wind_speed_ms"], "m/s"],
        ["Fleet availability (time-based)", k["availability_pct"], "%"],
        ["Capacity factor", f"='Turbine Performance'!F{tr}", "%"],
        ["Performance deviation vs reference", k["performance_deviation_pct"], "%"],
        ["Total downtime", f"='Turbine Performance'!I{tr}", "h"],
        ["  of which planned", k["planned_downtime_hours"], "h"],
        ["  of which unplanned", k["unplanned_downtime_hours"], "h"],
        ["  of which external (grid)", k["external_downtime_hours"], "h"],
        ["Anomalies raised", f"='Turbine Performance'!J{tr}", "count"],
        ["Turbines", k["turbines"], "count"],
        ["Data coverage", k["data_coverage_pct"], "%"],
    ]
    _table(ws, 14, ["KPI", "Value", "Unit"], kpi_rows, {2: "#,##0.00"})
    ws.freeze_panes = None
    r0 = 14 + len(kpi_rows) + 2
    ws.cell(row=r0, column=1, value="Key findings").font = Font(bold=True, size=12, color=NAVY)
    for i, f in enumerate(report["key_findings"], 1):
        ws.cell(row=r0 + i, column=1, value=f"{i}. {f}").alignment = Alignment(wrap_text=False)
    r1 = r0 + len(report["key_findings"]) + 2
    ws.cell(row=r1, column=1, value="Recommended investigations").font = Font(bold=True, size=12, color=NAVY)
    for i, f in enumerate(report["recommended_investigations"], 1):
        ws.cell(row=r1 + i, column=1, value=f"{i}. {f}")
    r2 = r1 + len(report["recommended_investigations"]) + 2
    ws.cell(row=r2, column=1, value="Method notes").font = Font(bold=True, size=12, color=NAVY)
    for i, n in enumerate(report["notes"], 1):
        ws.cell(row=r2 + i, column=1, value=n).font = SUB_FONT
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 10

    # ---------------------------------------------------------- Daily Energy
    ws_d = wb.create_sheet("Daily Energy")
    _title(ws_d, f"Daily energy - {report['month']}", disc)
    d = report["daily_energy"]
    rows = [[x["date"], x["energy_mwh"], x["avg_wind_speed_ms"], x["availability_pct"], x["capacity_factor_pct"]]
            for x in d]
    f_d, l_d = _table(ws_d, 4, ["Date", "Energy (MWh)", "Avg wind (m/s)", "Availability (%)", "Capacity factor (%)"],
                      rows, {2: "#,##0.0", 3: "0.00", 4: "0.00", 5: "0.0"})
    ws_d.cell(row=l_d + 1, column=1, value="Total").font = Font(bold=True)
    ws_d.cell(row=l_d + 1, column=2, value=f"=SUM(B{f_d}:B{l_d})").number_format = "#,##0.0"
    lc = LineChart()
    lc.title, lc.y_axis.title, lc.height, lc.width = "Daily energy (MWh)", "MWh", 7.5, 18
    lc.add_data(Reference(ws_d, min_col=2, min_row=4, max_row=l_d), titles_from_data=True)
    lc.set_categories(Reference(ws_d, min_col=1, min_row=f_d, max_row=l_d))
    ws_d.add_chart(lc, "G4")

    # ---------------------------------------------------------- Monthly Energy
    ws_m = wb.create_sheet("Monthly Energy")
    _title(ws_m, "Monthly energy - all months in database", disc)
    m = report["monthly_energy"]
    rows = [[x["month"], x["energy_mwh"], x["avg_wind_speed_ms"], x["availability_pct"], x["capacity_factor_pct"],
             x["performance_deviation_pct"]] for x in m]
    f_m, l_m = _table(ws_m, 4, ["Month", "Energy (MWh)", "Avg wind (m/s)", "Availability (%)",
                                "Capacity factor (%)", "Perf. deviation (%)"], rows,
                      {2: "#,##0.0", 3: "0.00", 4: "0.00", 5: "0.0", 6: "+0.00;-0.00"})
    bc = BarChart()
    bc.title, bc.y_axis.title, bc.height, bc.width = "Monthly energy (MWh)", "MWh", 7.5, 16
    bc.add_data(Reference(ws_m, min_col=2, min_row=4, max_row=l_m), titles_from_data=True)
    bc.set_categories(Reference(ws_m, min_col=1, min_row=f_m, max_row=l_m))
    bc.legend = None
    ws_m.add_chart(bc, "H4")

    # ---------------------------------------------------------- Availability
    ws_a = wb.create_sheet("Availability")
    _title(ws_a, f"Availability - {report['month']}", disc)
    rows = [[t["turbine_id"], t["availability_pct"], _n(t["planned_downtime_hours"]), _n(t["unplanned_downtime_hours"]),
             _n(t["external_downtime_hours"]), _n(t["environmental_stop_hours"])] for t in tp]
    f_a, l_a = _table(ws_a, 4, ["Turbine", "Availability (%)", "Planned maint. (h)", "Unplanned fault (h)",
                                "External/grid (h)", "High-wind stops (h)"], rows,
                      {2: "0.00", 3: "0.0", 4: "0.0", 5: "0.0", 6: "0.0"})
    ws_a.cell(row=l_a + 2, column=1, value="Definition: available time / eligible time x 100. Planned "
              "maintenance and faults are unavailable; grid events and data gaps are excluded; high-wind stops "
              "count as available.").font = SUB_FONT
    ac = BarChart()
    ac.title, ac.y_axis.title, ac.height, ac.width = "Availability by turbine (%)", "%", 7.5, 16
    ac.add_data(Reference(ws_a, min_col=2, min_row=4, max_row=l_a), titles_from_data=True)
    ac.set_categories(Reference(ws_a, min_col=1, min_row=f_a, max_row=l_a))
    ac.y_axis.scaling.min = 85
    ac.y_axis.scaling.max = 100
    ac.legend = None
    ws_a.add_chart(ac, "H4")

    # ---------------------------------------------------------- Downtime
    ws_dt = wb.create_sheet("Downtime")
    _title(ws_dt, f"Downtime - {report['month']}", disc)
    dt = report["downtime"]
    rows = [[x["turbine_id"], _n(x["planned_downtime_hours"]), _n(x["unplanned_downtime_hours"]),
             _n(x["external_downtime_hours"]), None] for x in dt["by_turbine"]]
    for i, row in enumerate(rows):
        row[4] = f"=SUM(B{5 + i}:D{5 + i})"
    f_t, l_t = _table(ws_dt, 4, ["Turbine", "Planned (h)", "Unplanned (h)", "External (h)", "Total (h)"], rows,
                      {2: "0.0", 3: "0.0", 4: "0.0", 5: "0.0"})
    sc = BarChart()
    sc.type, sc.grouping, sc.overlap = "col", "stacked", 100
    sc.title, sc.y_axis.title, sc.height, sc.width = "Downtime by turbine (h)", "hours", 7.5, 16
    sc.add_data(Reference(ws_dt, min_col=2, max_col=4, min_row=4, max_row=l_t), titles_from_data=True)
    sc.set_categories(Reference(ws_dt, min_col=1, min_row=f_t, max_row=l_t))
    ws_dt.add_chart(sc, "H4")
    r = l_t + 3
    ws_dt.cell(row=r, column=1, value="Service events overlapping the month").font = Font(bold=True, color=NAVY)
    ev_rows = [[e["event_id"], e["turbine_id"], e["start_time"], e["end_time"], e["duration_hours"], e["event_type"],
                e["fault_code"], e["description"]] for e in dt["service_events"]]
    _table(ws_dt, r + 1, ["Event", "Turbine", "Start", "End", "Duration (h)", "Type", "Code", "Description"],
           ev_rows, {5: "0.0"})
    ws_dt.freeze_panes = "A5"

    # ---------------------------------------------------------- Anomalies
    ws_an = wb.create_sheet("Anomalies")
    _title(ws_an, f"Anomalies - {report['month']} (alerts for investigation, not diagnoses)", disc)
    rows = [[a["anomaly_id"], a["turbine_id"], a["timestamp"], a["anomaly_type"], a["severity"], a["measured_value"],
             a["unit"], a["expected_range"], a["explanation"], a["recommended_investigation"], a["status"]]
            for a in report["anomalies"]["items"]]
    _table(ws_an, 4, ["ID", "Turbine", "Start", "Type", "Severity", "Measured", "Unit", "Expected range",
                      "Explanation", "Recommended investigation", "Status"], rows, {6: "0.00"})
    sev_fill = {"High": "FECACA", "Medium": "FEF3C7", "Low": "DCFCE7"}
    for i, a in enumerate(report["anomalies"]["items"], 5):
        ws_an.cell(row=i, column=5).fill = PatternFill("solid", fgColor=sev_fill.get(a["severity"], "FFFFFF"))

    # ---------------------------------------------------------- Data Quality
    ws_q = wb.create_sheet("Data Quality")
    _title(ws_q, f"Data quality - {report['month']}", disc)
    q = report["data_quality"]
    rows = [["Valid 10-min records", q["valid_records"], "count"],
            ["Records valid for analysis", q["analysis_records"], "count"],
            ["Records with validation flags", q["flagged_records"], "count"],
            ["Missing data (no record)", q["missing_data_hours"], "h"],
            ["Data coverage (valid power data / recorded time)", q["data_coverage_pct"], "%"],
            ["Quarantined rows (all imports)", q["quarantined_rows_all_imports"], "count"]]
    _table(ws_q, 4, ["Metric", "Value", "Unit"], rows, {2: "#,##0.00"})
    ws_q.cell(row=12, column=1, value="Flagged rows are retained with reasons; analytics exclude only the "
              "affected measurements.").font = SUB_FONT

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
