import {
  parseMarketCapabilitySummary,
  parseCompetitions,
  parseContext,
  parseFixtureGroups,
  parseLiveMatch,
  parseForecast,
  parseForecastHistory,
  parsePerformance,
  parsePerformanceList,
  parsePredictionArchive,
  parsePredictionPage,
  parseSources,
  parseSyncRun,
  parseSyncRuns,
} from "@/lib/contracts";
import type { MarketScope, SyncRun } from "@/lib/contracts";
import { parseBackupView, type BackupScope, type BackupView } from "@/lib/backup";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080";

type RequestOptions = { method?: "GET" | "POST"; body?: Record<string, string | boolean>; signal?: AbortSignal; origin?: string };

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

function fetchResponse(path: string, options: RequestOptions) {
  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET", signal: options.signal,
    headers: { Accept: "application/json", ...(options.origin ? { Origin: options.origin } : {}), ...(options.method === "POST" ? { "Content-Type": "application/json" } : {}) },
    cache: path.startsWith("/v1/admin/backup") ? "no-store" : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
}

async function request<T>(path: string, parse: (value: unknown) => T, options: RequestOptions = {}): Promise<T> {
  const response = await fetchResponse(path, options);
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

type BackupStatusResult = { view: BackupView; error: null } | { view: null; error: string };

const backupTimeoutMessage = "The backup status check timed out. Check the local API and external drive, then retry.";

function backupStatusHTTPError(status: number): string {
  switch (status) {
    case 404:
      return "The running API does not support Backup & Recovery (HTTP 404). Check the API address and start a compatible MatchForge release.";
    case 401:
    case 403:
      return "The API denied access to backup status. Open MatchForge at the configured Admin origin.";
    case 408:
    case 504:
      return backupTimeoutMessage;
    default:
      return `The API could not check backup status (HTTP ${status}). Check the local API and retry.`;
  }
}

async function requestBackupStatus(path: string, options: RequestOptions): Promise<BackupStatusResult> {
  const deadline = AbortSignal.timeout(15_000);
  const signal = options.signal ? AbortSignal.any([options.signal, deadline]) : deadline;
  let response: Response;
  try {
    response = await fetchResponse(path, { ...options, signal });
  } catch {
    const error = options.origin
      ? "The web server could not reach the backup API. Check the local API address and retry."
      : "The browser could not reach the backup API. Check the local API and its cross-origin settings for this Admin page, then retry.";
    return { view: null, error: deadline.aborted ? backupTimeoutMessage : error };
  }
  if (!response.ok) return { view: null, error: backupStatusHTTPError(response.status) };
  try {
    return { view: parseBackupView(await response.json()), error: null };
  } catch {
    return {
      view: null,
      error: deadline.aborted ? backupTimeoutMessage : "The API returned incompatible backup status. Run matching MatchForge web and API releases, then retry.",
    };
  }
}

export const api = {
  backup: (signal?: AbortSignal, origin?: string) => requestBackupStatus("/v1/admin/backup", { signal, origin }),
  previewBackup: (signal?: AbortSignal) => requestBackupStatus("/v1/admin/backup/preview", { method: "POST", body: {}, signal }),
  startBackup: (requestId: string, scope: BackupScope, digest: string | null, signal?: AbortSignal, governed: string | null = null) => request("/v1/admin/backup", (value) => {
    const run = parseSyncRun(value);
    if (run.sync_type !== "MANUAL_BACKUP" || run.run_id !== requestId || run.parameters.scope !== scope ||
        (run.parameters.unavailable_sha256 ?? null) !== digest || (run.parameters.governed_sha256 ?? null) !== governed) throw new Error("Backup request identity or scope mismatch");
    return run;
  }, { method: "POST", body: { request_id: requestId, confirmed: true, scope, ...(digest ? { unavailable_sha256: digest } : {}), ...(governed ? { governed_sha256: governed } : {}) }, signal }),
  marketCapabilities: (scope: MarketScope, signal?: AbortSignal) => request(`/v1/admin/market-capabilities?${new URLSearchParams(scope)}`, (value) => {
    const report = parseMarketCapabilitySummary(value);
    if (report.competition_id !== scope.competition_id || report.season_id !== scope.season_id || Date.parse(report.knowledge_cutoff) !== Date.parse(scope.knowledge_cutoff)) throw new Error("market report scope mismatch");
    return report;
  }, { signal }),
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
  predictions: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/external-predictions?${query}`, parsePredictionPage, { signal }),
  predictionArchive: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/external-predictions/archive?${query}`, parsePredictionArchive, { signal }),
  sources: (query = new URLSearchParams(), signal?: AbortSignal) => request(`/v1/external-prediction-sources?${query}`, parseSources, { signal }),
  startMvpSync: (body: Record<string, string>) => startSync("mvp", body),
  startOpenFootballSync: (body: Record<string, string>) => startSync("openfootball", body),
  startFootballDataUKSync: (body: Record<string, string>) => startSync("football-data-uk", body),
  startResultRecovery: (body: Record<string, string>) => startSync("result-recovery", body),
  startHistoryBackfill: (body: Record<string, string | boolean>) => startSync("history", body),
  startForecastRefresh: (body: Record<string, string>) => startSync("forecast-refresh", body),
  startExternalPredictionSettlement: () => startSync("settle-external-predictions", {}),
  startExternalPredictionsSync: (body: Record<string, string>) => startSync("external-predictions", body),
  startFotMobSync: (body: Record<string, string>) => startSync("fotmob", body),
  startPitchAPISync: (body: Record<string, string>) => startSync("pitchapi", body),
  startAllDataSync: (body: Record<string, string>) => startSync("all", body),
  syncRuns: (signal?: AbortSignal) => request("/v1/admin/sync-runs", parseSyncRuns, { signal }),
  syncRun: (id: string, signal?: AbortSignal) => request(`/v1/admin/sync-runs/${encodeURIComponent(id)}`, parseSyncRun, { signal }),
  stopSyncRun: (id: string, signal?: AbortSignal) => request(`/v1/admin/sync-runs/${encodeURIComponent(id)}/stop`, parseSyncRun, { method: "POST", signal }),
  retrySyncRun: (id: string) => request(`/v1/admin/sync-runs/${encodeURIComponent(id)}/retry`, parseSyncRun, { method: "POST" }),
};

function startSync(action: string, body: Record<string, string | boolean>): Promise<SyncRun> {
  return request(`/v1/admin/sync/${action}`, parseSyncRun, { method: "POST", body });
}
