import {
  parseCompetitions,
  parseContext,
  parseFixtureGroups,
  parseLiveMatch,
  parseForecast,
  parseForecastHistory,
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
    headers: { Accept: "application/json", ...(options.method === "POST" ? { "Content-Type": "application/json" } : {}) },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) throw await responseError(response);
  return parse(await response.json());
}

async function responseError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const payload: unknown = await response.json();
    if (typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "string") message = payload.error;
  } catch {
    // Keep status-based message when the server did not return JSON.
  }
  return new ApiError(message, response.status);
}

export const api = {
  competitions: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/competitions?${query}`, parseCompetitions, { signal }),
  fixtures: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/fixtures?${query}`, parseFixtureGroups, { signal }),
  live: (fixtureId: string, signal?: AbortSignal) => request(`/v1/fixtures/${encodeURIComponent(fixtureId)}/live`, (value) => {
    const live = parseLiveMatch(value);
    if (live.fixture_id !== fixtureId) throw new Error("live fixture mismatch");
    return live;
  }, { signal }),
  context: (fixtureId: string, signal?: AbortSignal) => request(`/v1/fixtures/${encodeURIComponent(fixtureId)}/context`, (value) => {
    const context = parseContext(value);
    if (context.fixture_id !== fixtureId) throw new Error("context fixture mismatch");
    return context;
  }, { signal }),
  forecast: (fixtureId: string, forecastId: string, signal?: AbortSignal) => request(`/v1/fixtures/${encodeURIComponent(fixtureId)}/forecasts/${encodeURIComponent(forecastId)}`, (value) => {
    const forecast = parseForecast(value);
    if (forecast.fixture_id !== fixtureId || forecast.id !== forecastId) throw new Error("forecast identity mismatch");
    return forecast;
  }, { signal }),
  forecastHistory: (fixtureId: string, signal?: AbortSignal) => request(`/v1/fixtures/${encodeURIComponent(fixtureId)}/forecasts`, (value) => { const rows = parseForecastHistory(value); if (rows.some((row) => row.fixture_id !== fixtureId)) throw new Error("forecast history fixture mismatch"); return rows; }, { signal }),
  performance: (competitionId: string, signal?: AbortSignal) => request(`/v1/competitions/${encodeURIComponent(competitionId)}/performance`, (value) => {
    const performance = parsePerformance(value);
    if (performance.competition_id !== competitionId) throw new Error("performance competition mismatch");
    return performance;
  }, { signal }),
  performanceList: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/performance?${query}`, parsePerformanceList, { signal }),
  predictions: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/external-predictions?${query}`, parsePredictions, { signal }),
  sources: (query = new URLSearchParams(), signal?: AbortSignal) => request(`/v1/external-prediction-sources?${query}`, parseSources, { signal }),
  startMvpSync: (body: Record<string, string>) => startSync("mvp", body),
  startOpenFootballSync: (body: Record<string, string>) => startSync("openfootball", body),
  startFootballDataUKSync: (body: Record<string, string>) => startSync("football-data-uk", body),
  startHistoryBackfill: (body: Record<string, string>) => startSync("history", body),
  startForecastRefresh: (body: Record<string, string>) => startSync("forecast-refresh", body),
  startExternalPredictionsSync: (body: Record<string, string>) => startSync("external-predictions", body),
  startFotMobSync: (body: Record<string, string>) => startSync("fotmob", body),
  startPitchAPISync: (body: Record<string, string>) => startSync("pitchapi", body),
  startAllDataSync: (body: Record<string, string>) => startSync("all", body),
  syncRuns: (signal?: AbortSignal) => request("/v1/admin/sync-runs", parseSyncRuns, { signal }),
  syncRun: (id: string, signal?: AbortSignal) => request(`/v1/admin/sync-runs/${encodeURIComponent(id)}`, parseSyncRun, { signal }),
  stopSyncRun: (id: string) => request(`/v1/admin/sync-runs/${encodeURIComponent(id)}/stop`, parseSyncRun, { method: "POST" }),
  retrySyncRun: (id: string) => request(`/v1/admin/sync-runs/${encodeURIComponent(id)}/retry`, parseSyncRun, { method: "POST" }),
};

function startSync(action: string, body: Record<string, string>): Promise<SyncRun> {
  return request(`/v1/admin/sync/${action}`, parseSyncRun, { method: "POST", body });
}
