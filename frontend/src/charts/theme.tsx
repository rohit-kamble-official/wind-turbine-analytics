// Chart palette. Categorical slots validated (light surface) with the dataviz
// palette validator: blue/orange/aqua pass CVD + normal-vision separation; aqua
// is < 3:1 contrast so charts using it always carry a legend + tooltip/table.
export const C = {
  brand: "#0e9f6e",      // single-series measure (energy, availability)
  navy: "#0b2545",
  reference: "#94a3b8",  // theoretical / expected curves (dashed)
  s1: "#2a78d6",
  s2: "#eb6834",
  s3: "#1baf7a",
  grid: "#e2e8f0",
  axis: "#94a3b8",
  bad: "#c2410c",        // below-threshold bars (paired with sign + tooltip)
};

export const axisProps = {
  stroke: C.axis,
  tickLine: false,
  axisLine: { stroke: C.grid },
  tick: { fontSize: 11, fill: "#64748b" },
} as const;

export const gridProps = { stroke: C.grid, strokeDasharray: "0", vertical: false } as const;

export function ChartTooltip({ active, payload, label, unit, labelFormatter, digits = 1 }: {
  active?: boolean;
  payload?: { name?: string; value?: number | string; color?: string; dataKey?: string; payload?: Record<string, unknown> }[];
  label?: string | number;
  unit?: string | Record<string, string>;
  labelFormatter?: (l: string | number) => string;
  digits?: number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      {label !== undefined && <div className="mb-1 font-medium text-navy-900">{labelFormatter ? labelFormatter(label) : label}</div>}
      {payload.map((p, i) => {
        const u = typeof unit === "string" ? unit : unit?.[String(p.dataKey)] ?? "";
        const v = typeof p.value === "number" ? p.value.toLocaleString("en-GB", { maximumFractionDigits: digits }) : p.value;
        return (
          <div key={i} className="flex items-center gap-2 text-slate-600">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
            <span>{p.name}</span>
            <span className="ml-auto pl-3 font-medium tabular-nums text-navy-900">{v ?? "–"} {u}</span>
          </div>
        );
      })}
    </div>
  );
}

export const shortDate = (s: string | number) =>
  new Date(String(s)).toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
