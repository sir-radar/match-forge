"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type ResourceState<T> = {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
};

export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({ data: null, loading: true, refreshing: false, error: null });
  const generation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    queueMicrotask(() => {
      if (!controller.signal.aborted && current === generation.current) {
        setState((previous) => ({ ...previous, loading: previous.data === null, refreshing: previous.data !== null, error: null }));
      }
    });
    load(controller.signal)
      .then((data) => {
        if (current === generation.current) setState({ data, loading: false, refreshing: false, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || current !== generation.current) return;
        setState((previous) => ({ ...previous, loading: false, refreshing: false, error: error instanceof Error ? error.message : "Request failed" }));
      });
    return () => controller.abort();
  }, [key, revision, load]);

  const retry = useCallback(() => setRevision((value) => value + 1), []);
  return { ...state, retry };
}
