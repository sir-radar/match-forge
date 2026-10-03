import { describe, expect, it } from "vitest";
import { parseFixtureGroups, parsePredictions } from "@/lib/contracts";

describe("API contract boundary", () => {
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
});
