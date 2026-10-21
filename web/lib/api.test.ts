import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";

const team = { id: "team", name: "Team", crest_url: null };
const context = { fixture_id: "fixture", home_form: [], away_form: [], h2h: [], h2h_summary: { meetings: 0, home_wins: 0, draws: 0, away_wins: 0, home_goals: 0, away_goals: 0 }, home_team_statistics: null, away_team_statistics: null, standings: [], data_availability: {} };
const live = { fixture_id: "fixture", status: "SCHEDULED", home: team, away: { ...team, id: "away" }, home_score: null, away_score: null, match_minute: null, added_time: null, period: null, events: [], statistics: [], score_source: null, event_source: null, statistics_source: null, availability: {}, partial: true };
const forecast = { id: "forecast", fixture_id: "fixture", expected_home_goals: 1, expected_away_goals: 1, probabilities: { home: .3, draw: .4, away: .3 }, model_label: "MVP_FORECAST", model_algorithm_version: "transferable-rolling-goals-poisson-v1", created_at: "2026-10-01T00:00:00Z", football_cutoff: "2026-10-01T00:00:00Z", knowledge_cutoff: "2026-10-01T00:00:00Z", knowledge_mode: "bitemporal", publication_mode: "MVP_OWNER_AUTHORIZED", score_matrix: [] };
const performance = { competition_id: "competition", league: "League", country: "Country", continent: "Europe", rating: "UNRATED", forecasts: 0, analytics_policy_version: "pre-match-revisions-v2", analytics_horizon: "LATEST", ...Object.fromEntries(["outcome_hit_rate", "brier", "log_loss", "baseline_brier", "baseline_log_loss", "exact_score_rate", "top_three_score_rate", "top_five_score_rate", "total_goals_hit_rate", "btts_hit_rate", "latest_fifty_brier", "latest_fifty_log_loss", "latest_fifty_baseline_brier", "latest_fifty_baseline_log_loss"].map((key) => [key, null])) };

function respond(payload: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("requested resource identity", () => {
  it.each([
    { name: "context", payload: context, load: () => api.context("fixture"), wrong: { fixture_id: "other" } },
    { name: "live", payload: live, load: () => api.live("fixture"), wrong: { fixture_id: "other" } },
    { name: "forecast fixture", payload: forecast, load: () => api.forecast("fixture", "forecast"), wrong: { fixture_id: "other" } },
    { name: "forecast revision", payload: forecast, load: () => api.forecast("fixture", "forecast"), wrong: { id: "other" } },
    { name: "performance", payload: performance, load: () => api.performance("competition"), wrong: { competition_id: "other" } },
  ])("binds $name to its request", async ({ payload, load, wrong }) => {
    respond(payload);
    await expect(load()).resolves.toMatchObject(payload);
    respond({ ...payload, ...wrong });
    await expect(load()).rejects.toThrow(/mismatch/);
  });

  it("forwards cancellation and encodes fixture and forecast path segments", async () => {
    respond({ ...forecast, fixture_id: "fixture/one", id: "forecast/one" });
    const controller = new AbortController();
    await api.forecast("fixture/one", "forecast/one", controller.signal);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/fixtures/fixture%2Fone/forecasts/forecast%2Fone"), expect.objectContaining({ signal: controller.signal }));
  });
});

describe("untrusted error responses", () => {
  it.each([null, [], "unavailable", 42, { error: 42 }])("retains HTTP status for %j", async (payload) => {
    respond(payload, 503);
    await expect(api.competitions(new URLSearchParams())).rejects.toMatchObject({ message: "Request failed (503)", status: 503 });
  });
  it("preserves a server error message", async () => {
    respond({ error: "Read report unavailable" }, 503);
    await expect(api.context("fixture")).rejects.toEqual(new ApiError("Read report unavailable", 503));
  });
  it("handles a non-JSON gateway response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Unavailable</html>", { status: 502 })));
    await expect(api.context("fixture")).rejects.toMatchObject({ message: "Request failed (502)", status: 502 });
  });

  it.each(["created_at", "football_cutoff", "knowledge_cutoff"])("rejects malformed forecast %s", async (field) => {
    respond({ ...forecast, [field]: "2026-10-01" });
    await expect(api.forecast("fixture", "forecast")).rejects.toThrow(field);
  });

  it("rejects provider-native live states and malformed source times", async () => {
    respond({ ...live, status: "inprogress" });
    await expect(api.live("fixture")).rejects.toThrow(/status/);
    const source = { provider: "source", provider_match_id: "native-id", observed_at: "yesterday", last_fetched_at: "2026-10-01T00:00:00Z", stale: false };
    respond({ ...live, score_source: source });
    await expect(api.live("fixture")).rejects.toThrow(/observed_at/);
    respond({ ...live, score_source: { ...source, observed_at: source.last_fetched_at, last_fetched_at: "invalid" } });
    await expect(api.live("fixture")).rejects.toThrow(/last_fetched_at/);
  });
});
