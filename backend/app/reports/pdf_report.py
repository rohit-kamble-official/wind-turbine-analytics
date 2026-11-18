"""Monthly PDF report (ReportLab + Matplotlib charts)."""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,  # noqa: E402
                                Table, TableStyle)

from app.analytics.turbine_model import reference_curve_table  # noqa: E402

NAVY = colors.HexColor("#0B2545")
GREEN = colors.HexColor("#1B998B")
GREY = colors.HexColor("#64748B")
LIGHT = colors.HexColor("#F1F5F9")
MPL_NAVY, MPL_GREEN, MPL_GREY = "#0B2545", "#1B998B", "#94A3B8"

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=NAVY, fontSize=18, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=NAVY, fontSize=13, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=7.5, leading=10, textColor=GREY)
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=7.5, leading=9)


def _fig_to_image(fig, width_cm: float = 17) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * cm * ratio
    return img


def _style_axes(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(MPL_GREY)
    ax.spines["bottom"].set_color(MPL_GREY)
    ax.tick_params(colors="#334155", labelsize=8)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.6)
    ax.set_axisbelow(True)


def _table(data: list[list], col_widths: list[float] | None = None, zebra: bool = True) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1)
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]
    if zebra:
        for i in range(1, len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(st))
    return t


def _f(v, fmt="{:,.1f}", none="-"):
    return none if v is None else fmt.format(v)


def _footer(disclaimer: str, month: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(1.5 * cm, 1.0 * cm, disclaimer[:150])
        canvas.drawRightString(A4[0] - 1.5 * cm, 1.0 * cm, f"Monthly report {month} - page {doc.page}")
        canvas.setStrokeColor(GREEN)
        canvas.setLineWidth(2)
        canvas.line(1.5 * cm, A4[1] - 1.2 * cm, A4[0] - 1.5 * cm, A4[1] - 1.2 * cm)
        canvas.restoreState()
    return draw


def build_pdf_report(report: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title=f"Wind Farm Monthly Performance Report {report['month']}",
                            author="Wind Turbine Performance Analytics (portfolio project)")
    k = report["kpis"]
    tp = report["turbine_performance"]
    s = []

    s.append(Paragraph(f"Wind Farm Monthly Performance Report - {report['month']}", H1))
    s.append(Paragraph(f"Period {report['period_start']} to {report['period_end']} &middot; generated "
                       f"{report['generated_at']}", SMALL))
    s.append(Paragraph(f"<b>{report['disclaimer']}</b>", SMALL))
    s.append(Spacer(1, 8))

    # 1. Executive summary
    s.append(Paragraph("1. Executive summary", H2))
    s.append(Paragraph(report["executive_summary"], BODY))
    s.append(Spacer(1, 6))
    kpi = [["KPI", "Value"],
           ["2. Total energy production", f"{_f(k['energy_mwh'])} MWh"],
           ["3. Average wind speed", f"{_f(k['avg_wind_speed_ms'], '{:.2f}')} m/s"],
           ["4. Fleet availability (time-based)", f"{_f(k['availability_pct'], '{:.2f}')} %"],
           ["5. Capacity factor", f"{_f(k['capacity_factor_pct'])} %"],
           ["7. Performance deviation vs reference", f"{_f(k['performance_deviation_pct'], '{:+.2f}')} %"],
           ["8. Total downtime (planned / unplanned / external)",
            f"{_f(k['downtime_hours'])} h ({_f(k['planned_downtime_hours'])} / {_f(k['unplanned_downtime_hours'])}"
            f" / {_f(k['external_downtime_hours'])})"],
           ["9. Anomalies raised", str(k["anomaly_count"])],
           ["10. Data coverage", f"{_f(k['data_coverage_pct'], '{:.2f}')} %"]]
    s.append(_table(kpi, [10 * cm, 7 * cm]))

    # Daily energy chart
    d = report["daily_energy"]
    fig, ax = plt.subplots(figsize=(8, 2.6))
    ax.plot([x["date"][5:] for x in d], [x["energy_mwh"] for x in d], color=MPL_NAVY, linewidth=1.8)
    ax.fill_between(range(len(d)), [x["energy_mwh"] or 0 for x in d], color=MPL_GREEN, alpha=0.12)
    ax.set_ylabel("MWh / day", fontsize=8)
    ax.set_title("Daily energy production (farm)", fontsize=9, color=MPL_NAVY, loc="left")
    ax.set_xticks(range(0, len(d), max(1, len(d) // 10)))
    _style_axes(ax)
    s.append(Spacer(1, 6))
    s.append(_fig_to_image(fig))

    # 4/5. Turbine table
    s.append(PageBreak())
    s.append(Paragraph("Turbine performance (availability, capacity factor, deviation)", H2))
    rows = [["Turbine", "Energy\n(MWh)", "Wind\n(m/s)", "Avail.\n(%)", "CF\n(%)", "Dev.\n(%)", "Downtime\n(h)",
             "Anom."]]
    for t in tp:
        rows.append([t["turbine_id"], _f(t["energy_mwh"]), _f(t["avg_wind_speed_ms"], "{:.2f}"),
                     _f(t["availability_pct"], "{:.2f}"), _f(t["capacity_factor_pct"]),
                     _f(t["performance_deviation_pct"], "{:+.2f}"), _f(t["downtime_hours"]), str(t["anomalies"])])
    s.append(_table(rows))
    fig, axes = plt.subplots(1, 2, figsize=(8, 2.6))
    ids = [t["turbine_id"] for t in tp]
    axes[0].bar(ids, [t["availability_pct"] or 0 for t in tp], color=MPL_GREEN)
    axes[0].set_ylim(min(85, min((t["availability_pct"] or 100) for t in tp) - 2), 100.5)
    axes[0].set_title("Availability (%)", fontsize=9, color=MPL_NAVY, loc="left")
    devs = [t["performance_deviation_pct"] or 0 for t in tp]
    axes[1].bar(ids, devs, color=[MPL_GREEN if v >= -3 else "#E76F51" for v in devs])
    axes[1].axhline(0, color=MPL_GREY, linewidth=0.8)
    axes[1].set_title("Performance deviation (%)", fontsize=9, color=MPL_NAVY, loc="left")
    for ax in axes:
        _style_axes(ax)
        ax.tick_params(axis="x", rotation=60, labelsize=7)
    s.append(Spacer(1, 6))
    s.append(_fig_to_image(fig))

    # 6. Power curve
    s.append(Paragraph("6. Power curve analysis", H2))
    pc = report["power_curve"]
    ref = reference_curve_table(0.5)
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot([r["wind_speed_ms"] for r in ref], [r["power_kw"] for r in ref], color=MPL_GREY, linestyle="--",
            label="Reference (theoretical) curve")
    ax.plot([b["avg_wind_speed_ms"] for b in pc], [b["avg_power_kw"] for b in pc], color=MPL_NAVY, marker="o",
            markersize=3, linewidth=1.5, label="Measured (binned, 0.5 m/s)")
    ax.set_xlabel("Wind speed (m/s)", fontsize=8)
    ax.set_ylabel("Power (kW)", fontsize=8)
    ax.legend(fontsize=7, frameon=False)
    _style_axes(ax)
    s.append(_fig_to_image(fig, 15))
    s.append(Paragraph("Measured power is the mean 10-min active power of valid Running records per wind-speed "
                       "bin. Theoretical power is the reference curve of the simulated turbine model at the bin's "
                       "mean wind speed. Nacelle anemometer, no air-density correction.", SMALL))

    # 8. Downtime
    s.append(PageBreak())
    s.append(Paragraph("8. Downtime summary", H2))
    dt = report["downtime"]
    rows = [["Turbine", "Planned (h)", "Unplanned (h)", "External (h)", "Total (h)"]]
    for x in dt["by_turbine"]:
        rows.append([x["turbine_id"], _f(x["planned_downtime_hours"]), _f(x["unplanned_downtime_hours"]),
                     _f(x["external_downtime_hours"]), _f(x["downtime_hours"])])
    left = _table(rows)
    parts = [("Planned", k["planned_downtime_hours"] or 0), ("Unplanned", k["unplanned_downtime_hours"] or 0),
             ("External", k["external_downtime_hours"] or 0)]
    parts = [p for p in parts if p[1] > 0]
    if parts:
        fig, ax = plt.subplots(figsize=(3.2, 3.2))
        ax.pie([p[1] for p in parts], labels=[p[0] for p in parts], autopct="%1.0f%%",
               colors=[MPL_NAVY, "#E76F51", "#F4A261"][:len(parts)], textprops={"fontsize": 8},
               wedgeprops={"width": 0.45})
        ax.set_title("Downtime split", fontsize=9, color=MPL_NAVY)
        right = _fig_to_image(fig, 6.5)
        s.append(Table([[left, right]], colWidths=[10.5 * cm, 7 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    else:
        s.append(left)
    if dt["by_fault_code"]:
        s.append(Spacer(1, 6))
        s.append(Paragraph("Unplanned downtime by fault code (service events)", BODY))
        s.append(_table([["Fault code", "Hours"]] + [[x["fault_code"], _f(x["hours"])] for x in dt["by_fault_code"]],
                        [4 * cm, 3 * cm]))

    # 9. Anomalies
    s.append(Paragraph("9. Anomaly summary", H2))
    an = report["anomalies"]
    s.append(Paragraph(f"{an['total']} anomalies raised. By severity: "
                       + ", ".join(f"{k_} {v}" for k_, v in an["by_severity"].items())
                       + ". Anomalies are alerts for investigation, not evidence of equipment failure.", BODY))
    rows = [["Turbine", "Start", "Type", "Sev.", "Explanation"]]
    for a in an["items"][:20]:
        rows.append([a["turbine_id"], a["timestamp"][:16].replace("T", " "), Paragraph(a["anomaly_type"], CELL),
                     a["severity"], Paragraph(a["explanation"], CELL)])
    s.append(_table(rows, [1.6 * cm, 2.6 * cm, 3.4 * cm, 1.4 * cm, 9 * cm]))

    # 10. Data quality
    s.append(Paragraph("10. Data quality summary", H2))
    q = report["data_quality"]
    s.append(_table([["Metric", "Value"],
                     ["Valid 10-min records", f"{q['valid_records']:,}"],
                     ["Records valid for analysis", f"{q['analysis_records']:,}"],
                     ["Records with validation flags", f"{q['flagged_records']:,}"],
                     ["Missing data (h)", _f(q["missing_data_hours"])],
                     ["Data coverage (%)", _f(q["data_coverage_pct"], "{:.2f}")],
                     ["Quarantined rows (all imports)", f"{q['quarantined_rows_all_imports']:,}"]],
                    [10 * cm, 5 * cm]))

    # 11/12. Findings & recommendations
    block = [Paragraph("11. Key findings", H2)]
    block += [Paragraph(f"&bull; {f}", BODY) for f in report["key_findings"]]
    s.append(KeepTogether(block))
    s.append(Paragraph("12. Recommended investigations", H2))
    s += [Paragraph(f"{i}. {r}", BODY) for i, r in enumerate(report["recommended_investigations"], 1)]
    s.append(Spacer(1, 8))
    s.append(Paragraph("Method notes", H2))
    s += [Paragraph(f"&bull; {n}", SMALL) for n in report["notes"]]

    footer = _footer(report["disclaimer"], report["month"])
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    return out_path
