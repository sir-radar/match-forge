import type { Competition, Fixture, FixtureGroup } from "@/lib/contracts";

export type PredictedOutcome = "either" | "home" | "draw" | "away";
export type MatchResult = "ALL" | "HOME_WON" | "AWAY_WON" | "DRAW";
export type FixtureFilters = {
  continent: string; country: string; competition: string; forecast: string;
  team: string; status: string; outcome: PredictedOutcome;
  minimumProbability: number | null; result: MatchResult;
};
export const DEFAULT_FIXTURE_FILTERS: FixtureFilters = {
  continent: "", country: "", competition: "", forecast: "", team: "", status: "ALL",
  outcome: "either", minimumProbability: null, result: "ALL",
};

export function filterFixtureGroups(groups: FixtureGroup[], filters: FixtureFilters): FixtureGroup[] {
  return groups.filter((group) => matchesCompetition(group.competition, filters))
    .map((group) => ({ ...group, fixtures: group.fixtures.filter((fixture) => matchesFixture(fixture, filters)) }))
    .filter((group) => group.fixtures.length > 0);
}

function matchesCompetition(competition: Competition, filters: FixtureFilters) {
  return (!filters.continent || competition.continent === filters.continent)
    && (!filters.country || competition.country === filters.country)
    && (!filters.competition || competition.id === filters.competition);
}

function matchesFixture(fixture: Fixture, filters: FixtureFilters) {
  const query = filters.team.trim().toLocaleLowerCase();
  const matchesTeam = [fixture.home.name, fixture.away.name].some((name) => name.toLocaleLowerCase().includes(query));
  return matchesTeam && matchesStatus(fixture, filters.status)
    && (!filters.forecast || fixture.forecast_availability === filters.forecast)
    && matchesProbability(fixture, filters) && matchesResult(fixture, filters.result);
}

function matchesStatus(fixture: Fixture, status: string) {
  if (status === "ALL") return true;
  if (status === "UPCOMING") return fixture.status === "SCHEDULED";
  if (status === "LIVE") return ["LIVE", "HALF_TIME"].includes(fixture.status);
  return fixture.status === status;
}

function validProbability(value: number) {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

function matchesProbability(fixture: Fixture, { minimumProbability, outcome }: FixtureFilters) {
  if (minimumProbability === null) return true;
  if (!fixture.forecast || fixture.forecast_availability !== "FORECAST_AVAILABLE") return false;
  const probabilities = fixture.forecast.probabilities;
  const values = outcome === "either" ? [probabilities.home, probabilities.away] : [probabilities[outcome]];
  // Compare published values directly; display rounding must not change inclusion.
  return values.every(validProbability) && Math.max(...values) >= minimumProbability / 100;
}

function validScore(score: number | null): score is number {
  return score !== null && Number.isSafeInteger(score) && score >= 0;
}

function matchesResult(fixture: Fixture, result: MatchResult) {
  if (result === "ALL") return true;
  if (fixture.status !== "FINISHED" || fixture.result_score_basis !== "REGULATION_90") return false;
  const { home_score: home, away_score: away } = fixture;
  if (!validScore(home) || !validScore(away)) return false;
  if (result === "HOME_WON") return home > away;
  if (result === "AWAY_WON") return away > home;
  return home === away;
}
