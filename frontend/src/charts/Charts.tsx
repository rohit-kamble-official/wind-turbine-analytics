import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, LineChart, Pie, PieChart,
  ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import type {
  AvailabilityRow, DailyMetric, DowntimeResponse, MonthlyMetric, PowerCurveResponse, TemperaturePoint,
} from "../services/types";
import { axisProps, C, ChartTooltip, gridProps, shortDate } from "./theme";

const H = 280;

/** 1. Daily energy production (line) with expected energy for context. */
export function DailyEnergyChart({ data, showExpected = true }: { data: DailyMetric[]; showExpected?: boolean }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={28} {...axisProps} />
        <YAxis {...axisProps} width={48} domain={[0, "auto"]} allowDataOverflow label={{ value: "MWh", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 11 }} />
        <Tooltip content={<ChartTooltip unit="MWh" labelFormatter={(l) => new Date(String(l)).toDateString()} />}
          cursor={{ stroke: C.axis, strokeDasharray: "3 3" }} />
        {showExpected && <Legend verticalAlign="top" height={24} iconType="plainline" />}
        <Line isAnimationActive={false} type="monotone" dataKey="energy_mwh" name="Measured energy" stroke={C.brand} strokeWidth={2} dot={false}
          activeDot={{ r: 4, stroke: "#fff", strokeWidth: 2 }} />
        {showExpected && (
          <Line isAnimationActive={false} type="monotone" dataKey="expected_energy_mwh" name="Expected while running" stroke={C.reference}
            strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** 4. Monthly energy production (area). */
export function MonthlyEnergyChart({ data }: { data: MonthlyMetric[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="gEnergy" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.brand} stopOpacity={0.35} />
            <stop offset="100%" stopColor={C.brand} stopOpacity={0.03} />
          </linearGradient>
        </defs>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="month" {...axisProps} tickFormatter={(m) => new Date(`${m}-01`).toLocaleDateString("en-GB", { month: "short", year: "2-digit" })} />
        <YAxis {...axisProps} width={56} label={{ value: "MWh", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 11 }} />
        <Tooltip content={<ChartTooltip unit="MWh" />} cursor={{ stroke: C.axis, strokeDasharray: "3 3" }} />
        <Area isAnimationActive={false} type="monotone" dataKey="energy_mwh" name="Energy" stroke={C.brand} strokeWidth={2} fill="url(#gEnergy)"
          activeDot={{ r: 4, stroke: "#fff", strokeWidth: 2 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** 2 + 6. Wind speed vs power scatter with binned measured curve and reference curve. */
export function PowerCurveChart({ data, showScatter = true, height = 340 }: { data: PowerCurveResponse; showScatter?: boolean; height?: number }) {
  const ref = data.reference_curve.map((r) => ({ x: r.wind_speed_ms, ref: r.power_kw }));
  const bins = data.bins.map((b) => ({ x: b.avg_wind_speed_ms, measured: b.avg_power_kw }));
  const scatter = data.scatter.map((s) => ({ x: s.wind_speed_ms, y: s.active_power_kw }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart margin={{ top: 8, right: 16, bottom: 18, left: 4 }}>
        <CartesianGrid {...gridProps} vertical />
        <XAxis type="number" dataKey="x" domain={[0, 26]} ticks={[0, 3, 5, 10, 13, 15, 20, 25]} {...axisProps}
          label={{ value: "Wind speed (m/s)", position: "insideBottom", offset: -10, fill: "#64748b", fontSize: 11 }} />
        <YAxis type="number" domain={[0, 3300]} {...axisProps} width={52}
          label={{ value: "Power (kW)", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 11 }} />
        <Tooltip content={<ChartTooltip unit="kW" digits={0} labelFormatter={(l) => `${Number(l).toFixed(2)} m/s`} />} />
        <Legend verticalAlign="top" height={26} />
        {showScatter && (
          <Scatter name="10-min readings (sample)" data={scatter} dataKey="y" fill={C.s1} fillOpacity={0.18} shape="circle"
            isAnimationActive={false} legendType="circle" />
        )}
        <Line data={ref} dataKey="ref" name="Reference (theoretical)" stroke={C.reference} strokeWidth={2}
          strokeDasharray="5 4" dot={false} type="linear" isAnimationActive={false} />
        <Line data={bins} dataKey="measured" name="Measured (binned 0.5 m/s)" stroke={C.navy} strokeWidth={2}
          dot={{ r: 2.5, fill: C.navy }} type="linear" isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** 3. Turbine availability (bar). */
export function AvailabilityChart({ data, target = 97 }: { data: AvailabilityRow[]; target?: number }) {
  const min = Math.floor(Math.min(90, ...data.map((d) => d.availability_pct ?? 100)) - 1);
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap="25%">
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="turbine_id" {...axisProps} />
        <YAxis domain={[min, 100]} {...axisProps} width={40} tickFormatter={(v) => `${v}%`} />
        <Tooltip content={<ChartTooltip unit="%" digits={2} />} cursor={{ fill: "#f1f5f9" }} />
        <ReferenceLine y={target} stroke={C.navy} strokeDasharray="4 3"
          label={{ value: `${target}% reference`, position: "insideTopRight", fill: "#475569", fontSize: 10 }} />
        <Bar isAnimationActive={false} dataKey="availability_pct" name="Availability" radius={[4, 4, 0, 0]} maxBarSize={36}>
          {data.map((d) => <Cell key={d.turbine_id} fill={(d.availability_pct ?? 100) < target ? C.bad : C.brand} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 5. Turbine performance comparison (energy bars). */
export function TurbineComparisonChart({ data, dataKey, name, unit, highlightBelow }: {
  data: Record<string, unknown>[]; dataKey: string; name: string; unit: string; highlightBelow?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap="25%">
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="turbine_id" {...axisProps} />
        <YAxis {...axisProps} width={52} />
        <Tooltip content={<ChartTooltip unit={unit} digits={2} />} cursor={{ fill: "#f1f5f9" }} />
        {highlightBelow !== undefined && <ReferenceLine y={0} stroke={C.axis} />}
        <Bar isAnimationActive={false} dataKey={dataKey} name={name} radius={[4, 4, 0, 0]} maxBarSize={36}>
          {data.map((d, i) => (
            <Cell key={i} fill={highlightBelow !== undefined && Number(d[dataKey]) < highlightBelow ? C.bad : C.brand} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 7. Downtime distribution (donut) - categories, not ranked. */
export function DowntimePieChart({ data }: { data: DowntimeResponse }) {
  const parts = [
    { name: "Planned maintenance", value: data.planned_hours, color: C.s1 },
    { name: "Unplanned fault", value: data.unplanned_hours, color: C.s2 },
    { name: "External / grid", value: data.external_hours, color: C.s3 },
  ].filter((p) => p.value > 0);
  const total = parts.reduce((a, p) => a + p.value, 0);
  if (!total) return <div className="flex h-[280px] items-center justify-center text-sm text-slate-400">No downtime in the selected period.</div>;
  return (
    <div className="flex flex-col items-center gap-2 sm:flex-row">
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie data={parts} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="88%" paddingAngle={1.5}
            stroke="#fff" strokeWidth={2} isAnimationActive={false}>
            {parts.map((p) => <Cell key={p.name} fill={p.color} />)}
          </Pie>
          <Tooltip content={<ChartTooltip unit="h" />} />
        </PieChart>
      </ResponsiveContainer>
      <ul className="w-full space-y-2 text-sm sm:w-56">
        {parts.map((p) => (
          <li key={p.name} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />
            <span className="text-slate-600">{p.name}</span>
            <span className="ml-auto tabular-nums font-medium text-navy-900">{p.value.toFixed(1)} h</span>
            <span className="w-10 text-right tabular-nums text-xs text-slate-500">{((p.value / total) * 100).toFixed(0)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 8. Temperature trends (daily averages + gearbox daily max). */
export function TemperatureChart({ data }: { data: TemperaturePoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={28} {...axisProps} />
        <YAxis {...axisProps} width={40} tickFormatter={(v) => `${v}°`} />
        <Tooltip content={<ChartTooltip unit="°C" />} cursor={{ stroke: C.axis, strokeDasharray: "3 3" }} />
        <Legend verticalAlign="top" height={24} iconType="plainline" />
        <Line isAnimationActive={false} dataKey="max_gearbox_temp_c" name="Gearbox (daily max)" stroke={C.s1} strokeWidth={1.25} strokeDasharray="3 3" dot={false} />
        <Line isAnimationActive={false} dataKey="avg_gearbox_temp_c" name="Gearbox (avg)" stroke={C.s1} strokeWidth={2} dot={false} />
        <Line isAnimationActive={false} dataKey="avg_generator_temp_c" name="Generator (avg)" stroke={C.s2} strokeWidth={2} dot={false} />
        <Line isAnimationActive={false} dataKey="avg_nacelle_temp_c" name="Nacelle (avg)" stroke={C.s3} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Daily fleet performance deviation (line around zero). */
export function DeviationTrendChart({ data }: { data: DailyMetric[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={28} {...axisProps} />
        <YAxis {...axisProps} width={44} tickFormatter={(v) => `${v}%`} />
        <ReferenceLine y={0} stroke={C.axis} />
        <Tooltip content={<ChartTooltip unit="%" digits={2} />} cursor={{ stroke: C.axis, strokeDasharray: "3 3" }} />
        <Line isAnimationActive={false} dataKey="performance_deviation_pct" name="Deviation vs reference" stroke={C.navy} strokeWidth={2} dot={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Stacked downtime per turbine. */
export function DowntimeByTurbineChart({ data }: { data: DowntimeResponse["by_turbine"] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap="25%">
        <CartesianGrid {...gridProps} />
        <XAxis dataKey="turbine_id" {...axisProps} />
        <YAxis {...axisProps} width={44} label={{ value: "h", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 11 }} />
        <Tooltip content={<ChartTooltip unit="h" />} cursor={{ fill: "#f1f5f9" }} />
        <Legend verticalAlign="top" height={24} />
        <Bar isAnimationActive={false} dataKey="planned_hours" name="Planned" stackId="a" fill={C.s1} stroke="#fff" strokeWidth={1} maxBarSize={36} />
        <Bar isAnimationActive={false} dataKey="unplanned_hours" name="Unplanned" stackId="a" fill={C.s2} stroke="#fff" strokeWidth={1} maxBarSize={36} />
        <Bar isAnimationActive={false} dataKey="external_hours" name="External" stackId="a" fill={C.s3} stroke="#fff" strokeWidth={1} maxBarSize={36} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
