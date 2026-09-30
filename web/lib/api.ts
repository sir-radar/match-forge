import {
  parseCompetitions,
  parseContext,
  parseFixtureGroups,
  parseForecast,
  parsePerformance,
  parsePredictions,
  parseSources,
} from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080";

async function request<T>(path: string, parse: (value: unknown) => T, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { error?: unknown };
      if (typeof payload.error === "string") message = payload.error;
    } catch {
      // Keep status-based message when the server did not return JSON.
    }
    throw new Error(message);
  }
  return parse(await response.json());
}

export const api = {
  competitions: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/competitions?${query}`, parseCompetitions, signal),
  fixtures: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/fixtures?${query}`, parseFixtureGroups, signal),
  context: (fixtureId: string, signal?: AbortSignal) => request(`/v1/fixtures/${fixtureId}/context`, parseContext, signal),
  forecast: (fixtureId: string, forecastId: string, signal?: AbortSignal) => request(`/v1/fixtures/${fixtureId}/forecasts/${forecastId}`, parseForecast, signal),
  performance: (competitionId: string, signal?: AbortSignal) => request(`/v1/competitions/${competitionId}/performance`, parsePerformance, signal),
  predictions: (query: URLSearchParams, signal?: AbortSignal) => request(`/v1/external-predictions?${query}`, parsePredictions, signal),
  sources: (signal?: AbortSignal) => request("/v1/external-prediction-sources", parseSources, signal),
};
