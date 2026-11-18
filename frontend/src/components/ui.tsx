import type { ReactNode } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, CircleDashed, Inbox, Loader2, PauseCircle, RefreshCw, Wrench, XOctagon } from "lucide-react";
import type { Severity } from "../services/types";

// ---------------------------------------------------------------- formatting
export const fmt = {
  num: (v: number | null | undefined, d = 1) =>
    v === null || v === undefined || Number.isNaN(v) ? "–" : v.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }),
  signed: (v: number | null | undefined, d = 2) =>
    v === null || v === undefined ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`,
  dateTime: (s: string | null | undefined) =>
    s ? new Date(s).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "–",
  date: (s: string) => new Date(s).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }),
};

// ---------------------------------------------------------------- layout
export function Card({ title, subtitle, actions, children, className = "" }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className}`}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-navy-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-navy-900">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-500">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

// ---------------------------------------------------------------- states
export function Loading({ height = 260, label = "Loading…" }: { height?: number; label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 text-sm text-slate-400" style={{ height }} role="status">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function Empty({ height = 260, message = "No data for the selected filters." }: { height?: number; message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 text-sm text-slate-400" style={{ height }}>
      <Inbox className="h-6 w-6" /> {message}
    </div>
  );
}

export function ErrorState({ message, onRetry, height = 260 }: { message: string; onRetry?: () => void; height?: number }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 text-center text-sm text-rose-700" style={{ height }} role="alert">
      <AlertCircle className="h-6 w-6" />
      <span className="max-w-md">Could not load data: {message}</span>
      {onRetry && (
        <button onClick={onRetry} className="mt-1 inline-flex items-center gap-1 rounded-md border border-rose-200 px-2.5 py-1 text-xs hover:bg-rose-50">
          <RefreshCw className="h-3 w-3" /> Retry
        </button>
      )}
    </div>
  );
}

/** Renders loading / error / empty states, else children(data). */
export function Async<T>({ state, height = 260, isEmpty, children }: {
  state: { data: T | null; loading: boolean; error: string | null; reload: () => void };
  height?: number; isEmpty?: (d: T) => boolean; children: (d: T) => ReactNode;
}) {
  if (state.loading && !state.data) return <Loading height={height} />;
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} height={height} />;
  if (!state.data || (isEmpty && isEmpty(state.data))) return <Empty height={height} />;
  return <div className={state.loading ? "opacity-60 transition-opacity" : "transition-opacity"}>{children(state.data)}</div>;
}

// ---------------------------------------------------------------- badges
const STATUS: Record<string, { cls: string; icon: ReactNode }> = {
  Running: { cls: "bg-emerald-50 text-emerald-800 ring-emerald-200", icon: <CheckCircle2 className="h-3.5 w-3.5" /> },
  Idle: { cls: "bg-slate-100 text-slate-700 ring-slate-200", icon: <PauseCircle className="h-3.5 w-3.5" /> },
  Fault: { cls: "bg-rose-50 text-rose-800 ring-rose-200", icon: <XOctagon className="h-3.5 w-3.5" /> },
  Maintenance: { cls: "bg-amber-50 text-amber-800 ring-amber-200", icon: <Wrench className="h-3.5 w-3.5" /> },
};

export function StatusBadge({ status, code }: { status: string; code?: string }) {
  const s = STATUS[status] ?? { cls: "bg-slate-100 text-slate-600 ring-slate-200", icon: <CircleDashed className="h-3.5 w-3.5" /> };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${s.cls}`}>
      {s.icon}
      {status}
      {code ? <span className="font-mono text-[10px] opacity-75">{code}</span> : null}
    </span>
  );
}

const SEV: Record<Severity, string> = {
  High: "bg-rose-50 text-rose-800 ring-rose-200",
  Medium: "bg-amber-50 text-amber-800 ring-amber-200",
  Low: "bg-sky-50 text-sky-800 ring-sky-200",
};

export function SeverityBadge({ severity }: { severity: Severity | null }) {
  if (!severity) return <span className="text-slate-400">–</span>;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${SEV[severity]}`}>
      <AlertTriangle className="h-3 w-3" /> {severity}
    </span>
  );
}

/** Coloured number for deviation: below -3 % red, below 0 amber, else green (text + sign, not colour alone). */
export function DeviationValue({ v }: { v: number | null }) {
  if (v === null || v === undefined) return <span className="text-slate-400">–</span>;
  const cls = v < -3 ? "text-rose-700" : v < 0 ? "text-amber-700" : "text-emerald-700";
  return <span className={`font-medium tabular-nums ${cls}`}>{fmt.signed(v)}%</span>;
}

export function Select({ value, onChange, children, label, className = "" }: {
  value: string; onChange: (v: string) => void; children: ReactNode; label: string; className?: string;
}) {
  return (
    <label className={`flex items-center gap-2 text-xs text-slate-500 ${className}`}>
      <span className="whitespace-nowrap">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm text-navy-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100">
        {children}
      </select>
    </label>
  );
}

export function Pager({ page, pages, total, onPage }: { page: number; pages: number; total: number; onPage: (p: number) => void }) {
  return (
    <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
      <span>{total.toLocaleString()} rows · page {page} of {pages}</span>
      <div className="flex gap-1">
        <button disabled={page <= 1} onClick={() => onPage(page - 1)} className="rounded border border-slate-200 px-2.5 py-1 disabled:opacity-40 hover:bg-slate-50">Previous</button>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)} className="rounded border border-slate-200 px-2.5 py-1 disabled:opacity-40 hover:bg-slate-50">Next</button>
      </div>
    </div>
  );
}
