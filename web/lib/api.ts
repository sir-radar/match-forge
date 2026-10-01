import {
  parseCompetitions,
  parseContext,
  parseFixtureGroups,
  parseForecast,
  parsePerformance,
  parsePerformanceList,
  parsePredictions,
  parseSources,
  parseSyncRun,
  parseSyncRuns,
} from "@/lib/contracts";
import type { SyncRun } from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080";

type RequestOptions = { method?: "GET" | "POST"; body?: Record<string, string>; signal?: AbortSignal };

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(path: string, parse: (value: unknown) => T, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET", signal: options.signal,
    headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { error?: unknown };
      if (typeof payload.error === "string") message = payload.error;
    } catch {
      // Keep status-based message when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  return parse(await response.json());
}

export const api = {
  competitions: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/competitions?${query}`, parseCompetitions, { signal }),
  fixtures: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/fixtures?${query}`, parseFixtureGroups, { signal }),
  context: (fixtureId: string, signal?: AbortSignal) => request(`/v1/fixtures/${fixtureId}/context`, parseContext, { signal }),
  forecast: (fixtureId: string, forecastId: string, signal?: AbortSignal) => request(`/v1/fixtures/${fixtureId}/forecasts/${forecastId}`, parseForecast, { signal }),
  performance: (competitionId: string, signal?: AbortSignal) => request(`/v1/competitions/${competitionId}/performance`, parsePerformance, { signal }),
  performanceList: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/performance?${query}`, parsePerformanceList, { signal }),
  predictions: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/external-predictions?${query}`, parsePredictions, { signal }),
  sources: (query = new URLSearchParams(), signal?: AbortSignal) => request(`/v1/external-prediction-sources?${query}`, parseSources, { signal }),
  startMvpSync: (body: Record<string, string>) => startSync("mvp", body),
  startOpenFootballSync: (body: Record<string, string>) => startSync("openfootball", body),
  startFootballDataUKSync: (body: Record<string, string>) => startSync("football-data-uk", body),
  startHistoryBackfill: (body: Record<string, string>) => startSync("history", body),
  startForecastRefresh: (body: Record<string, string>) => startSync("forecast-refresh", body),
  startExternalPredictionsSync: (body: Record<string, string>) => startSync("external-predictions", body),
  startAllDataSync: (body: Record<string, string>) => startSync("all", body),
  syncRuns: (signal?: AbortSignal) => request("/v1/admin/sync-runs", parseSyncRuns, { signal }),
  syncRun: (id: string, signal?: AbortSignal) => request(`/v1/admin/sync-runs/${encodeURIComponent(id)}`, parseSyncRun, { signal }),
};

function startSync(action: string, body: Record<string, string>): Promise<SyncRun> {
  return request(`/v1/admin/sync/${action}`, parseSyncRun, { method: "POST", body });
}
