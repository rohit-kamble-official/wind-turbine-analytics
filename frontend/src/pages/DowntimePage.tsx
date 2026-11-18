import { DowntimeByTurbineChart, DowntimePieChart } from "../charts/Charts";
import { Async, Card, fmt, PageHeader } from "../components/ui";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function DowntimePage() {
  const { params } = useFilters();
  const dt = useApi((s) => api.downtime(params, s), [params]);
  const d = dt.data;
  const tiles: [string, number | undefined, string][] = [
    ["Total downtime", d?.total_downtime_hours, "Planned + unplanned + external"],
    ["Planned", d?.planned_hours, "Scheduled maintenance (PM-*)"],
    ["Unplanned", d?.unplanned_hours, "Turbine-side faults"],
    ["Fault-related", d?.fault_related_hours, "Unplanned + external"],
    ["High-wind stops", d?.environmental_stop_hours, "Not downtime – shown for context"],
    ["Missing data", d?.missing_data_hours, "SCADA gaps – excluded"],
  ];
  return (
    <div className="space-y-5">
      <PageHeader title="Service & Downtime" description="Downtime by category, turbine and fault code, plus the service event log for the selected period." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {tiles.map(([label, v, hint]) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-1 text-xl font-semibold tabular-nums">{dt.loading && !d ? "…" : `${fmt.num(v, 1)} h`}</div>
            <div className="text-[11px] text-slate-500">{hint}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-3">
        <Card title="Downtime by turbine" subtitle="Stacked hours" className="xl:col-span-2">
          <Async state={dt}>{(x) => <DowntimeByTurbineChart data={x.by_turbine} />}</Async>
        </Card>
        <Card title="Downtime distribution">
          <Async state={dt}>{(x) => <DowntimePieChart data={x} />}</Async>
        </Card>
      </div>
      <div className="grid gap-5 xl:grid-cols-3">
        <Card title="By fault / maintenance code" subtitle="From 10-min status data">
          <Async state={dt} isEmpty={(x) => x.by_fault_code.length === 0}>
            {(x) => (
              <table className="min-w-full text-sm">
                <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                  <tr><th className="py-2 text-left">Code</th><th className="py-2 text-left">Category</th><th className="py-2 text-right">Hours</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {x.by_fault_code.map((c) => (
                    <tr key={c.fault_code + c.category}><td className="py-1.5 font-mono text-xs">{c.fault_code}</td>
                      <td className="py-1.5 text-slate-600">{c.category.replace(/_/g, " ")}</td>
                      <td className="py-1.5 text-right tabular-nums">{fmt.num(c.hours, 1)}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </Async>
        </Card>
        <Card title="Service events" subtitle="Events overlapping the selected period" className="xl:col-span-2">
          <Async state={dt} isEmpty={(x) => x.events.length === 0}>
            {(x) => (
              <div className="max-h-[420px] overflow-auto">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 border-b border-slate-200 bg-white text-[11px] uppercase tracking-wide text-slate-500">
                    <tr><th className="py-2 text-left">Event</th><th className="py-2 text-left">Turbine</th><th className="py-2 text-left">Start</th>
                      <th className="py-2 text-right">Hours</th><th className="py-2 pl-3 text-left">Type</th><th className="py-2 text-left">Code</th><th className="py-2 text-left">Description</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {x.events.map((e) => (
                      <tr key={e.event_id}>
                        <td className="py-1.5 font-mono text-xs text-slate-500">{e.event_id}</td>
                        <td className="py-1.5 font-medium">{e.turbine_id}</td>
                        <td className="py-1.5 tabular-nums text-slate-600">{fmt.dateTime(e.start_time)}</td>
                        <td className="py-1.5 text-right tabular-nums">{fmt.num(e.duration_hours, 1)}</td>
                        <td className="py-1.5 pl-3"><span className={`rounded px-1.5 py-0.5 text-xs ${e.is_planned ? "bg-sky-50 text-sky-800" : e.event_type.startsWith("External") ? "bg-slate-100 text-slate-700" : "bg-orange-50 text-orange-800"}`}>{e.event_type}</span></td>
                        <td className="py-1.5 font-mono text-xs">{e.fault_code}</td>
                        <td className="py-1.5 text-xs text-slate-600">{e.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Async>
        </Card>
      </div>
    </div>
  );
}
