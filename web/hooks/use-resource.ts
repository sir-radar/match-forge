"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type ResourceState<T> = {
  key: string;
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  errorStatus: number | null;
};

function errorStatus(error: unknown): number | null {
  if (typeof error !== "object" || error === null || !("status" in error)) return null;
  const status = error.status;
  return typeof status === "number" && Number.isInteger(status) ? status : null;
}

export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({ key, data: null, loading: true, refreshing: false, error: null, errorStatus: null });
  const generation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    queueMicrotask(() => {
      if (!controller.signal.aborted && current === generation.current) {
        setState((previous) => previous.key === key ? ({ ...previous, loading: previous.data === null, refreshing: previous.data !== null, error: null, errorStatus: null }) : ({ key, data: null, loading: true, refreshing: false, error: null, errorStatus: null }));
      }
    });
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted && current === generation.current) setState({ key, data, loading: false, refreshing: false, error: null, errorStatus: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || current !== generation.current) return;
        setState((previous) => ({ ...previous, loading: false, refreshing: false, error: error instanceof Error ? error.message : "Request failed", errorStatus: errorStatus(error) }));
      });
    return () => controller.abort();
  }, [key, revision, load]);

  const retry = useCallback(() => setRevision((value) => value + 1), []);
  return state.key === key ? { ...state, retry } : { key, data: null, loading: true, refreshing: false, error: null, errorStatus: null, retry };
}
