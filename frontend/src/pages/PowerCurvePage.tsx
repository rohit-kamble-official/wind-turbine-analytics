import { useState } from "react";
import { PowerCurveChart } from "../charts/Charts";
import { Async, Card, fmt, PageHeader, Select } from "../components/ui";
import { useFilters } from "../context/FilterContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function PowerCurvePage() {
  const { params, turbineId } = useFilters();
  const [bin, setBin] = useState("0.5");
  const [scatter, setScatter] = useState(true);
  const pc = useApi((s) => api.powerCurve(params, Number(bin), scatter ? 2500 : 0, s), [params, bin, scatter]);

  return (
    <div className="space-y-5">
      <PageHeader title="Power Curve Analysis"
        description="Measured power (method of bins) compared with the theoretical reference curve of the simulated turbine model." />
      <Card title={`Power curve – ${turbineId || "all turbines"}`}
        subtitle={pc.data ? `${pc.data.records_used.toLocaleString()} valid Running 10-min records` : ""}
        actions={<div className="flex items-center gap-3">
          <Select label="Bin width" value={bin} onChange={setBin}>
            {["0.5", "1.0"].map((b) => <option key={b} value={b}>{b} m/s</option>)}
          </Select>
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            <input type="checkbox" checked={scatter} onChange={(e) => setScatter(e.target.checked)} className="accent-brand-600" /> Show readings
          </label>
        </div>}>
        <Async state={pc} height={420} isEmpty={(d) => d.records_used === 0}>{(d) => <PowerCurveChart data={d} showScatter={scatter} height={420} />}</Async>
      </Card>
      <div className="grid gap-5 xl:grid-cols-3">
        <Card title="Binned results" subtitle="Low-confidence bins (< 10 records) marked" className="xl:col-span-2">
          <Async state={pc} isEmpty={(d) => d.bins.length === 0}>
            {(d) => (
              <div className="max-h-[420px] overflow-auto">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 border-b border-slate-200 bg-white text-[11px] uppercase tracking-wide text-slate-500">
                    <tr><th className="py-2 text-left">Bin (m/s)</th><th className="py-2 text-right">Records</th><th className="py-2 text-right">Mean wind</th>
                      <th className="py-2 text-right">Measured (kW)</th><th className="py-2 text-right">Expected (kW)</th><th className="py-2 text-right">Deviation</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 tabular-nums">
                    {d.bins.map((b) => (
                      <tr key={b.bin_center_ms} className={b.low_confidence ? "text-slate-400" : ""}>
                        <td className="py-1.5">{b.bin_center_ms.toFixed(1)}{b.low_confidence && " *"}</td>
                        <td className="py-1.5 text-right">{b.count.toLocaleString()}</td>
                        <td className="py-1.5 text-right">{fmt.num(b.avg_wind_speed_ms, 2)}</td>
                        <td className="py-1.5 text-right">{fmt.num(b.avg_power_kw, 0)}</td>
                        <td className="py-1.5 text-right">{fmt.num(b.expected_power_kw, 0)}</td>
                        <td className={`py-1.5 text-right ${(b.deviation_pct ?? 0) < -3 ? "text-rose-700" : ""}`}>{b.deviation_pct == null ? "–" : `${fmt.signed(b.deviation_pct)}%`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Async>
        </Card>
        <Card title="Measured vs theoretical power">
          <div className="space-y-3 text-sm leading-relaxed text-slate-600">
            <p><b className="text-navy-900">Measured power</b> is the average 10-minute active power the turbine actually exported, grouped into wind-speed bins. Only valid records with status Running are used (faults, stops, flagged sensors are excluded).</p>
            <p><b className="text-navy-900">Theoretical (expected) power</b> is what the reference power curve predicts at the measured wind speed – the turbine's design capability under standard conditions.</p>
            <p>The gap between them is the <b className="text-navy-900">performance deviation</b>. A persistent negative gap at a turbine can point to issues worth investigating (e.g. pitch/yaw calibration, blade condition, derating), but the data alone does not prove a cause.</p>
            <p className="text-xs text-slate-500">{pc.data?.note}</p>
          </div>
        </Card>
      </div>
    </div>
  );
}
