"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { HistoricalCoverage, ProviderConfiguration, SyncRun, SyncType } from "@/lib/contracts";

export type SyncFilters = { date: string; from_date: string; season: string; competition: string; country: string };
export function syncLane(type: SyncType): string { return type === "FOTMOB_SYNC" ? "LIVE_FOTMOB" : type === "PITCHAPI_SYNC" ? "LIVE_PITCHAPI" : type === "PUBLIC_REPORTS" || type === "CONTEXT_REPORTS" ? "PUBLIC_REPORTS" : "BULK"; }
function runActive(run: SyncRun): boolean { return run.status === "QUEUED" || run.status === "RUNNING"; }

export function mergeSyncRuns(current: SyncRun[], incoming: SyncRun[]): SyncRun[] {
  const known = new Map(current.map((run) => [run.run_id, run]));
  const merged = incoming.map((run) => {
    const prior = known.get(run.run_id);
    return prior && !runActive(prior) ? prior : run;
  });
  const received = new Set(incoming.map((run) => run.run_id));
  return [...current.filter((run) => !received.has(run.run_id) && runActive(run)), ...merged];
}

function useSyncStatus() {
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [coverage, setCoverage] = useState<HistoricalCoverage | null>(null);
  const [providerConfiguration, setProviderConfiguration] = useState<ProviderConfiguration>({ fotmob_enabled: false, pitchapi_enabled: false, operational_sync_interval: "0s" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clock, setClock] = useState(0);
  const mounted = useRef(false);
  const latestRuns = useRef<SyncRun[]>([]);
  const request = useRef<{ generation: number; controller: AbortController | null }>({ generation: 0, controller: null });
  const invalidate = useCallback(() => { request.current.generation++; request.current.controller?.abort(); }, []);
  const currentRequest = useCallback((generation: number, signal: AbortSignal) => mounted.current && !signal.aborted && generation === request.current.generation, []);
  const publish = useCallback((incoming: SyncRun[]) => {
    latestRuns.current = mergeSyncRuns(latestRuns.current, incoming);
    setRuns(latestRuns.current);
  }, []);
  const reload = useCallback(async () => {
    invalidate();
    const generation = request.current.generation;
    const controller = new AbortController(); request.current.controller = controller;
    try {
      const response = await api.syncRuns(controller.signal);
      // A long bulk run can leave the recent-list page while live jobs complete.
      const incoming = [...response.runs];
      const ids = new Set(response.runs.map((run) => run.run_id));
      for (const run of latestRuns.current.filter((run) => runActive(run) && !ids.has(run.run_id))) {
        incoming.push(await api.syncRun(run.run_id, controller.signal));
      }
      if (!currentRequest(generation, controller.signal)) return;
      publish(incoming); setCoverage(response.coverage); setProviderConfiguration(response.provider_configuration); setError(null);
    } catch (cause) {
      if (!currentRequest(generation, controller.signal)) return;
      setError(errorMessage(cause));
    } finally {
      if (currentRequest(generation, controller.signal)) setLoading(false);
    }
  }, [currentRequest, invalidate, publish]);
  useEffect(() => {
    mounted.current = true; queueMicrotask(() => { if (mounted.current) void reload(); });
    return () => { mounted.current = false; invalidate(); };
  }, [invalidate, reload]);
  const active = runs.filter(runActive);
  const hasActive = active.length > 0;
  useEffect(() => {
    if (!hasActive) return;
    let stopped = false;
    let timer = window.setTimeout(poll, 2500);
    async function poll() { await reload(); if (!stopped) timer = window.setTimeout(poll, 2500); }
    const clockTimer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => { stopped = true; window.clearTimeout(timer); window.clearInterval(clockTimer); invalidate(); };
  }, [hasActive, invalidate, reload]);

  return { active, clock, coverage, error, loading, providerConfiguration, runs, latestRuns, mounted, publish, reload, invalidate, setClock };
}

export function useSyncAdminState(initialDate: string) {
  const { active, clock, coverage, error, loading, providerConfiguration, runs, latestRuns, mounted, publish, reload, invalidate, setClock } = useSyncStatus();
  const [filters, setFilters] = useState<SyncFilters>({ date: initialDate, from_date: "", season: "", competition: "", country: "" });
  const [submitting, setSubmitting] = useState<Record<string, string | undefined>>({});
  const [laneErrors, setLaneErrors] = useState<Record<string, string | undefined>>({});
  const pending = useRef(new Map<string, string>());
  const laneBusy = (type: SyncType) => active.some((run) => syncLane(run.sync_type) === syncLane(type)) || submitting[syncLane(type)] !== undefined;
  const mutate = async (type: SyncType, action: string, operation: () => Promise<SyncRun>, allowActive = false) => {
    const lane = syncLane(type);
    if (pending.current.has(lane) || (!allowActive && latestRuns.current.some((run) => runActive(run) && syncLane(run.sync_type) === lane))) return;
    pending.current.set(lane, action); setSubmitting(Object.fromEntries(pending.current)); setLaneErrors((old) => ({ ...old, [lane]: undefined })); invalidate();
    try {
      const run = await operation();
      if (!mounted.current) return;
      publish([run, ...latestRuns.current.filter((item) => item.run_id !== run.run_id)]);
      setClock(Date.now());
      await reload();
    } catch (cause) {
      if (!mounted.current) return;
      setLaneErrors((old) => ({ ...old, [lane]: errorMessage(cause) }));
      if (cause instanceof ApiError && cause.status === 409) await reload();
    } finally {
      pending.current.delete(lane); if (mounted.current) setSubmitting(Object.fromEntries(pending.current));
    }
  };
  const start = (type: SyncType, operation: (body: Record<string, string>) => Promise<SyncRun>) => mutate(type, type, () => operation(Object.fromEntries(Object.entries(filters).filter(([, value]) => value))));
  const stop = (run: SyncRun) => mutate(run.sync_type, `STOP:${run.run_id}`, () => api.stopSyncRun(run.run_id), true);
  const retry = (run: SyncRun) => mutate(run.sync_type, `RETRY:${run.run_id}`, () => api.retrySyncRun(run.run_id));
  return { active, clock, coverage, error, laneErrors, filters, loading, providerConfiguration, retry, runs, setFilters, start, stop, submitting, reload, laneBusy };
}

function errorMessage(cause: unknown): string {
  if (cause instanceof ApiError) return cause.status >= 500 ? `The API could not start or read the sync. ${cause.message}` : cause.message;
  return cause instanceof Error ? `Network or response error: ${cause.message}` : "Unknown synchronization error.";
}
