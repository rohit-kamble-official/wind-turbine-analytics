import { useEffect, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { Async, Card, fmt, PageHeader, Pager, Select, StatusBadge } from "../components/ui";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { UploadResponse } from "../services/types";

function UploadPanel() {
  const { refreshHealth, bumpData, health } = useFilters();
  const demo = Boolean(health?.demo_mode);
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [batchStatus, setBatchStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!result || result.batch.status !== "recomputing") return;
    const t = setInterval(async () => {
      const b = await api.importStatus(result.batch.id);
      setBatchStatus(`${b.status}${b.message ? ` – ${b.message}` : ""}`);
      if (b.status !== "recomputing") { clearInterval(t); refreshHealth(); bumpData(); }
    }, 2000);
    return () => clearInterval(t);
  }, [result, refreshHealth, bumpData]);

  const onUpload = async () => {
    const f = input.current?.files?.[0];
    if (!f) return setError("Choose a CSV file first.");
    setBusy(true); setError(null); setResult(null); setBatchStatus(null);
    try {
      const r = await api.upload(f);
      setResult(r);
      setBatchStatus(r.batch.status);
      refreshHealth();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  return (
    <Card title="Upload SCADA data" subtitle="CSV with the same 17 columns as data/generated/scada_data.csv">
      <div className="flex flex-wrap items-center gap-3">
        <input ref={input} type="file" accept=".csv" className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm" />
        <button onClick={onUpload} disabled={busy || demo}
          className="inline-flex items-center gap-1.5 rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
          <UploadCloud className="h-4 w-4" /> {busy ? "Validating…" : "Upload & validate"}
        </button>
      </div>
      {demo && <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-900">Uploads are disabled on this public demo (read-only simulated dataset). Clone the repository and run it locally to try the upload and recompute pipeline.</p>}
      <p className="mt-2 text-xs text-slate-500">Rows are validated (timestamps, duplicates, ranges, turbine IDs). Records already in the database are skipped; invalid rows are quarantined with reasons, never silently dropped. KPIs and anomalies are then recomputed in the background.</p>
      {error && <p className="mt-3 rounded-md bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p>}
      {result && (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-sm">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
            {Object.entries(result.validation).map(([k, v]) => (
              <div key={k}><div className="text-[11px] uppercase text-slate-500">{k.replace(/_/g, " ")}</div><div className="font-semibold tabular-nums">{v.toLocaleString()}</div></div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-600">Batch #{result.batch.id} · recompute: {batchStatus ?? result.recompute}</p>
        </div>
      )}
    </Card>
  );
}

export default function DataManagementPage() {
  const { params } = useFilters();
  const quality = useApi((s) => api.quality(s), []);
  const imports = useApi((s) => api.imports(s), []);
  const [page, setPage] = useState(1);
  const [opStatus, setOpStatus] = useState("");
  const [flagged, setFlagged] = useState(false);
  useEffect(() => setPage(1), [params, opStatus, flagged]);
  const scada = useApi((s) => api.scada({ ...params, page, page_size: 20, operating_status: opStatus || undefined, flagged_only: flagged }, s),
    [params, page, opStatus, flagged]);

  return (
    <div className="space-y-5">
      <PageHeader title="Data Management" description="Data quality, imports and raw 10-minute SCADA readings. All data in this system is simulated." />
      <div className="grid gap-5 xl:grid-cols-3">
        <Card title="Data quality report" subtitle="From the latest validation run" className="xl:col-span-2">
          <Async state={quality} height={200}>
            {(q) => (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {[["Quality score", `${fmt.num(q.data_quality_score_pct, 2)}%`], ["Rows received", q.total_rows.toLocaleString()],
                    ["Valid for analysis", q.valid_for_analysis.toLocaleString()], ["Quarantined", q.quarantined_rows.toLocaleString()],
                    ["Missing intervals", q.missing_intervals.toLocaleString()], ["Period", `${q.period_start} → ${q.period_end}`]].map(([l, v]) => (
                    <div key={l}><div className="text-[11px] uppercase tracking-wide text-slate-500">{l}</div><div className="font-semibold tabular-nums">{v}</div></div>
                  ))}
                </div>
                <table className="min-w-full text-sm">
                  <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                    <tr><th className="py-2 text-left">Validation flag</th><th className="py-2 text-right">Rows</th><th className="py-2 pl-4 text-left">Handling</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {Object.entries(q.flag_counts).map(([k, v]) => (
                      <tr key={k}><td className="py-1.5 font-mono text-xs">{k}</td><td className="py-1.5 text-right tabular-nums">{v.toLocaleString()}</td>
                        <td className="py-1.5 pl-4 text-xs text-slate-600">{q.flag_descriptions[k]}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Async>
        </Card>
        <Card title="Completeness by turbine">
          <Async state={quality} height={200}>
            {(q) => (
              <table className="min-w-full text-sm">
                <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                  <tr><th className="py-2 text-left">Turbine</th><th className="py-2 text-right">Complete</th><th className="py-2 text-right">Analysis-ready</th><th className="py-2 text-right">Gaps</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100 tabular-nums">
                  {q.per_turbine.map((t) => (
                    <tr key={t.turbine_id}><td className="py-1.5 font-medium">{t.turbine_id}</td><td className="py-1.5 text-right">{fmt.num(t.completeness_pct, 2)}%</td>
                      <td className="py-1.5 text-right">{fmt.num(t.analysis_ready_pct, 2)}%</td><td className="py-1.5 text-right">{t.missing_intervals}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </Async>
        </Card>
      </div>
      <UploadPanel />
      <Card title="Import history">
        <Async state={imports} height={100} isEmpty={(d) => d.length === 0}>
          {(d) => (
            <table className="min-w-full text-sm">
              <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                <tr>{["#", "Source", "Imported", "Received", "Inserted", "Already present", "Quarantined", "Flagged", "Status"].map((h) => <th key={h} className="py-2 text-left">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100 tabular-nums">
                {d.map((b) => (
                  <tr key={b.id}><td className="py-1.5">{b.id}</td><td className="py-1.5">{b.source}</td><td className="py-1.5">{fmt.dateTime(b.imported_at)}</td>
                    <td className="py-1.5">{b.rows_received.toLocaleString()}</td><td className="py-1.5">{b.rows_inserted.toLocaleString()}</td>
                    <td className="py-1.5">{b.rows_already_present.toLocaleString()}</td><td className="py-1.5">{b.rows_quarantined}</td>
                    <td className="py-1.5">{b.rows_flagged.toLocaleString()}</td><td className="py-1.5" title={b.message ?? ""}>{b.status}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Async>
      </Card>
      <Card title="SCADA readings" subtitle="10-minute records for the current filters (paginated server-side)"
        actions={<div className="flex items-center gap-3">
          <Select label="Status" value={opStatus} onChange={setOpStatus}>
            <option value="">All</option>{["Running", "Idle", "Fault", "Maintenance"].map((s) => <option key={s}>{s}</option>)}
          </Select>
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            <input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} className="accent-brand-600" /> Flagged only
          </label>
        </div>}>
        <Async state={scada} height={240} isEmpty={(d) => d.items.length === 0}>
          {(d) => (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                    <tr>{["Timestamp", "Turbine", "Wind m/s", "Power kW", "Expected kW", "Rotor rpm", "Pitch °", "Gearbox °C", "Status", "QC flags"].map((h) =>
                      <th key={h} className="whitespace-nowrap px-2 py-2 text-left">{h}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 tabular-nums">
                    {d.items.map((r) => (
                      <tr key={r.timestamp + r.turbine_id} className={r.is_valid_for_analysis ? "" : "bg-amber-50/50"}>
                        <td className="whitespace-nowrap px-2 py-1.5">{r.timestamp.replace("T", " ").slice(0, 16)}</td>
                        <td className="px-2 py-1.5 font-medium">{r.turbine_id}</td>
                        <td className="px-2 py-1.5">{fmt.num(r.wind_speed_ms, 2)}</td>
                        <td className="px-2 py-1.5">{fmt.num(r.active_power_kw, 0)}</td>
                        <td className="px-2 py-1.5">{fmt.num(r.theoretical_power_kw, 0)}</td>
                        <td className="px-2 py-1.5">{fmt.num(r.rotor_speed_rpm, 1)}</td>
                        <td className="px-2 py-1.5">{fmt.num(r.pitch_angle_deg, 1)}</td>
                        <td className="px-2 py-1.5">{fmt.num(r.gearbox_temperature_c, 1)}</td>
                        <td className="px-2 py-1.5"><StatusBadge status={r.operating_status} code={r.fault_code} /></td>
                        <td className="px-2 py-1.5 font-mono text-[11px] text-amber-800">{r.qc_flags}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager page={d.page} pages={d.pages} total={d.total} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </div>
  );
}
