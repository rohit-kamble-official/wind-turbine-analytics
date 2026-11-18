import type { ReactNode } from "react";

export function KpiCard({ label, value, unit, icon, hint, loading }: {
  label: string; value: string; unit?: string; icon: ReactNode; hint?: ReactNode; loading?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-medium uppercase leading-tight tracking-wide text-slate-500">{label}</span>
        <span className="rounded-lg bg-brand-50 p-1.5 text-brand-600">{icon}</span>
      </div>
      {loading ? (
        <div className="mt-3 h-7 w-24 animate-pulse rounded bg-slate-100" />
      ) : (
        <div className="mt-2 flex items-baseline gap-1">
          <span className="text-2xl font-semibold tabular-nums text-navy-900">{value}</span>
          {unit && <span className="text-sm text-slate-500">{unit}</span>}
        </div>
      )}
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}
