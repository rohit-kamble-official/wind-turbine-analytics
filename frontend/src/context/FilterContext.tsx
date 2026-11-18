import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type FilterParams } from "../services/api";
import type { Health, Turbine } from "../services/types";

interface FilterState {
  startDate: string;
  endDate: string;
  turbineId: string; // "" = all turbines
  minDate: string;
  maxDate: string;
  turbines: Turbine[];
  health: Health | null;
  healthError: string | null;
  ready: boolean;
  params: FilterParams;
  setRange: (start: string, end: string) => void;
  setTurbineId: (id: string) => void;
  refreshHealth: () => Promise<void>;
  dataVersion: number; // bump to force re-fetch after uploads
  bumpData: () => void;
}

const Ctx = createContext<FilterState | null>(null);

export function FilterProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [turbines, setTurbines] = useState<Turbine[]>([]);
  const [startDate, setStart] = useState("");
  const [endDate, setEnd] = useState("");
  const [turbineId, setTurbineId] = useState("");
  const [dataVersion, setDataVersion] = useState(0);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await api.health();
      setHealth(h);
      setHealthError(null);
      // initialise the range to the full data period on first load
      setStart((s) => s || h.data_start || "");
      setEnd((e) => e || h.data_end || "");
    } catch (e) {
      setHealthError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    api.turbines().then(setTurbines).catch(() => setTurbines([]));
    const t = setInterval(refreshHealth, 30000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  const setRange = useCallback((s: string, e: string) => {
    if (s && e && s > e) [s, e] = [e, s];
    setStart(s);
    setEnd(e);
  }, []);

  const params = useMemo<FilterParams>(
    () => ({ start_date: startDate || undefined, end_date: endDate || undefined, turbine_id: turbineId || undefined }),
    [startDate, endDate, turbineId],
  );

  const value: FilterState = {
    startDate, endDate, turbineId, turbines, health, healthError, params, setRange, setTurbineId, refreshHealth,
    minDate: health?.data_start ?? "", maxDate: health?.data_end ?? "",
    ready: Boolean(health && startDate && endDate), dataVersion, bumpData: () => setDataVersion((v) => v + 1),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useFilters(): FilterState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useFilters must be used inside FilterProvider");
  return c;
}
