import { describe, expect, it } from "vitest";
import { parseContext, parseFixtureGroups, parseLiveMatch, parsePerformance, parsePerformanceList, parsePredictions, parsePredictionPage, parseSyncRun } from "@/lib/contracts";

const competition = { id: "c", name: "League", country: "Country", continent: "Europe", division: 1, type: "LEAGUE", season: "2026", availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: false, xg: false, team_stats: false }, availability_status: "FIXTURES_ONLY", sources: {} };
const fixture = { id: "f", kickoff_at: "2026-01-01T12:00:00Z", status: "SCHEDULED", home: { id: "h", name: "Home", crest_url: null }, away: { id: "a", name: "Away", crest_url: null }, home_score: null, away_score: null, venue: null, round: null, forecast_availability: "UNAVAILABLE", forecast: null };
const context = { fixture_id: "f", home_form: [], away_form: [], h2h: [], h2h_summary: { meetings: 0, home_wins: 0, draws: 0, away_wins: 0, home_goals: 0, away_goals: 0 }, home_team_statistics: null, away_team_statistics: null, standings: [], data_availability: {} };

describe("API contract boundary", () => {
  it("rejects duplicate canonical identities within and across groups", () => {
    expect(() => parseFixtureGroups({ groups: [{ competition, fixtures: [fixture, fixture] }] })).toThrow(/duplicate fixture/);
    expect(() => parseFixtureGroups({ groups: [{ competition, fixtures: [fixture] }, { competition: { ...competition, id: "other" }, fixtures: [fixture] }] })).toThrow(/duplicate fixture/);
    expect(() => parseFixtureGroups({ groups: [{ competition, fixtures: [] }, { competition, fixtures: [] }] })).toThrow(/duplicate competition/);
  });

  it("preserves separate canonical matches with the same teams and kickoff", () => {
    const groups = parseFixtureGroups({ groups: [{ competition, fixtures: [fixture, { ...fixture, id: "second-leg" }] }] });
    expect(groups[0].fixtures.map(({ id }) => id)).toEqual(["f", "second-leg"]);
  });

  it.each(["SCHEDULED", "LIVE", "HALF_TIME", "FINISHED", "POSTPONED", "CANCELLED", "ABANDONED", "SUSPENDED", "INTERRUPTED", "AWARDED"])("accepts canonical fixture state %s", (status) => {
    expect(parseFixtureGroups({ groups: [{ competition, fixtures: [{ ...fixture, status }] }] })[0].fixtures[0].status).toBe(status);
  });

  it.each(["UNKNOWN", "live", "IN_PLAY"])("rejects noncanonical fixture state %s", (status) => {
    expect(() => parseFixtureGroups({ groups: [{ competition, fixtures: [{ ...fixture, status }] }] })).toThrow(/status/);
  });

  it.each(["not-a-date", "2026-01-01", "2026-01-01T12:00:00", null])("rejects invalid required fixture time %s", (kickoff_at) => {
    expect(() => parseFixtureGroups({ groups: [{ competition, fixtures: [{ ...fixture, kickoff_at }] }] })).toThrow(/kickoff_at/);
  });

  it("validates form venue before using it as a domain value", () => {
    const form = { kickoff_at: fixture.kickoff_at, opponent: "Other", venue: "NEUTRAL", goals_for: 0, goals_against: 0, result: "D" };
    expect(() => parseContext({ ...context, home_form: [form] })).toThrow(/venue/);
    expect(parseContext({ ...context, home_form: [{ ...form, venue: "AWAY" }] }).home_form[0].venue).toBe("AWAY");
  });
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
  it("validates live ordering metadata without conflating fetch time", () => {
    const source = { provider: "fotmob", provider_match_id: "native", observed_at: "2026-11-01T12:00:00Z", last_fetched_at: "2026-11-01T12:05:00Z", stale: false, ordering_basis: "MATCH_CLOCK", source_updated_at: null };
    const live = { fixture_id: "f", status: "LIVE", home: { id: "h", name: "Home", crest_url: null }, away: { id: "a", name: "Away", crest_url: null }, home_score: 0, away_score: 0, match_minute: 20, added_time: null, period: null, events: [], statistics: [], score_source: source, event_source: null, statistics_source: null, availability: {}, partial: true, score_conflict: true };
    expect(parseLiveMatch(live).score_source).toMatchObject({ ordering_basis: "MATCH_CLOCK", source_updated_at: null });
    expect(() => parseLiveMatch({ ...live, score_source: { ...source, ordering_basis: "HTTP_TIME" } })).toThrow(/ordering_basis/);
    expect(() => parseLiveMatch({ ...live, score_source: { ...source, source_updated_at: "not-a-date" } })).toThrow();
    expect(() => parseLiveMatch({ ...live, score_conflict: "false" })).toThrow(/score_conflict/);
    const { ordering_basis, source_updated_at, ...legacy } = source;
    void ordering_basis; void source_updated_at;
    expect(parseLiveMatch({ ...live, score_source: legacy }).score_source?.ordering_basis).toBe("UNKNOWN");
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
    const payload = {
      run_id: "run", sync_type: "MVP_SYNC", status: "RUNNING",
      requested_at: "2026-10-04T10:00:00Z", started_at: null, finished_at: null,
      requested_date: "2026-10-04", parameters: {}, summary: {},
      error_message: null, log_path: null,
      history_queue: { total: 227, pending: 184, running: 3, succeeded: 40, failed: 0 },
    };
    const run = parseSyncRun(payload);

    expect(run.status).toBe("RUNNING");
    expect(run.history_queue).toEqual({ total: 227, pending: 184, running: 3, succeeded: 40, failed: 0 });
    expect(parseSyncRun({ ...payload, sync_type: "CONTEXT_REPORTS" }).sync_type).toBe("CONTEXT_REPORTS");
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

  it("rejects single-source or minority consensus claims", () => {
    const pagination = { page: 1, page_size: 20, total_items: 0, total_pages: 0 };
    const consensus = { id: "f:RESULT_1X2", fixture: "Home vs Away", market: "RESULT_1X2", kickoff: "2026-01-01T12:00:00Z", selection: "HOME_WIN", count: 1, total: 1, agreement: "AGREES" };
    expect(() => parsePredictionPage({ predictions: [], pagination, consensus: [consensus] })).toThrow(/count/);
    expect(() => parsePredictionPage({ predictions: [], pagination, consensus: [{ ...consensus, count: 2, total: 4 }] })).toThrow(/majority/);
    expect(parsePredictionPage({ predictions: [], pagination, consensus: [] }).consensus).toEqual([]);
  });

});
