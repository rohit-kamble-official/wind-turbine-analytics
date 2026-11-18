import type { Anomaly, TurbineStatusRow } from "../services/types";
import { DeviationValue, fmt, SeverityBadge, StatusBadge } from "./ui";

const th = "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const td = "px-3 py-2.5 whitespace-nowrap";

export function TurbineStatusTable({ rows, onSelect, selected }: {
  rows: TurbineStatusRow[]; onSelect?: (id: string) => void; selected?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50/60">
          <tr>
            <th className={th}>Turbine</th>
            <th className={th}>Status (end of period)</th>
            <th className={`${th} text-right`}>Wind (m/s)</th>
            <th className={`${th} text-right`}>Active power (kW)</th>
            <th className={`${th} text-right`}>Availability</th>
            <th className={`${th} text-right`}>Capacity factor</th>
            <th className={`${th} text-right`}>Perf. deviation</th>
            <th className={th}>Latest alert</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.turbine_id} onClick={() => onSelect?.(r.turbine_id)}
              className={`${onSelect ? "cursor-pointer hover:bg-slate-50" : ""} ${selected === r.turbine_id ? "bg-brand-50/60" : ""}`}>
              <td className={`${td} font-medium text-navy-900`}>{r.turbine_id}</td>
              <td className={td}>{r.latest ? <StatusBadge status={r.latest.operating_status} code={r.latest.fault_code} /> : "–"}</td>
              <td className={`${td} text-right tabular-nums`}>{fmt.num(r.latest?.wind_speed_ms, 1)}</td>
              <td className={`${td} text-right tabular-nums`}>{fmt.num(r.latest?.active_power_kw, 0)}</td>
              <td className={`${td} text-right tabular-nums ${(r.availability_pct ?? 100) < 97 ? "font-medium text-rose-700" : ""}`}>
                {fmt.num(r.availability_pct, 2)}%
              </td>
              <td className={`${td} text-right tabular-nums`}>{fmt.num(r.capacity_factor_pct, 1)}%</td>
              <td className={`${td} text-right`}><DeviationValue v={r.performance_deviation_pct} /></td>
              <td className={td}>
                {r.latest_alert ? (
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={r.latest_alert_severity} />
                    <span className="max-w-[220px] truncate text-xs text-slate-600" title={r.latest_alert}>{r.latest_alert}</span>
                  </div>
                ) : <span className="text-xs text-slate-400">None in period</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AnomalyTable({ rows, compact = false, onSelect }: { rows: Anomaly[]; compact?: boolean; onSelect?: (a: Anomaly) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="border-b border-slate-200 bg-slate-50/60">
          <tr>
            <th className={th}>Turbine</th>
            <th className={th}>Detected</th>
            <th className={th}>Alert type</th>
            <th className={th}>Severity</th>
            {!compact && <th className={`${th} text-right`}>Measured</th>}
            {!compact && <th className={th}>Expected</th>}
            <th className={th}>Status</th>
            <th className={th}>Explanation</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((a) => (
            <tr key={a.anomaly_id} onClick={() => onSelect?.(a)} className={onSelect ? "cursor-pointer hover:bg-slate-50" : ""}>
              <td className={`${td} font-medium text-navy-900`}>{a.turbine_id}</td>
              <td className={`${td} tabular-nums text-slate-600`}>{fmt.dateTime(a.timestamp)}</td>
              <td className={td}>{a.anomaly_type}</td>
              <td className={td}><SeverityBadge severity={a.severity} /></td>
              {!compact && <td className={`${td} text-right tabular-nums`}>{fmt.num(a.measured_value, 1)} <span className="text-xs text-slate-500">{a.unit}</span></td>}
              {!compact && <td className={`${td} text-xs text-slate-500`}>{a.expected_range}</td>}
              <td className={td}><span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{a.status}</span></td>
              <td className="min-w-[280px] max-w-[420px] px-3 py-2.5 text-xs text-slate-600">
                <span className={compact ? "line-clamp-1" : "line-clamp-2"} title={a.explanation}>{a.explanation}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
