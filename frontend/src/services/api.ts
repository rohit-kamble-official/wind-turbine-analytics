import type {
  AnomalyPage, AvailabilityResponse, CapacityFactorResponse, DailyMetric, DeviationResponse, DowntimeResponse,
  Health, ImportBatch, KpiSummary, MonthlyMetric, MonthlyReport, Page, PowerCurveResponse, QualityReport, ScadaRow,
  TemperaturePoint, Turbine, TurbineStatusRow, UploadResponse,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export interface FilterParams {
  start_date?: string;
  end_date?: string;
  turbine_id?: string;
}

type Params = Record<string, string | number | boolean | undefined | null>;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function buildUrl(path: string, params: Params = {}): string {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const qs = q.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function get<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const res = await fetch(buildUrl(path, params), { signal });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: (s?: AbortSignal) => get<Health>("/api/health", {}, s),
  turbines: (s?: AbortSignal) => get<Turbine[]>("/api/turbines", {}, s),
  turbineStatus: (f: FilterParams, s?: AbortSignal) => get<TurbineStatusRow[]>("/api/turbines/status", { ...f }, s),
  summary: (f: FilterParams, s?: AbortSignal) => get<KpiSummary>("/api/metrics/summary", { ...f }, s),
  daily: (f: FilterParams, byTurbine = false, s?: AbortSignal) =>
    get<DailyMetric[]>("/api/metrics/daily", { ...f, by_turbine: byTurbine }, s),
  monthly: (f: FilterParams, s?: AbortSignal) => get<MonthlyMetric[]>("/api/metrics/monthly", { ...f }, s),
  availability: (f: FilterParams, basis = "technical", s?: AbortSignal) =>
    get<AvailabilityResponse>("/api/metrics/availability", { ...f, basis }, s),
  capacityFactor: (f: FilterParams, s?: AbortSignal) => get<CapacityFactorResponse>("/api/metrics/capacity-factor", { ...f }, s),
  powerCurve: (f: FilterParams, binWidth = 0.5, scatterPoints = 1500, s?: AbortSignal) =>
    get<PowerCurveResponse>("/api/metrics/power-curve", { ...f, bin_width: binWidth, scatter_points: scatterPoints }, s),
  deviation: (f: FilterParams, s?: AbortSignal) => get<DeviationResponse>("/api/metrics/performance-deviation", { ...f }, s),
  temperature: (f: FilterParams, s?: AbortSignal) => get<TemperaturePoint[]>("/api/metrics/temperature", { ...f }, s),
  anomalies: (f: FilterParams & { severity?: string; anomaly_type?: string; page?: number; page_size?: number }, s?: AbortSignal) =>
    get<AnomalyPage>("/api/anomalies", { ...f }, s),
  downtime: (f: FilterParams, s?: AbortSignal) => get<DowntimeResponse>("/api/downtime", { ...f }, s),
  scada: (f: FilterParams & { page?: number; page_size?: number; operating_status?: string; flagged_only?: boolean }, s?: AbortSignal) =>
    get<Page<ScadaRow>>("/api/scada", { ...f }, s),
  reportMonths: (s?: AbortSignal) => get<{ month: string; generated_at: string | null }[]>("/api/reports/months", {}, s),
  monthlyReport: (month: string, s?: AbortSignal) => get<MonthlyReport>("/api/reports/monthly", { month }, s),
  quality: (s?: AbortSignal) => get<QualityReport>("/api/data/quality", {}, s),
  imports: (s?: AbortSignal) => get<ImportBatch[]>("/api/data/imports", {}, s),
  importStatus: (id: number) => get<ImportBatch>(`/api/data/imports/${id}`),
  upload: async (file: File): Promise<UploadResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(buildUrl("/api/data/upload"), { method: "POST", body: fd });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = body.detail;
      throw new ApiError(res.status, typeof d === "string" ? d : d?.message ?? JSON.stringify(d));
    }
    return body as UploadResponse;
  },
};

export const downloadUrls = {
  csv: (dataset: string, f: FilterParams) => buildUrl("/api/export/csv", { dataset, ...f }),
  excel: (month?: string) => buildUrl("/api/export/excel", { month }),
  pdf: (month?: string) => buildUrl("/api/reports/pdf", { month }),
};
