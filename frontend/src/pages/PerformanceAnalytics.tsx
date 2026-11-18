import { useState } from "react";
import { DeviationTrendChart, TurbineComparisonChart } from "../charts/Charts";
import { Async, Card, DeviationValue, fmt, PageHeader, Select } from "../components/ui";
import { KpiRow } from "./Overview";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

const METRICS = {
  energy_mwh: { name: "Energy", unit: "MWh" },
  capacity_factor_pct: { name: "Capacity factor", unit: "%" },
  availability_pct: { name: "Availability", unit: "%" },
  performance_deviation_pct: { name: "Performance deviation", unit: "%" },
  downtime_hours: { name: "Downtime", unit: "h" },
} as const;
type MetricKey = keyof typeof METRICS;

export default function PerformanceAnalytics() {
  const { params } = useFilters();
  const [metric, setMetric] = useState<MetricKey>("energy_mwh");
  const status = useApi((s) => api.turbineStatus(params, s), [params]);
  const dev = useApi((s) => api.deviation(params, s), [params]);
  const cf = useApi((s) => api.capacityFactor(params, s), [params]);
  const m = METRICS[metric];

  return (
    <div className="space-y-5">
      <PageHeader title="Performance Analytics"
        description="Turbine-to-turbine comparison of energy, capacity factor and deviation from the reference power curve." />
      <KpiRow />
      <Card title="Turbine performance comparison" subtitle={`${m.name} (${m.unit}) for the selected period`}
        actions={<Select label="Metric" value={metric} onChange={(v) => setMetric(v as MetricKey)}>
          {Object.entries(METRICS).map(([k, v]) => <option key={k} value={k}>{v.name}</option>)}
        </Select>}>
        <Async state={status} isEmpty={(d) => d.length === 0}>
          {(d) => <TurbineComparisonChart data={d as unknown as Record<string, unknown>[]} dataKey={metric} name={m.name} unit={m.unit}
            highlightBelow={metric === "performance_deviation_pct" ? -3 : undefined} />}
        </Async>
      </Card>
      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="Daily performance deviation" subtitle={dev.data ? `Fleet ${fmt.signed(dev.data.fleet_deviation_pct)}% · ${dev.data.definition}` : ""}>
          <Async state={dev} isEmpty={(d) => d.daily.length === 0}>{(d) => <DeviationTrendChart data={d.daily} />}</Async>
        </Card>
        <Card title="Deviation by turbine" subtitle="Energy-weighted, relative to fleet in percentage points">
          <Async state={dev} isEmpty={(d) => d.turbines.length === 0}>
            {(d) => (
              <table className="min-w-full text-sm">
                <thead className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                  <tr><th className="py-2 text-left">Turbine</th><th className="py-2 text-right">Actual (MWh)</th>
                    <th className="py-2 text-right">Expected (MWh)</th><th className="py-2 text-right">Deviation</th><th className="py-2 text-right">vs fleet</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {d.turbines.map((t) => (
                    <tr key={t.turbine_id}>
                      <td className="py-2 font-medium">{t.turbine_id}</td>
                      <td className="py-2 text-right tabular-nums">{fmt.num(t.actual_energy_mwh, 1)}</td>
                      <td className="py-2 text-right tabular-nums">{fmt.num(t.expected_energy_mwh, 1)}</td>
                      <td className="py-2 text-right"><DeviationValue v={t.performance_deviation_pct} /></td>
                      <td className="py-2 text-right tabular-nums text-slate-600">{fmt.signed(t.relative_to_fleet_pp)} pp</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Async>
        </Card>
      </div>
      <Card title="Capacity factor" subtitle={cf.data ? `Energy / (rated ${cf.data.rated_power_kw.toLocaleString()} kW × valid-data hours) · fleet ${fmt.num(cf.data.fleet_capacity_factor_pct, 1)}%` : ""}>
        <Async state={cf} isEmpty={(d) => d.turbines.length === 0}>
          {(d) => <TurbineComparisonChart data={d.turbines as unknown as Record<string, unknown>[]} dataKey="capacity_factor_pct" name="Capacity factor" unit="%" />}
        </Async>
      </Card>
    </div>
  );
}
