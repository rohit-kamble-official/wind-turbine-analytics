import { useCallback, useEffect, useRef, useState } from "react";
import { useFilters } from "../context/FilterContext";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Fetch helper with abort-on-change. Waits until filters are initialised
 * (`ready`) so components never fire requests with an empty date range.
 */
export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: unknown[], enabled = true): ApiState<T> {
  const { ready, dataVersion } = useFilters();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!ready || !enabled) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    fetcherRef.current(ctrl.signal)
      .then((d) => setData(d))
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
        setData(null);
      })
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, enabled, nonce, dataVersion, ...deps]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading: loading || !ready, error, reload };
}
