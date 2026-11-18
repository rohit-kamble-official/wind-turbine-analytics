import { useEffect, useState } from "react";
import { DailyEnergyChart, TemperatureChart } from "../charts/Charts";
import { TurbineStatusTable } from "../components/Tables";
import { Async, Card, DeviationValue, fmt, PageHeader, StatusBadge } from "../components/ui";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function TurbineMonitoring() {
  const { params, turbineId, setTurbineId } = useFilters();
  const status = useApi((s) => api.turbineStatus(params, s), [params]);
  const [selected, setSelected] = useState(turbineId || "WTG01");
  useEffect(() => { if (turbineId) setSelected(turbineId); }, [turbineId]);
  const detailParams = { ...params, turbine_id: selected };
  const temps = useApi((s) => api.temperature(detailParams, s), [params, selected]);
  const daily = useApi((s) => api.daily(detailParams, false, s), [params, selected]);
  const row = status.data?.find((r) => r.turbine_id === selected);

  return (
    <div className="space-y-5">
      <PageHeader title="Turbine Monitoring"
        description="Operating state and KPIs per turbine. Click a row to inspect its temperature and production trends; use the top Turbine selector to filter the whole dashboard." />
      <Card title="Turbine status table" subtitle="Status = latest reading at the end of the selected range">
        <Async state={status} height={200} isEmpty={(d) => d.length === 0}>
          {(d) => <TurbineStatusTable rows={d} selected={selected} onSelect={setSelected} />}
        </Async>
      </Card>
      {row && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {[
            ["Turbine", <span className="flex items-center gap-2">{row.turbine_id}{turbineId !== row.turbine_id && (
              <button onClick={() => setTurbineId(row.turbine_id)} className="text-[11px] font-normal text-brand-600 hover:underline">filter dashboard</button>)}</span>],
            ["Status", row.latest ? <StatusBadge status={row.latest.operating_status} code={row.latest.fault_code} /> : "–"],
            ["Energy", `${fmt.num(row.energy_mwh, 1)} MWh`],
            ["Availability", `${fmt.num(row.availability_pct, 2)} %`],
            ["Downtime", `${fmt.num(row.downtime_hours, 1)} h`],
            ["Deviation", <DeviationValue v={row.performance_deviation_pct} />],
          ].map(([label, value], i) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
              <div className="mt-1 text-[15px] font-semibold text-navy-900">{value}</div>
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-2">
        <Card title={`Temperature trends – ${selected}`} subtitle="Daily averages (°C); gearbox daily maximum dashed. Invalid sensor values excluded.">
          <Async state={temps} isEmpty={(d) => d.length === 0}>{(d) => <TemperatureChart data={d} />}</Async>
        </Card>
        <Card title={`Daily energy – ${selected}`} subtitle="Measured vs expected while running (MWh/day)">
          <Async state={daily} isEmpty={(d) => d.length === 0}>{(d) => <DailyEnergyChart data={d} />}</Async>
        </Card>
      </div>
    </div>
  );
}
