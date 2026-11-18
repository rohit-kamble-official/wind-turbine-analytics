import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { AnomalyTable } from "../components/Tables";
import { Async, Card, fmt, PageHeader, Pager, Select, SeverityBadge } from "../components/ui";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api, downloadUrls } from "../services/api";
import type { Anomaly } from "../services/types";

export default function AnomalyPage() {
  const { params } = useFilters();
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Anomaly | null>(null);
  useEffect(() => setPage(1), [params, severity, type]);
  const state = useApi((s) => api.anomalies({ ...params, severity: severity || undefined, anomaly_type: type || undefined, page, page_size: 25 }, s),
    [params, severity, type, page]);
  const facets = state.data;

  return (
    <div className="space-y-5">
      <PageHeader title="Anomaly Detection"
        description="Statistical thresholds, rolling averages, robust z-scores and an Isolation Forest flag unusual behaviour. Each anomaly is an alert for investigation, not a diagnosis."
        actions={<a href={downloadUrls.csv("anomalies", params)} className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm hover:bg-slate-50">Export CSV</a>} />
      {facets && (
        <div className="grid grid-cols-3 gap-3 md:max-w-xl">
          {(["High", "Medium", "Low"] as const).map((s) => (
            <button key={s} onClick={() => setSeverity(severity === s ? "" : s)}
              className={`rounded-xl border bg-white px-4 py-3 text-left ${severity === s ? "border-navy-900 ring-1 ring-navy-900" : "border-slate-200"}`}>
              <SeverityBadge severity={s} />
              <div className="mt-1.5 text-2xl font-semibold tabular-nums">{facets.by_severity[s] ?? 0}</div>
            </button>
          ))}
        </div>
      )}
      <Card title="Anomaly log" subtitle="Newest first · click a row for details"
        actions={<div className="flex flex-wrap gap-3">
          <Select label="Severity" value={severity} onChange={setSeverity}>
            <option value="">All</option>{["High", "Medium", "Low"].map((s) => <option key={s}>{s}</option>)}
          </Select>
          <Select label="Type" value={type} onChange={setType}>
            <option value="">All types</option>
            {Object.entries(facets?.by_type ?? {}).map(([t, n]) => <option key={t} value={t}>{t} ({n})</option>)}
          </Select>
        </div>}>
        <Async state={state} height={240} isEmpty={(d) => d.items.length === 0}>
          {(d) => (<><AnomalyTable rows={d.items} onSelect={setSelected} /><Pager page={d.page} pages={d.pages} total={d.total} onPage={setPage} /></>)}
        </Async>
      </Card>

      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onClick={() => setSelected(null)}>
          <aside className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono text-xs text-slate-500">{selected.anomaly_id}</p>
                <h2 className="mt-1 text-lg font-semibold">{selected.anomaly_type}</h2>
              </div>
              <button onClick={() => setSelected(null)} aria-label="Close"><X className="h-5 w-5 text-slate-500" /></button>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-xs text-slate-500">Turbine</dt><dd className="font-medium">{selected.turbine_id}</dd></div>
              <div><dt className="text-xs text-slate-500">Severity</dt><dd><SeverityBadge severity={selected.severity} /></dd></div>
              <div><dt className="text-xs text-slate-500">Start</dt><dd>{fmt.dateTime(selected.timestamp)}</dd></div>
              <div><dt className="text-xs text-slate-500">Duration</dt><dd>{selected.duration_minutes >= 1440 ? `${(selected.duration_minutes / 1440).toFixed(0)} days` : `${selected.duration_minutes} min`}</dd></div>
              <div><dt className="text-xs text-slate-500">{selected.metric}</dt><dd className="font-medium">{fmt.num(selected.measured_value, 2)} {selected.unit}</dd></div>
              <div><dt className="text-xs text-slate-500">Expected range</dt><dd>{selected.expected_range}</dd></div>
            </dl>
            <h3 className="mt-5 text-sm font-semibold">Explanation</h3>
            <p className="mt-1 text-sm text-slate-600">{selected.explanation}</p>
            <h3 className="mt-4 text-sm font-semibold">Recommended investigation</h3>
            <p className="mt-1 text-sm text-slate-600">{selected.recommended_investigation}</p>
            <p className="mt-4 text-xs text-slate-500">Method: {selected.detection_method} · Status: {selected.status}</p>
            <p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">This alert indicates behaviour that differs from the expected pattern. It is not proof of an equipment failure – confirm with additional data before acting.</p>
          </aside>
        </div>
      )}
    </div>
  );
}
