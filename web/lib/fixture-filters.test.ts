import { describe, expect, it } from "vitest";
import { parseFixtureGroups, type Fixture } from "@/lib/contracts";
import { DEFAULT_FIXTURE_FILTERS, filterFixtureGroups } from "@/lib/fixture-filters";

const competition = { id: "league", name: "League", country: "England", continent: "Europe", division: 1, type: "LEAGUE", season: "2026", availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: true, xg: false, team_stats: false }, availability_status: "FORECAST_AVAILABLE", sources: {} };
const raw = { id: "home", kickoff_at: "2026-09-29T15:00:00Z", status: "FINISHED", result_score_basis: "REGULATION_90", home: { id: "h", name: "Arsenal", crest_url: null }, away: { id: "a", name: "Chelsea", crest_url: null }, home_score: 2, away_score: 0, venue: null, round: null, forecast_availability: "FORECAST_AVAILABLE", forecast: { id: "f", expected_home_goals: 1.5, expected_away_goals: 1, probabilities: { home: .55, draw: .35, away: .1 } } };
const fixture = parseFixtureGroups({ groups: [{ competition, fixtures: [raw] }] })[0].fixtures[0];
function matches(changes: Partial<typeof DEFAULT_FIXTURE_FILTERS>, item: Fixture = fixture) {
  return filterFixtureGroups([{ competition: { ...competition, type: "LEAGUE" as const }, fixtures: [item] }], { ...DEFAULT_FIXTURE_FILTERS, ...changes }).flatMap((group) => group.fixtures);
}

describe("fixture filters", () => {
  it("defaults to unrestricted fixtures including missing forecasts and results", () => {
    expect(matches({}, { ...fixture, status: "SCHEDULED", home_score: null, away_score: null, forecast: null })).toHaveLength(1);
  });
  it.each([0, 10, 55, 58, 100])("includes exact %s%% boundaries without rounding", (percent) => {
    const item = { ...fixture, forecast: { ...fixture.forecast!, probabilities: { home: percent / 100, draw: 0, away: 0 } } };
    expect(matches({ minimumProbability: percent, outcome: "home" }, item)).toHaveLength(1);
    if (percent < 100) expect(matches({ minimumProbability: percent + 1, outcome: "home" }, item)).toHaveLength(0);
  });
  it.each(["home", "draw", "away", "either"] as const)("uses published %s probability", (outcome) => {
    const threshold = { home: 55, draw: 35, away: 10, either: 55 }[outcome];
    expect(matches({ outcome, minimumProbability: threshold })).toHaveLength(1);
    expect(matches({ outcome, minimumProbability: threshold + 1 })).toHaveLength(0);
  });
  it("Either Team uses the larger individual team probability, never their sum or the draw", () => {
    const item = { ...fixture, forecast: { ...fixture.forecast!, probabilities: { home: .1, draw: .7, away: .2 } } };
    expect(matches({ outcome: "either", minimumProbability: 20 }, item)).toHaveLength(1);
    expect(matches({ outcome: "either", minimumProbability: 21 }, item)).toHaveLength(0);
  });
  it.each([null, 0, 10])("handles unavailable forecasts with threshold %s", (minimumProbability) => {
    expect(matches({ minimumProbability }, { ...fixture, forecast: null })).toHaveLength(minimumProbability === null ? 1 : 0);
    expect(matches({ minimumProbability }, { ...fixture, forecast_availability: "SOURCE_DATA_INCOMPLETE" })).toHaveLength(minimumProbability === null ? 1 : 0);
  });
  it.each([NaN, Infinity, -1, 1.01, undefined])("rejects invalid relevant probability %s", (home) => {
    expect(matches({ minimumProbability: 0, outcome: "home" }, { ...fixture, forecast: { ...fixture.forecast!, probabilities: { home: home as number } } })).toHaveLength(0);
  });
  it.each([["HOME_WON", 2, 0], ["AWAY_WON", 0, 2], ["DRAW", 0, 0]] as const)("classifies confirmed %s results", (result, home_score, away_score) => {
    expect(matches({ result }, { ...fixture, home_score, away_score })).toHaveLength(1);
    expect(matches({ result }, { ...fixture, home_score: 1, away_score: 2 })).toHaveLength(result === "AWAY_WON" ? 1 : 0);
  });
  it.each(["SCHEDULED", "LIVE", "HALF_TIME", "POSTPONED", "CANCELLED", "ABANDONED", "SUSPENDED", "INTERRUPTED", "AWARDED"] as const)("excludes %s from actual results even with scores", (status) => {
    expect(matches({ result: "HOME_WON" }, { ...fixture, status })).toHaveLength(0);
  });
  it.each([null, undefined, "UNKNOWN", "EXTRA_TIME", "PENALTY_SHOOTOUT"])("excludes unconfirmed regulation score basis %s", (result_score_basis) => {
    expect(matches({ result: "HOME_WON" }, { ...fixture, result_score_basis })).toHaveLength(0);
  });
  it.each([null, -1, .5, NaN, Infinity])("rejects invalid final score %s on either side", (score) => {
    expect(matches({ result: "DRAW" }, { ...fixture, home_score: score, away_score: score })).toHaveLength(0);
  });
  it("intersects geography, competition, team, status, availability, probability and result", () => {
    const filters = { continent: "Europe", country: "England", competition: "league", team: " arsenal ", status: "FINISHED", forecast: "FORECAST_AVAILABLE", outcome: "home" as const, minimumProbability: 55, result: "HOME_WON" as const };
    expect(matches(filters)).toHaveLength(1);
    for (const changes of [{ continent: "Africa" }, { country: "France" }, { competition: "other" }, { team: "Liverpool" }, { status: "LIVE" }, { forecast: "NOT_ENOUGH_HISTORY" }, { minimumProbability: 56 }, { result: "DRAW" as const }]) expect(matches({ ...filters, ...changes })).toHaveLength(0);
  });
  it.each([["UPCOMING", "SCHEDULED"], ["LIVE", "HALF_TIME"], ["LIVE", "LIVE"], ["FINISHED", "FINISHED"]] as const)("supports %s status for %s", (status, fixtureStatus) => {
    expect(matches({ status }, { ...fixture, status: fixtureStatus })).toHaveLength(1);
  });
  it("removes empty competition groups and never mutates source data", () => {
    const groups = [{ competition: { ...competition, type: "LEAGUE" as const }, fixtures: [fixture] }];
    expect(filterFixtureGroups(groups, { ...DEFAULT_FIXTURE_FILTERS, team: "missing" })).toEqual([]);
    expect(groups[0].fixtures).toEqual([fixture]);
  });
});
