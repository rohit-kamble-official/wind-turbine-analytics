import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Activity, BarChart3, Calendar, ChevronDown, Database, Download, FileText, Gauge, LayoutDashboard, LineChart, Menu,
  ShieldAlert, Wind, Wrench, X,
} from "lucide-react";
import { useFilters } from "../context/FilterContext";
import { downloadUrls } from "../services/api";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/turbines", label: "Turbine Monitoring", icon: Gauge },
  { to: "/performance", label: "Performance Analytics", icon: BarChart3 },
  { to: "/power-curve", label: "Power Curve Analysis", icon: LineChart },
  { to: "/anomalies", label: "Anomaly Detection", icon: ShieldAlert },
  { to: "/downtime", label: "Service & Downtime", icon: Wrench },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/data", label: "Data Management", icon: Database },
];

function addDays(d: string, n: number) {
  if (!d) return "";
  const x = new Date(`${d}T00:00:00Z`);
  if (Number.isNaN(x.getTime())) return "";
  x.setUTCDate(x.getUTCDate() + n);
  return x.toISOString().slice(0, 10);
}

function DateRange() {
  const { startDate, endDate, minDate, maxDate, setRange } = useFilters();
  const presets = [
    { label: "7D", fn: () => setRange(addDays(maxDate, -6), maxDate) },
    { label: "30D", fn: () => setRange(addDays(maxDate, -29), maxDate) },
    { label: "90D", fn: () => setRange(addDays(maxDate, -89) < minDate ? minDate : addDays(maxDate, -89), maxDate) },
    { label: "All", fn: () => setRange(minDate, maxDate) },
  ];
  const isActive = (p: string) =>
    Boolean(maxDate) && endDate === maxDate && (p === "All" ? startDate === minDate
      : startDate === (p === "7D" ? addDays(maxDate, -6) : p === "30D" ? addDays(maxDate, -29) : addDays(maxDate, -89)));
  const input = "rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm text-navy-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Calendar className="h-4 w-4 text-slate-400" aria-hidden />
      <input type="date" aria-label="Start date" className={input} value={startDate} min={minDate} max={endDate || maxDate}
        onChange={(e) => e.target.value && setRange(e.target.value, endDate)} />
      <span className="text-slate-400">–</span>
      <input type="date" aria-label="End date" className={input} value={endDate} min={startDate || minDate} max={maxDate}
        onChange={(e) => e.target.value && setRange(startDate, e.target.value)} />
      <div className="flex overflow-hidden rounded-md border border-slate-200">
        {presets.map((p) => (
          <button key={p.label} onClick={p.fn}
            className={`px-2 py-1.5 text-xs font-medium ${isActive(p.label) ? "bg-navy-900 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ExportMenu() {
  const { params } = useFilters();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const items = [
    { label: "Daily metrics (CSV)", href: downloadUrls.csv("daily", params) },
    { label: "Turbine summary (CSV)", href: downloadUrls.csv("turbine_summary", params) },
    { label: "Monthly metrics (CSV)", href: downloadUrls.csv("monthly", params) },
    { label: "Anomalies (CSV)", href: downloadUrls.csv("anomalies", params) },
    { label: "Latest monthly report (Excel)", href: downloadUrls.excel() },
    { label: "Latest monthly report (PDF)", href: downloadUrls.pdf() },
  ];
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-brand-700">
        <Download className="h-4 w-4" /> Export <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-1 w-64 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          <p className="px-3 py-1.5 text-[11px] text-slate-500">CSV exports use the current date & turbine filters</p>
          {items.map((i) => (
            <a key={i.label} href={i.href} onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-navy-900 hover:bg-slate-50">
              {i.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function DataStatus() {
  const { health, healthError } = useFilters();
  let cls = "bg-slate-100 text-slate-600", text = "Connecting…";
  if (healthError) { cls = "bg-rose-50 text-rose-700"; text = "API offline"; }
  else if (health?.last_import_status === "recomputing") { cls = "bg-amber-50 text-amber-800"; text = "Recomputing…"; }
  else if (health?.status === "ok") { cls = "bg-emerald-50 text-emerald-800"; text = `${health.scada_records.toLocaleString()} readings`; }
  else if (health) { cls = "bg-amber-50 text-amber-800"; text = "No data loaded"; }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}
      title={healthError ?? `Data ${health?.data_start} to ${health?.data_end} (simulated)`}>
      <Activity className="h-3.5 w-3.5" /> {text}
    </span>
  );
}

export default function DashboardLayout() {
  const { turbineId, setTurbineId, turbines, healthError } = useFilters();
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="flex h-full">
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-navy-900 text-slate-200 transition-transform lg:static lg:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="rounded-lg bg-brand-500/15 p-2"><Wind className="h-5 w-5 text-brand-500" /></div>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-white">Turbine Performance</div>
            <div className="text-[11px] text-slate-400">Monitoring & Analytics</div>
          </div>
          <button className="ml-auto lg:hidden" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X className="h-5 w-5" /></button>
        </div>
        <nav className="mt-2 space-y-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${isActive ? "bg-white/10 font-medium text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}>
              {({ isActive }) => (<><Icon className={`h-4 w-4 ${isActive ? "text-brand-500" : ""}`} />{label}</>)}
            </NavLink>
          ))}
        </nav>
        <div className="absolute inset-x-0 bottom-0 border-t border-white/10 px-5 py-4 text-[11px] leading-relaxed text-slate-400">
          <span className="font-semibold text-amber-300">Simulated data.</span> Portfolio project – not real operational
          data and not an official product of any turbine manufacturer.
        </div>
      </aside>
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setMobileOpen(false)} />}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 lg:px-6">
            <button className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
            <h1 className="mr-auto text-[15px] font-semibold text-navy-900">Wind Turbine Performance Monitoring & Analytics</h1>
            <DateRange />
            <label className="flex items-center gap-2 text-xs text-slate-500">
              <span>Turbine</span>
              <select value={turbineId} onChange={(e) => setTurbineId(e.target.value)}
                className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm text-navy-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100">
                <option value="">All turbines</option>
                {turbines.map((t) => <option key={t.turbine_id} value={t.turbine_id}>{t.turbine_id}</option>)}
              </select>
            </label>
            <DataStatus />
            <ExportMenu />
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-4 py-5 lg:px-6">
          {healthError ? (
            <div className="mx-auto mt-16 max-w-lg rounded-xl border border-rose-200 bg-white p-6 text-center">
              <h2 className="font-semibold text-rose-700">Cannot reach the backend API</h2>
              <p className="mt-2 text-sm text-slate-600">{healthError}</p>
              <p className="mt-3 text-sm text-slate-500">Start it from <code>backend/</code> with
                <code className="mx-1 rounded bg-slate-100 px-1">uvicorn app.main:app --port 8000</code>.</p>
            </div>
          ) : <Outlet />}
        </main>
      </div>
    </div>
  );
}
