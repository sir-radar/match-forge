"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type ResourceState<T> = {
  key: string;
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
};

export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({ key, data: null, loading: true, refreshing: false, error: null });
  const generation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    queueMicrotask(() => {
      if (!controller.signal.aborted && current === generation.current) {
        setState((previous) => previous.key === key ? ({ ...previous, loading: previous.data === null, refreshing: previous.data !== null, error: null }) : ({ key, data: null, loading: true, refreshing: false, error: null }));
      }
    });
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted && current === generation.current) setState({ key, data, loading: false, refreshing: false, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || current !== generation.current) return;
        setState((previous) => ({ ...previous, loading: false, refreshing: false, error: error instanceof Error ? error.message : "Request failed" }));
      });
    return () => controller.abort();
  }, [key, revision, load]);

  const retry = useCallback(() => setRevision((value) => value + 1), []);
  return state.key === key ? { ...state, retry } : { key, data: null, loading: true, refreshing: false, error: null, retry };
}
