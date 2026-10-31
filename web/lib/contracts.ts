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
  type: "LEAGUE" | "CUP" | "UNKNOWN";
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

const fixtureStatuses = ["SCHEDULED", "LIVE", "HALF_TIME", "FINISHED", "POSTPONED", "CANCELLED", "ABANDONED", "SUSPENDED", "INTERRUPTED", "AWARDED"] as const;

export type Fixture = {
  id: string;
  kickoff_at: string;
  status: (typeof fixtureStatuses)[number];
  home: Team;
  away: Team;
  home_score: number | null;
  away_score: number | null;
  venue: string | null;
  round: string | null;
  forecast_availability: string;
  forecast: ForecastSummary | null;
  provider: string | null;
  provider_status: string | null;
  match_minute: number | null;
  added_time: number | null;
  period: string | null;
  last_successful_update: string | null;
  freshness?: "UNKNOWN" | "FRESH" | "STALE";
  stale: boolean;
  goal_scorers: LiveEvent[];
};

export type FixtureGroup = { competition: Competition; fixtures: Fixture[] };

export type LiveEvent = {
  id: string;
  type: string;
  team_id: string | null;
  team_side: "HOME" | "AWAY" | null;
  player_id: string | null;
  player_name: string | null;
  minute: number | null;
  added_time: number | null;
  period: string | null;
  own_goal: boolean;
  penalty: boolean;
  disallowed: boolean;
  provider: string;
};

export type LiveStatistic = {
  metric: string;
  label: string;
  period: string;
  home: number | null;
  away: number | null;
  unit: string;
  original_field: string;
  available: boolean;
};

export type LiveSource = { freshness?: "UNKNOWN" | "FRESH" | "STALE"; provider: string; provider_match_id: string; observed_at: string; last_fetched_at: string; stale: boolean };

export type LiveMatch = {
  fixture_id: string;
  status: Fixture["status"];
  home: Team;
  away: Team;
  home_score: number | null;
  away_score: number | null;
  match_minute: number | null;
  added_time: number | null;
  period: string | null;
  events: LiveEvent[];
  statistics: LiveStatistic[];
  score_source: LiveSource | null;
  event_source: LiveSource | null;
  statistics_source: LiveSource | null;
  availability: Record<string, boolean>;
  partial: boolean;
};

export type Forecast = ForecastSummary & {
  fixture_id: string;
  model_label: string;
  model_algorithm_version: string;
  created_at: string;
  football_cutoff: string;
  knowledge_cutoff: string;
  knowledge_mode: string;
  publication_mode: string;
  score_matrix_version: "legacy-compact-index-v1" | "compact-buckets-v2";
  score_matrix: ScoreCell[];
};

export type ScoreCell = {
  home_goals: number;
  away_goals: number;
  probability: number;
  home_label: string;
  away_label: string;
  home_bucket_kind: "EXACT" | "AT_LEAST";
  away_bucket_kind: "EXACT" | "AT_LEAST";
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
  home_xg: number | null;
  away_xg: number | null;
};

export type TeamStatistics = {
  recent_matches: number;
  goals_for: number;
  goals_against: number;
  average_goals_for: number;
  average_goals_against: number;
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
  h2h_summary: { meetings: number; home_wins: number; draws: number; away_wins: number; home_goals: number; away_goals: number };
  home_team_statistics: TeamStatistics | null;
  away_team_statistics: TeamStatistics | null;
  standings: Standing[];
  data_availability: Record<string, boolean>;
};

export type Performance = {
  report_status?: "READY" | "EMPTY" | "PENDING" | "FAILED";
  analytics_policy_version: "pre-match-revisions-v2";
  analytics_horizon: "LATEST" | "7D" | "3D" | "24H" | "6H" | "1H" | "15M";
  competition_id: string;
  league: string;
  country: string;
  continent: string;
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

export type Pagination = { page: number; page_size: 20 | 50 | 100; total_items: number; total_pages: number };

export type PerformancePage = {
  performance: Performance[];
  pagination: Pagination;
};

export type ExternalPrediction = {
  source_code?: string;
  fixture_identity_status?: string | null;
  source_date_status?: string;
  source_revision_conflict?: boolean;
  comparison_status?: "READY" | "PENDING" | "FAILED" | "UNSUPPORTED" | "NO_FORECAST" | "UNMATCHED" | "QUARANTINED";
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
  settlement_state: "WON" | "LOST" | "VOID" | "PENDING";
  actual_home_score: number | null;
  actual_away_score: number | null;
  result_score_basis: string | null;
  result_provider: string | null;
  result_updated_at: string | null;
};

export type ExternalSource = {
  prospectively_captured_selections?: number;
  retrospectively_captured_selections?: number;
  last_collection_at?: string | null;
  last_collection_status?: string | null;
  collection_error?: string | null;
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
  settled_selections: number;
  correct_selections: number;
  settled_hit_rate: number | null;
  matchforge_agreement_rate: number | null;
};

export type SyncType = "MVP_SYNC" | "OPENFOOTBALL" | "FOOTBALL_DATA_UK" | "HISTORY_BACKFILL" | "FORECAST_REFRESH" | "CONTEXT_REPORTS" | "PUBLIC_REPORTS" | "EXTERNAL_PREDICTIONS" | "FOTMOB_SYNC" | "PITCHAPI_SYNC" | "ALL_DATA";
export type SyncStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type HistoryQueueProgress = {
  total: number;
  pending: number;
  running: number;
  succeeded: number;
  failed: number;
};
export type SyncRun = {
  run_id: string;
  sync_type: SyncType;
  status: SyncStatus;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
  requested_date: string | null;
  parameters: Record<string, unknown>;
  summary: Record<string, unknown>;
  error_message: string | null;
  log_path: string | null;
  history_queue?: HistoryQueueProgress;
};
export type HistoricalCoverage = {
  provider_history?: ProviderHistoryProgress[];
  eligible_history: number;
  excluded_history: number;
  provisional_fixtures: number;
  verified_provider_matches: number;
  identity_conflicts: number;
  historical_matches: number;
  competitions_with_history: number;
  teams_with_10_matches: number;
  teams_below_10_matches: number;
  scheduled_fixtures: number;
  forecast_available: number;
  not_enough_history: number;
  forecast_refresh_pending?: number;
  forecast_refresh_complete?: number;
  mapping_failures: number;
  source_conflicts: number;
  missing_live_scores: number;
  fotmob_mapped: number;
  fotmob_unmapped: number;
  pitchapi_mapped: number;
  pitchapi_unmapped: number;
  fotmob_history: number;
  pitchapi_history: number;
  api_football_requests_used: number;
  api_football_remaining: number;
  api_football_exhausted: boolean;
};
export type ProviderConfiguration = {
  history_sync_enabled?: boolean;
  history_sync_interval?: string;
  fotmob_enabled: boolean;
  pitchapi_enabled: boolean;
  operational_sync_interval: string;
};
export type ProviderHistoryProgress = {
  provider: "fotmob" | "pitchapi";
  pending: number; running: number; completed: number; failed: number; deferred: number;
  oldest_pending_observed_at: string | null;
  completions_24_hours: number; observed_seconds: number;
  requests_used: number; historical_requests_used: number;
  remaining_requests: number | null; exhausted: boolean; deferred_until: string | null;
  completions_per_hour: number | null; estimated_drain_hours: number | null;
};
export type SyncRunsResponse = { runs: SyncRun[]; coverage: HistoricalCoverage; provider_configuration: ProviderConfiguration };

export function parseCompetitions(value: unknown): Competition[] {
  const envelope = object(value, "competitions response");
  return array(envelope.competitions, "competitions").map(parseCompetition);
}

export function parseFixtureGroups(value: unknown): FixtureGroup[] {
  const envelope = object(value, "fixtures response");
  const competitionIds = new Set<string>(), fixtureIds = new Set<string>();
  return array(envelope.groups, "groups").map((item) => {
    const group = object(item, "fixture group");
    const competition = parseCompetition(group.competition);
    if (competitionIds.has(competition.id)) throw new Error("duplicate competition identity");
    competitionIds.add(competition.id);
    const fixtures = array(group.fixtures, "fixtures").map(parseFixture);
    for (const fixture of fixtures) {
      if (fixtureIds.has(fixture.id)) throw new Error("duplicate fixture identity");
      fixtureIds.add(fixture.id);
    }
    return { competition, fixtures };
  });
}

export function parseLiveMatch(value: unknown): LiveMatch {
  const item = object(value, "live match");
  return {
    fixture_id: text(item.fixture_id, "fixture_id"), status: parseFixtureStatus(item.status),
    home: parseTeam(item.home), away: parseTeam(item.away),
    home_score: nullableNumber(item.home_score, "home_score"), away_score: nullableNumber(item.away_score, "away_score"),
    match_minute: nullableNumber(item.match_minute, "match_minute"), added_time: nullableNumber(item.added_time, "added_time"),
    period: nullableText(item.period, "period"),
    events: array(item.events, "events").map(parseLiveEvent),
    statistics: array(item.statistics, "statistics").map(parseLiveStatistic),
    score_source: item.score_source === null ? null : parseLiveSource(item.score_source),
    event_source: item.event_source === null ? null : parseLiveSource(item.event_source),
    statistics_source: item.statistics_source === null ? null : parseLiveSource(item.statistics_source),
    availability: booleanRecord(item.availability, "availability"),
    partial: boolean(item.partial, "partial"),
  };
}

export function parseForecast(value: unknown): Forecast {
  const item = object(value, "forecast");
  const summary = parseForecastSummary(item);
  const algorithm = text(item.model_algorithm_version, "model_algorithm_version");
  const version = scoreMatrixVersion(item.score_matrix_version, algorithm);
  return {
    ...summary,
    fixture_id: text(item.fixture_id, "fixture_id"),
    model_label: text(item.model_label, "model_label"),
    model_algorithm_version: algorithm,
    created_at: timestamp(item.created_at, "created_at"),
    football_cutoff: timestamp(item.football_cutoff, "football_cutoff"),
    knowledge_cutoff: timestamp(item.knowledge_cutoff, "knowledge_cutoff"),
    knowledge_mode: text(item.knowledge_mode, "knowledge_mode"),
    publication_mode: text(item.publication_mode, "publication_mode"),
    score_matrix_version: version,
    score_matrix: array(item.score_matrix, "score_matrix").map((entry) => parseScoreCell(entry, version)),
  };
}

function scoreMatrixVersion(value: unknown, algorithm: string): Forecast["score_matrix_version"] {
  if (value === "compact-buckets-v2" || value === "legacy-compact-index-v1") return value;
  if (value === undefined && ["transferable-rolling-goals-poisson-v1", "transferable-rolling-goals-poisson-v1-rolling10-v2"].includes(algorithm)) return "legacy-compact-index-v1";
  throw new Error("unsupported score_matrix_version");
}

function parseScoreCell(value: unknown, version: Forecast["score_matrix_version"]): ScoreCell {
  const cell = object(value, "score cell");
  const home = parseScoreBucket(cell, "home", version);
  const away = parseScoreBucket(cell, "away", version);
  return {
    home_goals: home.goals, away_goals: away.goals,
    home_label: home.label, away_label: away.label,
    home_bucket_kind: home.kind, away_bucket_kind: away.kind,
    probability: probability(cell.probability, "probability"),
  };
}

function parseScoreBucket(cell: Record<string, unknown>, side: "home" | "away", version: Forecast["score_matrix_version"]): { goals: number; label: string; kind: ScoreCell["home_bucket_kind"] } {
  const goals = integer(cell[`${side}_goals`], `${side}_goals`, 0);
  if (version === "legacy-compact-index-v1") {
    if (goals > 5) throw new Error("invalid legacy score bucket");
    return { goals, label: goals === 5 ? "5+" : String(goals), kind: goals === 5 ? "AT_LEAST" as const : "EXACT" as const };
  }
  const kind = text(cell[`${side}_bucket_kind`], `${side}_bucket_kind`);
  if (kind !== "EXACT" && kind !== "AT_LEAST") throw new Error(`invalid ${side}_bucket_kind`);
  const label = text(cell[`${side}_label`], `${side}_label`);
  if (label !== `${goals}${kind === "AT_LEAST" ? "+" : ""}`) throw new Error(`inconsistent ${side}_label`);
  return { goals, label, kind };
}

export function parseContext(value: unknown): MatchContext {
  const item = object(value, "match context");
  const form = (entry: unknown): FormMatch => {
    const row = object(entry, "form match");
    const result = text(row.result, "result");
    if (!(["W", "D", "L"] as string[]).includes(result)) throw new Error("invalid form result");
    const venue = row.venue;
    if (venue !== "HOME" && venue !== "AWAY") throw new Error("invalid form venue");
    return {
      kickoff_at: timestamp(row.kickoff_at, "kickoff_at"),
      opponent: text(row.opponent, "opponent"),
      venue,
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
        kickoff_at: timestamp(row.kickoff_at, "kickoff_at"),
        home_team: text(row.home_team, "home_team"),
        away_team: text(row.away_team, "away_team"),
        home_goals: numeric(row.home_goals, "home_goals"),
        away_goals: numeric(row.away_goals, "away_goals"),
        home_xg: nullableNumber(row.home_xg, "home_xg"),
        away_xg: nullableNumber(row.away_xg, "away_xg"),
      };
    }),
    h2h_summary: parseH2HSummary(item.h2h_summary),
    home_team_statistics: item.home_team_statistics === null ? null : parseTeamStatistics(item.home_team_statistics),
    away_team_statistics: item.away_team_statistics === null ? null : parseTeamStatistics(item.away_team_statistics),
    standings: array(item.standings, "standings").map(parseStanding),
    data_availability: booleanRecord(item.data_availability, "data_availability"),
  };
}

export function parsePerformance(value: unknown): Performance {
  const item = object(value, "performance");
  const reportStatus = item.report_status === undefined ? undefined : text(item.report_status, "report_status");
  if (reportStatus && !["READY", "EMPTY", "PENDING", "FAILED"].includes(reportStatus)) throw new Error("invalid report_status");
  const rating = text(item.rating, "rating") as Performance["rating"];
  if (!["UNRATED", "WATCH", "GOOD", "STRONG"].includes(rating)) throw new Error("invalid rating");
  if (item.analytics_policy_version !== "pre-match-revisions-v2") throw new Error("unsupported analytics policy");
  const horizon = text(item.analytics_horizon, "analytics_horizon") as Performance["analytics_horizon"];
  if (!["LATEST", "7D", "3D", "24H", "6H", "1H", "15M"].includes(horizon)) throw new Error("invalid analytics horizon");
  return {
    report_status: reportStatus as Performance["report_status"],
    analytics_policy_version: "pre-match-revisions-v2", analytics_horizon: horizon,
    competition_id: text(item.competition_id, "competition_id"),
    league: text(item.league, "league"),
    country: text(item.country, "country"),
    continent: text(item.continent, "continent"),
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

function parsePagination(value: unknown): Pagination {
  const pagination = object(value, "pagination");
  const page = integer(pagination.page, "page", 1);
  const pageSize = integer(pagination.page_size, "page_size", 1);
  const totalItems = integer(pagination.total_items, "total_items", 0);
  const totalPages = integer(pagination.total_pages, "total_pages", 0);
  if (pageSize !== 20 && pageSize !== 50 && pageSize !== 100) throw new Error("page_size must be 20, 50, or 100");
  if (totalItems === 0 && totalPages !== 0) throw new Error("total_pages must be 0 when total_items is 0");
  if (totalItems > 0 && (totalPages < 1 || page > totalPages)) throw new Error("pagination page range is invalid");
  if (totalPages !== Math.ceil(totalItems / pageSize)) throw new Error("pagination total_pages is inconsistent");
  return { page, page_size: pageSize, total_items: totalItems, total_pages: totalPages };
}

export function parsePerformanceList(value: unknown): PerformancePage {
  const envelope = object(value, "performance response");
  return { performance: array(envelope.performance, "performance").map(parsePerformance), pagination: parsePagination(envelope.pagination) };
}

function parseH2HSummary(value: unknown): MatchContext["h2h_summary"] {
  const item = object(value, "h2h summary");
  return { meetings: numeric(item.meetings, "meetings"), home_wins: numeric(item.home_wins, "home_wins"), draws: numeric(item.draws, "draws"), away_wins: numeric(item.away_wins, "away_wins"), home_goals: numeric(item.home_goals, "home_goals"), away_goals: numeric(item.away_goals, "away_goals") };
}

function parseTeamStatistics(value: unknown): TeamStatistics {
  const item = object(value, "team statistics");
  return { recent_matches: numeric(item.recent_matches, "recent_matches"), goals_for: numeric(item.goals_for, "goals_for"), goals_against: numeric(item.goals_against, "goals_against"), average_goals_for: numeric(item.average_goals_for, "average_goals_for"), average_goals_against: numeric(item.average_goals_against, "average_goals_against") };
}

export function parsePredictions(value: unknown): ExternalPrediction[] {
  const envelope = object(value, "external predictions response");
  return array(envelope.predictions, "predictions").map((entry) => {
    const item = object(entry, "external prediction");
    const comparisonStatus = parseComparisonStatus(item.comparison_status);
    const agreement = parseAgreement(item.agreement);
    const settlement = item.settlement_state === undefined ? "PENDING" : text(item.settlement_state, "settlement_state");
    if (!["WON", "LOST", "VOID", "PENDING"].includes(settlement)) throw new Error("invalid settlement_state");
    return {
      id: text(item.id, "id"),
      ...parseExternalIdentity(item),
      source: text(item.source, "source"),
      source_page: text(item.source_page, "source_page"),
      prediction_date: text(item.prediction_date, "prediction_date"),
      original_date_text: text(item.original_date_text, "original_date_text"),
      collected_at: timestamp(item.collected_at, "collected_at"),
      fixture_id: nullableText(item.fixture_id, "fixture_id"),
      kickoff_at: nullableTimestamp(item.kickoff_at, "kickoff_at"),
      competition: text(item.competition, "competition"),
      home_team: text(item.home_team, "home_team"),
      away_team: text(item.away_team, "away_team"),
      market: text(item.market, "market"),
      selection: text(item.selection, "selection"),
      match_status: text(item.match_status, "match_status"),
      matchforge_probability: item.matchforge_probability === null ? null : probability(item.matchforge_probability, "matchforge_probability"),
      comparison_status: comparisonStatus as ExternalPrediction["comparison_status"],
      agreement: agreement as ExternalPrediction["agreement"],
      settlement_state: settlement as ExternalPrediction["settlement_state"],
      actual_home_score: item.actual_home_score === undefined ? null : nullableNumber(item.actual_home_score, "actual_home_score"),
      actual_away_score: item.actual_away_score === undefined ? null : nullableNumber(item.actual_away_score, "actual_away_score"),
      result_score_basis: item.result_score_basis === undefined ? null : nullableText(item.result_score_basis, "result_score_basis"),
      result_provider: item.result_provider === undefined ? null : nullableText(item.result_provider, "result_provider"),
      result_updated_at: item.result_updated_at === undefined ? null : nullableTimestamp(item.result_updated_at, "result_updated_at"),
    };
  });
}

export function parseSources(value: unknown): ExternalSource[] {
  const envelope = object(value, "sources response");
  return array(envelope.sources, "sources").map((entry) => {
    const item = object(entry, "external source");
    return {
      prospectively_captured_selections: item.prospectively_captured_selections === undefined ? undefined : integer(item.prospectively_captured_selections, "prospectively_captured_selections", 0),
      retrospectively_captured_selections: item.retrospectively_captured_selections === undefined ? undefined : integer(item.retrospectively_captured_selections, "retrospectively_captured_selections", 0),
      last_collection_at: item.last_collection_at === undefined ? undefined : nullableTimestamp(item.last_collection_at, "last_collection_at"),
      last_collection_status: item.last_collection_status === undefined ? undefined : nullableText(item.last_collection_status, "last_collection_status"),
      collection_error: item.collection_error === undefined ? undefined : nullableText(item.collection_error, "collection_error"),
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
      settled_selections: numeric(item.settled_selections, "settled_selections"),
      correct_selections: numeric(item.correct_selections, "correct_selections"),
      settled_hit_rate: nullableNumber(item.settled_hit_rate, "settled_hit_rate"),
      matchforge_agreement_rate: nullableNumber(item.matchforge_agreement_rate, "matchforge_agreement_rate"),
    };
  });
}

export function parseSyncRun(value: unknown): SyncRun {
  const item = object(value, "sync run");
  const syncType = text(item.sync_type, "sync_type") as SyncType;
  const status = text(item.status, "status") as SyncStatus;
  if (!["MVP_SYNC", "OPENFOOTBALL", "FOOTBALL_DATA_UK", "HISTORY_BACKFILL", "FORECAST_REFRESH", "CONTEXT_REPORTS", "PUBLIC_REPORTS", "EXTERNAL_PREDICTIONS", "FOTMOB_SYNC", "PITCHAPI_SYNC", "ALL_DATA"].includes(syncType)) throw new Error("invalid sync_type");
  if (!["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"].includes(status)) throw new Error("invalid sync status");
  const historyQueue = item.history_queue === undefined ? undefined : object(item.history_queue, "history_queue");
  return {
    run_id: text(item.run_id, "run_id"), sync_type: syncType, status,
    requested_at: text(item.requested_at, "requested_at"),
    started_at: nullableText(item.started_at, "started_at"),
    finished_at: nullableText(item.finished_at, "finished_at"),
    requested_date: nullableText(item.requested_date, "requested_date"),
    parameters: object(item.parameters, "parameters"), summary: object(item.summary, "summary"),
    error_message: nullableText(item.error_message, "error_message"),
    log_path: nullableText(item.log_path, "log_path"),
    history_queue: historyQueue ? {
      total: numeric(historyQueue.total, "history_queue.total"),
      pending: numeric(historyQueue.pending, "history_queue.pending"),
      running: numeric(historyQueue.running, "history_queue.running"),
      succeeded: numeric(historyQueue.succeeded, "history_queue.succeeded"),
      failed: numeric(historyQueue.failed, "history_queue.failed"),
    } : undefined,
  };
}

export function parseSyncRuns(value: unknown): SyncRunsResponse {
  const envelope = object(value, "sync runs response");
  const coverage = object(envelope.coverage, "coverage");
  const providerConfiguration = envelope.provider_configuration === undefined ? null : object(envelope.provider_configuration, "provider_configuration");
  return {
    runs: array(envelope.runs, "runs").map(parseSyncRun),
    provider_configuration: providerConfiguration ? {
      fotmob_enabled: boolean(providerConfiguration.fotmob_enabled, "fotmob_enabled"),
      pitchapi_enabled: boolean(providerConfiguration.pitchapi_enabled, "pitchapi_enabled"),
      operational_sync_interval: text(providerConfiguration.operational_sync_interval, "operational_sync_interval"),
      history_sync_enabled: providerConfiguration.history_sync_enabled === undefined ? undefined : boolean(providerConfiguration.history_sync_enabled, "history_sync_enabled"),
      history_sync_interval: providerConfiguration.history_sync_interval === undefined ? undefined : text(providerConfiguration.history_sync_interval, "history_sync_interval"),
    } : { fotmob_enabled: false, pitchapi_enabled: false, operational_sync_interval: "0s" },
    coverage: {
      provider_history: coverage.provider_history == null ? undefined : array(coverage.provider_history, "provider_history").map(parseProviderHistory),
      historical_matches: numeric(coverage.historical_matches, "historical_matches"),
      competitions_with_history: numeric(coverage.competitions_with_history, "competitions_with_history"),
      teams_with_10_matches: numeric(coverage.teams_with_10_matches, "teams_with_10_matches"),
      teams_below_10_matches: numeric(coverage.teams_below_10_matches, "teams_below_10_matches"),
      scheduled_fixtures: numeric(coverage.scheduled_fixtures, "scheduled_fixtures"),
      forecast_available: numeric(coverage.forecast_available, "forecast_available"),
      not_enough_history: numeric(coverage.not_enough_history, "not_enough_history"),
      forecast_refresh_pending: coverage.forecast_refresh_pending === undefined ? undefined : integer(coverage.forecast_refresh_pending, "forecast_refresh_pending", 0),
      forecast_refresh_complete: coverage.forecast_refresh_complete === undefined ? undefined : integer(coverage.forecast_refresh_complete, "forecast_refresh_complete", 0),
      mapping_failures: numeric(coverage.mapping_failures, "mapping_failures"),
      source_conflicts: numeric(coverage.source_conflicts, "source_conflicts"),
      missing_live_scores: numeric(coverage.missing_live_scores, "missing_live_scores"),
      fotmob_mapped: numeric(coverage.fotmob_mapped, "fotmob_mapped"),
      fotmob_unmapped: numeric(coverage.fotmob_unmapped, "fotmob_unmapped"),
      pitchapi_mapped: numeric(coverage.pitchapi_mapped, "pitchapi_mapped"),
      pitchapi_unmapped: numeric(coverage.pitchapi_unmapped, "pitchapi_unmapped"),
      fotmob_history: numeric(coverage.fotmob_history, "fotmob_history"),
      pitchapi_history: numeric(coverage.pitchapi_history, "pitchapi_history"),
      eligible_history: numeric(coverage.eligible_history, "eligible_history"),
      excluded_history: numeric(coverage.excluded_history, "excluded_history"),
      provisional_fixtures: numeric(coverage.provisional_fixtures, "provisional_fixtures"),
      verified_provider_matches: numeric(coverage.verified_provider_matches, "verified_provider_matches"),
      identity_conflicts: numeric(coverage.identity_conflicts, "identity_conflicts"),
      api_football_requests_used: numeric(coverage.api_football_requests_used, "api_football_requests_used"),
      api_football_remaining: numeric(coverage.api_football_remaining, "api_football_remaining"),
      api_football_exhausted: boolean(coverage.api_football_exhausted, "api_football_exhausted"),
    },
  };
}

function parseProviderHistory(value: unknown): ProviderHistoryProgress {
  const item = object(value, "provider history");
  const provider = text(item.provider, "provider");
  if (provider !== "fotmob" && provider !== "pitchapi") throw new Error("invalid history provider");
  return {
    provider,
    pending: integer(item.pending, "pending", 0), running: integer(item.running, "running", 0),
    completed: integer(item.completed, "completed", 0), failed: integer(item.failed, "failed", 0),
    deferred: integer(item.deferred, "deferred", 0),
    oldest_pending_observed_at: nullableTimestamp(item.oldest_pending_observed_at, "oldest_pending_observed_at"),
    completions_24_hours: integer(item.completions_24_hours, "completions_24_hours", 0),
    observed_seconds: nonNegativeNumber(item.observed_seconds, "observed_seconds"),
    requests_used: integer(item.requests_used, "requests_used", 0),
    historical_requests_used: integer(item.historical_requests_used, "historical_requests_used", 0),
    remaining_requests: item.remaining_requests === null ? null : integer(item.remaining_requests, "remaining_requests", 0),
    exhausted: boolean(item.exhausted, "exhausted"),
    deferred_until: nullableTimestamp(item.deferred_until, "deferred_until"),
    completions_per_hour: item.completions_per_hour === null ? null : nonNegativeNumber(item.completions_per_hour, "completions_per_hour"),
    estimated_drain_hours: item.estimated_drain_hours === null ? null : nonNegativeNumber(item.estimated_drain_hours, "estimated_drain_hours"),
  };
}

function nonNegativeNumber(value: unknown, field: string): number {
  const result = numeric(value, field);
  if (result < 0) throw new Error(`${field} must be non-negative`);
  return result;
}

function nullableTimestamp(value: unknown, field: string): string | null {
  return value === null ? null : timestamp(value, field);
}

function timestamp(value: unknown, field: string): string {
  const result = text(value, field);
  if (!/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(result) || !Number.isFinite(Date.parse(result))) throw new Error(`${field} must be a timestamp with a timezone`);
  return result;
}

function parseFixtureStatus(value: unknown): Fixture["status"] {
  const status = fixtureStatuses.find((status) => status === value);
  if (status === undefined) throw new Error("invalid fixture status");
  return status;
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
    kickoff_at: timestamp(item.kickoff_at, "kickoff_at"),
    status: parseFixtureStatus(item.status),
    home: parseTeam(item.home),
    away: parseTeam(item.away),
    home_score: nullableNumber(item.home_score, "home_score"),
    away_score: nullableNumber(item.away_score, "away_score"),
    venue: nullableText(item.venue, "venue"),
    round: nullableText(item.round, "round"),
    forecast_availability: text(item.forecast_availability, "forecast_availability"),
    forecast: item.forecast === null ? null : parseForecastSummary(item.forecast),
    provider: item.provider === undefined ? null : nullableText(item.provider, "provider"),
    provider_status: item.provider_status === undefined ? null : nullableText(item.provider_status, "provider_status"),
    match_minute: item.match_minute === undefined ? null : nullableNumber(item.match_minute, "match_minute"),
    added_time: item.added_time === undefined ? null : nullableNumber(item.added_time, "added_time"),
    period: item.period === undefined ? null : nullableText(item.period, "period"),
    last_successful_update: item.last_successful_update === undefined ? null : nullableTimestamp(item.last_successful_update, "last_successful_update"),
    freshness: parseFreshness(item.freshness),
    stale: item.stale === undefined ? false : boolean(item.stale, "stale"),
    goal_scorers: item.goal_scorers === undefined ? [] : array(item.goal_scorers, "goal_scorers").map(parseLiveEvent),
  };
}

function parseLiveEvent(value: unknown): LiveEvent {
  const item = object(value, "live event");
  const side = item.team_side === null ? null : text(item.team_side, "team_side");
  if (side !== null && side !== "HOME" && side !== "AWAY") throw new Error("invalid team_side");
  return {
    id: text(item.id, "id"), type: text(item.type, "type"),
    team_id: nullableText(item.team_id, "team_id"), team_side: side,
    player_id: nullableText(item.player_id, "player_id"), player_name: nullableText(item.player_name, "player_name"),
    minute: nullableNumber(item.minute, "minute"), added_time: nullableNumber(item.added_time, "added_time"),
    period: nullableText(item.period, "period"), own_goal: boolean(item.own_goal, "own_goal"),
    penalty: boolean(item.penalty, "penalty"), disallowed: boolean(item.disallowed, "disallowed"),
    provider: text(item.provider, "provider"),
  };
}

function parseLiveStatistic(value: unknown): LiveStatistic {
  const item = object(value, "live statistic");
  return { metric: text(item.metric, "metric"), label: text(item.label, "label"), period: text(item.period, "period"), home: nullableNumber(item.home, "home"), away: nullableNumber(item.away, "away"), unit: text(item.unit, "unit"), original_field: text(item.original_field, "original_field"), available: boolean(item.available, "available") };
}

function parseLiveSource(value: unknown): LiveSource {
  const item = object(value, "live source");
  return { freshness: parseFreshness(item.freshness), provider: text(item.provider, "provider"), provider_match_id: text(item.provider_match_id, "provider_match_id"), observed_at: timestamp(item.observed_at, "observed_at"), last_fetched_at: timestamp(item.last_fetched_at, "last_fetched_at"), stale: boolean(item.stale, "stale") };
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
function integer(value: unknown, field: string, minimum: number): number {
  const result = numeric(value, field);
  if (!Number.isInteger(result) || result < minimum) throw new Error(`${field} must be an integer of at least ${minimum}`);
  return result;
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

export type ForecastRevision = {
  forecast_id: string; fixture_id: string; issued_at: string; football_cutoff: string; knowledge_cutoff: string;
  forecast_horizon: string; supersedes_forecast_id: string | null; model_id: string; artifact_sha256: string;
  predictive_input_snapshot_sha256: string; context_snapshot_sha256: string; payload_sha256: string;
  revision_reason_codes: string[]; new_information_ids: string[]; probability_payload: Forecast;
};

export function parseForecastHistory(value: unknown): ForecastRevision[] {
  const envelope = object(value, "forecast history");
  return array(envelope.forecasts, "forecasts").map((value) => {
    const item = object(value, "forecast revision");
    const model = text(item.model_id, "model_id");
    const checksum = (field: string) => { const value = text(item[field], field); if (!/^[0-9a-f]{64}$/.test(value)) throw new Error(`invalid ${field}`); return value; };
    const id = text(item.forecast_id, "forecast_id");
    const fixture = text(item.fixture_id, "fixture_id");
    const issued = timestamp(item.issued_at, "issued_at"), football = timestamp(item.football_cutoff, "football_cutoff"), knowledge = timestamp(item.knowledge_cutoff, "knowledge_cutoff");
    const payload = object(item.probability_payload, "probability_payload");
    return {
      forecast_id: id, fixture_id: fixture, issued_at: issued, football_cutoff: football, knowledge_cutoff: knowledge,
      forecast_horizon: text(item.forecast_horizon, "forecast_horizon"), supersedes_forecast_id: nullableText(item.supersedes_forecast_id, "supersedes_forecast_id"),
      model_id: model, artifact_sha256: checksum("artifact_sha256"), predictive_input_snapshot_sha256: checksum("predictive_input_snapshot_sha256"),
      context_snapshot_sha256: checksum("context_snapshot_sha256"), payload_sha256: checksum("payload_sha256"),
      revision_reason_codes: array(item.revision_reason_codes, "revision_reason_codes").map((value) => text(value, "revision reason")),
      new_information_ids: array(item.new_information_ids, "new_information_ids").map((value) => text(value, "information ID")),
      probability_payload: parseForecast({ ...payload, id, fixture_id: fixture, model_label: "MVP_FORECAST", model_algorithm_version: model,
        created_at: issued, football_cutoff: football, knowledge_cutoff: knowledge, knowledge_mode: "bitemporal", publication_mode: "MVP_OWNER_AUTHORIZED" }),
    };
  });
}

function parseFreshness(value: unknown): "UNKNOWN" | "FRESH" | "STALE" {
  if (value === undefined) return "UNKNOWN";
  if (value !== "UNKNOWN" && value !== "FRESH" && value !== "STALE") throw new Error("invalid freshness");
  return value;
}

function parseComparisonStatus(value: unknown): ExternalPrediction["comparison_status"] {
  if (value === undefined) return undefined;
  const status = text(value, "comparison_status");
  if (!["READY", "PENDING", "FAILED", "UNSUPPORTED", "NO_FORECAST", "UNMATCHED", "QUARANTINED"].includes(status)) throw new Error("invalid comparison_status");
  return status as ExternalPrediction["comparison_status"];
}

export type ExternalConsensus = { id: string; fixture: string; market: string; kickoff: string; selection: string; count: number; total: number; agreement: ExternalPrediction["agreement"] };
export type ExternalPredictionPage = { predictions: ExternalPrediction[]; pagination: Pagination; consensus: ExternalConsensus[] };

function parseAgreement(value: unknown): ExternalPrediction["agreement"] {
  const agreement = text(value, "agreement");
  if (!["AGREES", "WEAK_SUPPORT", "DISAGREES", "UNABLE_TO_EVALUATE"].includes(agreement)) throw new Error("invalid agreement");
  return agreement as ExternalPrediction["agreement"];
}

export function parsePredictionPage(value: unknown): ExternalPredictionPage {
  const envelope = object(value, "prediction page");
  const predictions = parsePredictions(value);
  const pagination = parsePagination(envelope.pagination);
  if (predictions.length > pagination.page_size) throw new Error("prediction page exceeds row bound");
  const consensus = array(envelope.consensus, "consensus").map((entry) => {
    const item = object(entry, "consensus item");
    const count = integer(item.count, "count", 2), total = integer(item.total, "total", 2);
    if (count > total || count * 2 <= total) throw new Error("invalid consensus majority");
    return { id: text(item.id, "id"), fixture: text(item.fixture, "fixture"), market: text(item.market, "market"), kickoff: timestamp(item.kickoff, "kickoff"), selection: text(item.selection, "selection"), count, total, agreement: parseAgreement(item.agreement) };
  });
  if (consensus.length > 3) throw new Error("consensus exceeds group bound");
  return { predictions, pagination, consensus };
}

function parseExternalIdentity(item: Record<string, unknown>) {
  return {
    source_code: item.source_code === undefined ? undefined : text(item.source_code, "source_code"),
    fixture_identity_status: item.fixture_identity_status === undefined ? undefined : nullableText(item.fixture_identity_status, "fixture_identity_status"),
    source_date_status: item.source_date_status === undefined ? undefined : text(item.source_date_status, "source_date_status"),
    source_revision_conflict: item.source_revision_conflict === undefined ? undefined : boolean(item.source_revision_conflict, "source_revision_conflict"),
  };
}
