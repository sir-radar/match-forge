import { describe, expect, it } from "vitest";
import { parseFixtureGroups, parseLiveMatch, parsePerformance, parsePerformanceList, parsePredictions, parseSyncRun } from "@/lib/contracts";

describe("API contract boundary", () => {
  it("parses zero-valued live scores and statistics", () => {
    const value = parseLiveMatch({
      fixture_id: "f", status: "LIVE",
      home: { id: "h", name: "Home", crest_url: null }, away: { id: "a", name: "Away", crest_url: null },
      home_score: 0, away_score: 0, match_minute: null, added_time: null, period: null,
      events: [], statistics: [{ metric: "red_cards", label: "Red cards", period: "FULL_MATCH", home: 0, away: null, unit: "number", original_field: "red_cards", available: true }],
      score_source: null, event_source: null, statistics_source: null,
      availability: { score: true, events: false, statistics: true }, partial: true,
    });
    expect(value.home_score).toBe(0);
    expect(value.statistics[0]).toMatchObject({ home: 0, away: null });
  });
  it("rejects invalid forecast probabilities", () => {
    expect(() => parseFixtureGroups({ groups: [{ competition: {
      id: "c", name: "League", country: "Country", continent: "Europe", division: 1, type: "LEAGUE", season: "2026",
      availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: true, xg: false, team_stats: false }, availability_status: "FORECAST_AVAILABLE", sources: {},
    }, fixtures: [{ id: "f", kickoff_at: "2026-01-01T12:00:00Z", status: "SCHEDULED", home: { id: "h", name: "Home", crest_url: null }, away: { id: "a", name: "Away", crest_url: null }, home_score: null, away_score: null, venue: null, round: null, forecast_availability: "FORECAST_AVAILABLE", forecast: { id: "p", expected_home_goals: 1, expected_away_goals: 1, probabilities: { home: 1.2, draw: 0, away: 0 } } }] }] })).toThrow(/\[0,1\]/);
  });

  it("rejects invalid external-prediction agreement states", () => {
    expect(() => parsePredictions({ predictions: [{
      id: "p", source: "Source", source_page: "https://example.com", prediction_date: "2026-10-01",
      original_date_text: "2026-10-01", collected_at: "2026-10-01T00:00:00Z", fixture_id: null,
      kickoff_at: null, competition: "League", home_team: "Home", away_team: "Away", market: "RESULT_1X2",
      selection: "Home", match_status: "MATCHED", matchforge_probability: 0.5, agreement: "UNKNOWN",
    }] })).toThrow(/invalid agreement/);
  });

  it("validates performance pagination metadata", () => {
    const valid = { performance: [], pagination: { page: 1, page_size: 20, total_items: 0, total_pages: 0 } };
    expect(parsePerformanceList(valid).pagination).toEqual(valid.pagination);
    expect(() => parsePerformanceList({ ...valid, pagination: { ...valid.pagination, page_size: 25 } })).toThrow(/page_size/);
    expect(() => parsePerformanceList({ ...valid, pagination: { ...valid.pagination, page: 1.5 } })).toThrow(/integer/);
    expect(() => parsePerformanceList({ ...valid, pagination: { ...valid.pagination, total_pages: 1 } })).toThrow(/total_pages/);
  });

  it("keeps queue progress separate from top-level sync status", () => {
    const run = parseSyncRun({
      run_id: "run", sync_type: "MVP_SYNC", status: "RUNNING",
      requested_at: "2026-10-04T10:00:00Z", started_at: null, finished_at: null,
      requested_date: "2026-10-04", parameters: {}, summary: {},
      error_message: null, log_path: null,
      history_queue: { total: 227, pending: 184, running: 3, succeeded: 40, failed: 0 },
    });

    expect(run.status).toBe("RUNNING");
    expect(run.history_queue).toEqual({ total: 227, pending: 184, running: 3, succeeded: 40, failed: 0 });
  });
  it("requires versioned analytics and fixed horizon metadata", () => {
    const item = { competition_id: "c", league: "League", country: "Test", continent: "Other", rating: "UNRATED", forecasts: 0,
      analytics_policy_version: "pre-match-revisions-v2", analytics_horizon: "LATEST",
      outcome_hit_rate: null, brier: null, log_loss: null, baseline_brier: null, baseline_log_loss: null,
      exact_score_rate: null, top_three_score_rate: null, top_five_score_rate: null, total_goals_hit_rate: null, btts_hit_rate: null,
      latest_fifty_brier: null, latest_fifty_log_loss: null, latest_fifty_baseline_brier: null, latest_fifty_baseline_log_loss: null };
    expect(parsePerformance(item).analytics_horizon).toBe("LATEST");
    expect(() => parsePerformance({ ...item, analytics_policy_version: "unknown" })).toThrow(/policy/);
    expect(() => parsePerformance({ ...item, analytics_horizon: "CONFIRMED_LINEUP" })).toThrow(/horizon/);
    expect(() => parsePerformance({ ...item, rating: "unknown" })).toThrow(/rating/);
  });

});
