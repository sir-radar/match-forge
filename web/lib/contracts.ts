export type Availability = {
  fixtures: boolean;
  results: boolean;
  standings: boolean;
  h2h: boolean;
  forecast: boolean;
  xg: boolean;
  team_stats: boolean;
};

export type Competition = {
  id: string;
  name: string;
  country: string;
  continent: string;
  division: number | null;
  type: "LEAGUE" | "CUP";
  season: string;
  availability: Availability;
  availability_status: string;
  sources: Record<string, string[]>;
};

export type Team = {
  id: string;
  name: string;
  crest_url: string | null;
};

export type ForecastSummary = {
  id: string;
  expected_home_goals: number;
  expected_away_goals: number;
  probabilities: Record<string, number>;
};

export type Fixture = {
  id: string;
  kickoff_at: string;
  status: string;
  home: Team;
  away: Team;
  home_score: number | null;
  away_score: number | null;
  venue: string | null;
  round: string | null;
  forecast_availability: string;
  forecast: ForecastSummary | null;
};

export type FixtureGroup = { competition: Competition; fixtures: Fixture[] };

export type Forecast = ForecastSummary & {
  fixture_id: string;
  model_label: string;
  model_algorithm_version: string;
  created_at: string;
  football_cutoff: string;
  knowledge_cutoff: string;
  knowledge_mode: string;
  publication_mode: string;
  score_matrix: ScoreCell[];
};

export type ScoreCell = {
  home_goals: number;
  away_goals: number;
  probability: number;
};

export type FormMatch = {
  kickoff_at: string;
  opponent: string;
  venue: "HOME" | "AWAY";
  goals_for: number;
  goals_against: number;
  result: "W" | "D" | "L";
};

export type H2HMatch = {
  kickoff_at: string;
  home_team: string;
  away_team: string;
  home_goals: number;
  away_goals: number;
};

export type Standing = {
  position: number;
  team_id: string;
  team: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
};

export type MatchContext = {
  fixture_id: string;
  home_form: FormMatch[];
  away_form: FormMatch[];
  h2h: H2HMatch[];
  standings: Standing[];
  data_availability: Record<string, boolean>;
};

export type Performance = {
  competition_id: string;
  rating: "UNRATED" | "WATCH" | "GOOD" | "STRONG";
  forecasts: number;
  outcome_hit_rate: number | null;
  brier: number | null;
  log_loss: number | null;
  baseline_brier: number | null;
  baseline_log_loss: number | null;
  exact_score_rate: number | null;
  top_three_score_rate: number | null;
  top_five_score_rate: number | null;
  total_goals_hit_rate: number | null;
  btts_hit_rate: number | null;
  latest_fifty_brier: number | null;
  latest_fifty_log_loss: number | null;
  latest_fifty_baseline_brier: number | null;
  latest_fifty_baseline_log_loss: number | null;
};

export type ExternalPrediction = {
  id: string;
  source: string;
  source_page: string;
  prediction_date: string;
  original_date_text: string;
  collected_at: string;
  fixture_id: string | null;
  kickoff_at: string | null;
  competition: string;
  home_team: string;
  away_team: string;
  market: string;
  selection: string;
  match_status: string;
  matchforge_probability: number | null;
  agreement: "AGREES" | "WEAK_SUPPORT" | "DISAGREES" | "UNABLE_TO_EVALUATE";
};

export type ExternalSource = {
  code: string;
  name: string;
  url: string;
  public_predictions: boolean;
  prediction_date_available: boolean;
  login_required: boolean;
  paid_content: boolean;
  automated_access_status: string;
  adapter_status: string;
  known_issues: string;
  checked_at: string;
  tracked_selections: number;
  settled_hit_rate: number | null;
};

export function parseCompetitions(value: unknown): Competition[] {
  const envelope = object(value, "competitions response");
  return array(envelope.competitions, "competitions").map(parseCompetition);
}

export function parseFixtureGroups(value: unknown): FixtureGroup[] {
  const envelope = object(value, "fixtures response");
  return array(envelope.groups, "groups").map((item) => {
    const group = object(item, "fixture group");
    return {
      competition: parseCompetition(group.competition),
      fixtures: array(group.fixtures, "fixtures").map(parseFixture),
    };
  });
}

export function parseForecast(value: unknown): Forecast {
  const item = object(value, "forecast");
  const summary = parseForecastSummary(item);
  return {
    ...summary,
    fixture_id: text(item.fixture_id, "fixture_id"),
    model_label: text(item.model_label, "model_label"),
    model_algorithm_version: text(item.model_algorithm_version, "model_algorithm_version"),
    created_at: text(item.created_at, "created_at"),
    football_cutoff: text(item.football_cutoff, "football_cutoff"),
    knowledge_cutoff: text(item.knowledge_cutoff, "knowledge_cutoff"),
    knowledge_mode: text(item.knowledge_mode, "knowledge_mode"),
    publication_mode: text(item.publication_mode, "publication_mode"),
    score_matrix: array(item.score_matrix, "score_matrix").map((entry) => {
      const cell = object(entry, "score cell");
      return {
        home_goals: numeric(cell.home_goals, "home_goals"),
        away_goals: numeric(cell.away_goals, "away_goals"),
        probability: probability(cell.probability, "probability"),
      };
    }),
  };
}

export function parseContext(value: unknown): MatchContext {
  const item = object(value, "match context");
  const form = (entry: unknown): FormMatch => {
    const row = object(entry, "form match");
    const result = text(row.result, "result");
    if (!(["W", "D", "L"] as string[]).includes(result)) throw new Error("invalid form result");
    return {
      kickoff_at: text(row.kickoff_at, "kickoff_at"),
      opponent: text(row.opponent, "opponent"),
      venue: text(row.venue, "venue") as "HOME" | "AWAY",
      goals_for: numeric(row.goals_for, "goals_for"),
      goals_against: numeric(row.goals_against, "goals_against"),
      result: result as FormMatch["result"],
    };
  };
  return {
    fixture_id: text(item.fixture_id, "fixture_id"),
    home_form: array(item.home_form, "home_form").map(form),
    away_form: array(item.away_form, "away_form").map(form),
    h2h: array(item.h2h, "h2h").map((entry) => {
      const row = object(entry, "h2h match");
      return {
        kickoff_at: text(row.kickoff_at, "kickoff_at"),
        home_team: text(row.home_team, "home_team"),
        away_team: text(row.away_team, "away_team"),
        home_goals: numeric(row.home_goals, "home_goals"),
        away_goals: numeric(row.away_goals, "away_goals"),
      };
    }),
    standings: array(item.standings, "standings").map(parseStanding),
    data_availability: booleanRecord(item.data_availability, "data_availability"),
  };
}

export function parsePerformance(value: unknown): Performance {
  const item = object(value, "performance");
  const rating = text(item.rating, "rating") as Performance["rating"];
  return {
    competition_id: text(item.competition_id, "competition_id"),
    rating,
    forecasts: numeric(item.forecasts, "forecasts"),
    outcome_hit_rate: nullableNumber(item.outcome_hit_rate, "outcome_hit_rate"),
    brier: nullableNumber(item.brier, "brier"),
    log_loss: nullableNumber(item.log_loss, "log_loss"),
    baseline_brier: nullableNumber(item.baseline_brier, "baseline_brier"),
    baseline_log_loss: nullableNumber(item.baseline_log_loss, "baseline_log_loss"),
    exact_score_rate: nullableNumber(item.exact_score_rate, "exact_score_rate"),
    top_three_score_rate: nullableNumber(item.top_three_score_rate, "top_three_score_rate"),
    top_five_score_rate: nullableNumber(item.top_five_score_rate, "top_five_score_rate"),
    total_goals_hit_rate: nullableNumber(item.total_goals_hit_rate, "total_goals_hit_rate"),
    btts_hit_rate: nullableNumber(item.btts_hit_rate, "btts_hit_rate"),
    latest_fifty_brier: nullableNumber(item.latest_fifty_brier, "latest_fifty_brier"),
    latest_fifty_log_loss: nullableNumber(item.latest_fifty_log_loss, "latest_fifty_log_loss"),
    latest_fifty_baseline_brier: nullableNumber(item.latest_fifty_baseline_brier, "latest_fifty_baseline_brier"),
    latest_fifty_baseline_log_loss: nullableNumber(item.latest_fifty_baseline_log_loss, "latest_fifty_baseline_log_loss"),
  };
}

export function parsePredictions(value: unknown): ExternalPrediction[] {
  const envelope = object(value, "external predictions response");
  return array(envelope.predictions, "predictions").map((entry) => {
    const item = object(entry, "external prediction");
    return {
      id: text(item.id, "id"),
      source: text(item.source, "source"),
      source_page: text(item.source_page, "source_page"),
      prediction_date: text(item.prediction_date, "prediction_date"),
      original_date_text: text(item.original_date_text, "original_date_text"),
      collected_at: text(item.collected_at, "collected_at"),
      fixture_id: nullableText(item.fixture_id, "fixture_id"),
      kickoff_at: nullableText(item.kickoff_at, "kickoff_at"),
      competition: text(item.competition, "competition"),
      home_team: text(item.home_team, "home_team"),
      away_team: text(item.away_team, "away_team"),
      market: text(item.market, "market"),
      selection: text(item.selection, "selection"),
      match_status: text(item.match_status, "match_status"),
      matchforge_probability: nullableNumber(item.matchforge_probability, "matchforge_probability"),
      agreement: text(item.agreement, "agreement") as ExternalPrediction["agreement"],
    };
  });
}

export function parseSources(value: unknown): ExternalSource[] {
  const envelope = object(value, "sources response");
  return array(envelope.sources, "sources").map((entry) => {
    const item = object(entry, "external source");
    return {
      code: text(item.code, "code"),
      name: text(item.name, "name"),
      url: text(item.url, "url"),
      public_predictions: boolean(item.public_predictions, "public_predictions"),
      prediction_date_available: boolean(item.prediction_date_available, "prediction_date_available"),
      login_required: boolean(item.login_required, "login_required"),
      paid_content: boolean(item.paid_content, "paid_content"),
      automated_access_status: text(item.automated_access_status, "automated_access_status"),
      adapter_status: text(item.adapter_status, "adapter_status"),
      known_issues: text(item.known_issues, "known_issues"),
      checked_at: text(item.checked_at, "checked_at"),
      tracked_selections: numeric(item.tracked_selections, "tracked_selections"),
      settled_hit_rate: nullableNumber(item.settled_hit_rate, "settled_hit_rate"),
    };
  });
}

function parseCompetition(value: unknown): Competition {
  const item = object(value, "competition");
  const availability = object(item.availability, "availability");
  return {
    id: text(item.id, "id"),
    name: text(item.name, "name"),
    country: text(item.country, "country"),
    continent: text(item.continent, "continent"),
    division: item.division === null ? null : numeric(item.division, "division"),
    type: text(item.type, "type") as Competition["type"],
    season: text(item.season, "season"),
    availability: {
      fixtures: boolean(availability.fixtures, "fixtures"),
      results: boolean(availability.results, "results"),
      standings: boolean(availability.standings, "standings"),
      h2h: boolean(availability.h2h, "h2h"),
      forecast: boolean(availability.forecast, "forecast"),
      xg: boolean(availability.xg, "xg"),
      team_stats: boolean(availability.team_stats, "team_stats"),
    },
    availability_status: text(item.availability_status, "availability_status"),
    sources: stringArrayRecord(item.sources, "sources"),
  };
}

function parseFixture(value: unknown): Fixture {
  const item = object(value, "fixture");
  return {
    id: text(item.id, "id"),
    kickoff_at: text(item.kickoff_at, "kickoff_at"),
    status: text(item.status, "status"),
    home: parseTeam(item.home),
    away: parseTeam(item.away),
    home_score: nullableNumber(item.home_score, "home_score"),
    away_score: nullableNumber(item.away_score, "away_score"),
    venue: nullableText(item.venue, "venue"),
    round: nullableText(item.round, "round"),
    forecast_availability: text(item.forecast_availability, "forecast_availability"),
    forecast: item.forecast === null ? null : parseForecastSummary(item.forecast),
  };
}

function parseTeam(value: unknown): Team {
  const item = object(value, "team");
  return { id: text(item.id, "id"), name: text(item.name, "name"), crest_url: nullableText(item.crest_url, "crest_url") };
}

function parseForecastSummary(value: unknown): ForecastSummary {
  const item = object(value, "forecast summary");
  return {
    id: text(item.id, "id"),
    expected_home_goals: numeric(item.expected_home_goals, "expected_home_goals"),
    expected_away_goals: numeric(item.expected_away_goals, "expected_away_goals"),
    probabilities: probabilityRecord(item.probabilities, "probabilities"),
  };
}

function parseStanding(value: unknown): Standing {
  const item = object(value, "standing");
  return {
    position: numeric(item.position, "position"), team_id: text(item.team_id, "team_id"),
    team: text(item.team, "team"), played: numeric(item.played, "played"),
    won: numeric(item.won, "won"), drawn: numeric(item.drawn, "drawn"),
    lost: numeric(item.lost, "lost"), goals_for: numeric(item.goals_for, "goals_for"),
    goals_against: numeric(item.goals_against, "goals_against"),
    goal_difference: numeric(item.goal_difference, "goal_difference"), points: numeric(item.points, "points"),
  };
}

function object(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${field} must be an object`);
  return value as Record<string, unknown>;
}
function array(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${field} must be an array`);
  return value;
}
function text(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${field} must be text`);
  return value;
}
function nullableText(value: unknown, field: string): string | null {
  return value === null ? null : text(value, field);
}
function numeric(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${field} must be finite`);
  return value;
}
function nullableNumber(value: unknown, field: string): number | null {
  return value === null ? null : numeric(value, field);
}
function probability(value: unknown, field: string): number {
  const result = numeric(value, field);
  if (result < 0 || result > 1) throw new Error(`${field} must be in [0,1]`);
  return result;
}
function boolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${field} must be boolean`);
  return value;
}
function probabilityRecord(value: unknown, field: string): Record<string, number> {
  return Object.fromEntries(Object.entries(object(value, field)).map(([key, entry]) => [key, probability(entry, `${field}.${key}`)]));
}
function booleanRecord(value: unknown, field: string): Record<string, boolean> {
  return Object.fromEntries(Object.entries(object(value, field)).map(([key, entry]) => [key, boolean(entry, `${field}.${key}`)]));
}
function stringArrayRecord(value: unknown, field: string): Record<string, string[]> {
  return Object.fromEntries(Object.entries(object(value, field)).map(([key, entry]) => [key, array(entry, `${field}.${key}`).map((item) => text(item, `${field}.${key}`))]));
}
