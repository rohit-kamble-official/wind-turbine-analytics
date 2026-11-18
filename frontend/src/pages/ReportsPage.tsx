import { useEffect, useState } from "react";
import { FileSpreadsheet, FileText, Table2 } from "lucide-react";
import { Async, Card, DeviationValue, fmt, PageHeader, Select } from "../components/ui";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api, downloadUrls } from "../services/api";

export default function ReportsPage() {
  const { params } = useFilters();
  const months = useApi((s) => api.reportMonths(s), []);
  const [month, setMonth] = useState("");
  useEffect(() => { if (!month && months.data?.length) setMonth(months.data[months.data.length - 1].month); }, [months.data, month]);
  const report = useApi((s) => api.monthlyReport(month, s), [month], Boolean(month));
  const btn = "inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50";

  return (
    <div className="space-y-5">
      <PageHeader title="Reports" description="Automated monthly performance reports (Excel with formulas and charts, PDF) and Power BI-ready CSV datasets."
        actions={<Select label="Month" value={month} onChange={setMonth}>
          {(months.data ?? []).map((m) => <option key={m.month} value={m.month}>{m.month}</option>)}
        </Select>} />
      <Card title="Downloads">
        <div className="flex flex-wrap gap-3">
          <a className={btn} href={downloadUrls.excel(month)}><FileSpreadsheet className="h-4 w-4 text-emerald-700" /> Excel report ({month})</a>
          <a className={btn} href={downloadUrls.pdf(month)}><FileText className="h-4 w-4 text-rose-700" /> PDF report ({month})</a>
          <a className={btn} href={downloadUrls.csv("daily", params)}><Table2 className="h-4 w-4 text-slate-600" /> Daily metrics CSV (current filters)</a>
          <a className={btn} href={downloadUrls.csv("turbine_summary", params)}><Table2 className="h-4 w-4 text-slate-600" /> Turbine summary CSV</a>
          <a className={btn} href={downloadUrls.csv("monthly", params)}><Table2 className="h-4 w-4 text-slate-600" /> Monthly CSV</a>
        </div>
        <p className="mt-3 text-xs text-slate-500">Full Power BI star-schema exports (Fact_SCADA, Dim_Turbine, Dim_Date, …) are produced by <code className="rounded bg-slate-100 px-1">python scripts/export_powerbi.py</code> into <code className="rounded bg-slate-100 px-1">powerbi/datasets/</code>.</p>
      </Card>
      <Async state={report} height={300}>
        {(r) => (
          <div className="space-y-5">
            <Card title={`Executive summary – ${r.month}`} subtitle={r.disclaimer}>
              <p className="text-sm leading-relaxed text-slate-700">{r.executive_summary}</p>
            </Card>
            <div className="grid gap-5 xl:grid-cols-2">
              <Card title="Key findings">
                <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-700">{r.key_findings.map((f, i) => <li key={i}>{f}</li>)}</ul>
              </Card>
              <Card title="Recommended investigations">
                <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-700">{r.recommended_investigations.map((f, i) => <li key={i}>{f}</li>)}</ol>
              </Card>
            </div>
            <Card title="Turbine performance" subtitle={`${r.period_start} to ${r.period_end}`}>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                    <tr>{["Turbine", "Energy (MWh)", "Wind (m/s)", "Availability", "CF", "Deviation", "Downtime (h)", "Anomalies"].map((h, i) =>
                      <th key={h} className={`py-2 ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 tabular-nums">
                    {r.turbine_performance.map((t) => (
                      <tr key={t.turbine_id}>
                        <td className="py-1.5 font-medium">{t.turbine_id}</td>
                        <td className="py-1.5 text-right">{fmt.num(t.energy_mwh, 1)}</td>
                        <td className="py-1.5 text-right">{fmt.num(t.avg_wind_speed_ms, 2)}</td>
                        <td className="py-1.5 text-right">{fmt.num(t.availability_pct, 2)}%</td>
                        <td className="py-1.5 text-right">{fmt.num(t.capacity_factor_pct, 1)}%</td>
                        <td className="py-1.5 text-right"><DeviationValue v={t.performance_deviation_pct} /></td>
                        <td className="py-1.5 text-right">{fmt.num(t.downtime_hours, 1)}</td>
                        <td className="py-1.5 text-right">{t.anomalies}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="mt-4 space-y-1 text-xs text-slate-500">{r.notes.map((n, i) => <li key={i}>• {n}</li>)}</ul>
            </Card>
          </div>
        )}
      </Async>
    </div>
  );
}
