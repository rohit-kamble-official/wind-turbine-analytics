import { Activity, AlertTriangle, Clock, Gauge, Percent, Wind, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { AvailabilityChart, DailyEnergyChart, DowntimePieChart, MonthlyEnergyChart, PowerCurveChart } from "../charts/Charts";
import { KpiCard } from "../components/KpiCard";
import { AnomalyTable, TurbineStatusTable } from "../components/Tables";
import { Async, Card, fmt } from "../components/ui";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export function KpiRow() {
  const { params } = useFilters();
  const s = useApi((sig) => api.summary(params, sig), [params]);
  const k = s.data;
  const L = s.loading && !k;
  if (s.error) return <Card><p className="text-sm text-rose-700">KPIs unavailable: {s.error}</p></Card>;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      <KpiCard label="Total energy" value={fmt.num(k?.energy_mwh, 0)} unit="MWh" icon={<Zap className="h-4 w-4" />} loading={L}
        hint={k?.data_coverage_pct != null ? `${fmt.num(k.data_coverage_pct, 1)}% data coverage` : undefined} />
      <KpiCard label="Avg wind speed" value={fmt.num(k?.avg_wind_speed_ms, 2)} unit="m/s" icon={<Wind className="h-4 w-4" />} loading={L} />
      <KpiCard label="Availability" value={fmt.num(k?.availability_pct, 2)} unit="%" icon={<Gauge className="h-4 w-4" />} loading={L}
        hint={<span title={k?.availability_definition}>Time-based, technical</span>} />
      <KpiCard label="Capacity factor" value={fmt.num(k?.capacity_factor_pct, 1)} unit="%" icon={<Percent className="h-4 w-4" />} loading={L}
        hint={k?.performance_deviation_pct != null ? `${fmt.signed(k.performance_deviation_pct)}% vs reference curve` : undefined} />
      <KpiCard label="Active turbines" value={k ? `${k.active_turbines}` : "–"} unit={k ? `/ ${k.total_turbines}` : ""} icon={<Activity className="h-4 w-4" />} loading={L}
        hint="Generated in period" />
      <KpiCard label="Total downtime" value={fmt.num(k?.downtime_hours, 0)} unit="h" icon={<Clock className="h-4 w-4" />} loading={L}
        hint={k ? `${fmt.num(k.unplanned_downtime_hours, 0)} h unplanned` : undefined} />
      <KpiCard label="Anomalies" value={k ? `${k.anomaly_count}` : "–"} icon={<AlertTriangle className="h-4 w-4" />} loading={L}
        hint="Alerts for investigation" />
    </div>
  );
}

export default function Overview() {
  const { params } = useFilters();
  const daily = useApi((s) => api.daily(params, false, s), [params]);
  const monthly = useApi((s) => api.monthly(params, s), [params]);
  const avail = useApi((s) => api.availability(params, "technical", s), [params]);
  const downtime = useApi((s) => api.downtime(params, s), [params]);
  const pc = useApi((s) => api.powerCurve(params, 0.5, 1200, s), [params]);
  const status = useApi((s) => api.turbineStatus(params, s), [params]);
  const anomalies = useApi((s) => api.anomalies({ ...params, page_size: 6 }, s), [params]);

  return (
    <div className="space-y-5">
      <KpiRow />
      <div className="grid gap-5 xl:grid-cols-3">
        <Card title="Daily energy production" subtitle="Measured vs expected (reference curve while running), MWh/day" className="xl:col-span-2">
          <Async state={daily} isEmpty={(d) => d.length === 0}>{(d) => <DailyEnergyChart data={d} />}</Async>
        </Card>
        <Card title="Downtime distribution" subtitle="Hours by category (high-wind stops excluded)">
          <Async state={downtime}>{(d) => <DowntimePieChart data={d} />}</Async>
        </Card>
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="Wind speed vs power output" subtitle={pc.data ? `${pc.data.records_used.toLocaleString()} valid running records · sample plotted` : "Valid running records"}>
          <Async state={pc} height={340} isEmpty={(d) => d.records_used === 0}>{(d) => <PowerCurveChart data={d} />}</Async>
        </Card>
        <Card title="Turbine availability" subtitle={avail.data ? `Fleet ${fmt.num(avail.data.fleet_availability_pct, 2)}% · bars below the 97% reference are highlighted` : "Time-based"}>
          <Async state={avail} isEmpty={(d) => d.turbines.length === 0}>{(d) => <AvailabilityChart data={d.turbines} />}</Async>
        </Card>
      </div>
      <Card title="Monthly energy production" subtitle="MWh per calendar month (partial months reflect the selected range)">
        <Async state={monthly} isEmpty={(d) => d.length === 0}>{(d) => <MonthlyEnergyChart data={d} />}</Async>
      </Card>
      <Card title="Turbine status" subtitle="Latest reading at the end of the selected range; KPIs for the whole range"
        actions={<Link to="/turbines" className="text-xs font-medium text-brand-600 hover:underline">Open monitoring →</Link>}>
        <Async state={status} height={200} isEmpty={(d) => d.length === 0}>{(d) => <TurbineStatusTable rows={d} />}</Async>
      </Card>
      <Card title="Recent anomalies" subtitle="Alerts for investigation — not proof of equipment failure"
        actions={<Link to="/anomalies" className="text-xs font-medium text-brand-600 hover:underline">View all →</Link>}>
        <Async state={anomalies} height={160} isEmpty={(d) => d.items.length === 0}>{(d) => <AnomalyTable rows={d.items} compact />}</Async>
      </Card>
    </div>
  );
}
