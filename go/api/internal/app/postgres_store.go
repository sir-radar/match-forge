package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type PostgresProductStore struct {
	pool *pgxpool.Pool
}

func NewPostgresProductStore(pool *pgxpool.Pool) *PostgresProductStore {
	return &PostgresProductStore{pool: pool}
}

func (store *PostgresProductStore) Competitions(ctx context.Context, filters CompetitionFilters) ([]Competition, error) {
	query := `
		SELECT competition_id::text, name, COALESCE(geographic_scope, country), continent, division,
		       competition_type, season_label, fixtures_available, results_available,
		       standings_available, h2h_available, forecast_available, xg_available,
		       team_stats_available, availability_status, source_roles
		FROM football.product_competitions
		WHERE lower(btrim(season_label)) <> 'unknown'`
	args := []any{}
	query = addFilter(query, &args, "continent", filters.Continent)
	query = addFilter(query, &args, "COALESCE(geographic_scope, country)", filters.Country)
	if filters.Division > 0 {
		args = append(args, filters.Division)
		query += fmt.Sprintf(" AND division = $%d", len(args))
	}
	if filters.ForecastAvailable != nil {
		args = append(args, *filters.ForecastAvailable)
		query += fmt.Sprintf(" AND forecast_available = $%d", len(args))
	}
	query += " ORDER BY continent, COALESCE(geographic_scope, country), division NULLS LAST, name"
	rows, err := store.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, scanCompetition)
}

func (store *PostgresProductStore) Fixtures(ctx context.Context, filters FixtureFilters) ([]FixtureGroup, error) {
	query := `
		SELECT pc.competition_id::text, pc.name, COALESCE(pc.geographic_scope, pc.country), pc.continent, pc.division,
		       pc.competition_type, pc.season_label, pc.fixtures_available,
		       pc.results_available, pc.standings_available, pc.h2h_available,
		       pc.forecast_available, pc.xg_available, pc.team_stats_available,
		       pc.availability_status, pc.source_roles,
		       pf.fixture_id::text, pf.kickoff_at,
		       COALESCE(observation.canonical_status, pf.status),
		       ht.team_id::text, ht.name, ht.crest_url,
		       at.team_id::text, at.name, at.crest_url,
		       COALESCE(observation.home_score, pf.home_score),
		       COALESCE(observation.away_score, pf.away_score), pf.venue, pf.round_name,
		       pf.forecast_availability,
		       forecast.forecast_id::text, forecast.expected_home_goals,
		       forecast.expected_away_goals, forecast.probabilities,
		       observation.provider_code, observation.provider_status,
		       observation.match_minute, observation.added_time, observation.period,
		       observation.observed_at, COALESCE(observation.stale_after < clock_timestamp(), false),
		       COALESCE(event_resource.payload->'events', '[]'::jsonb), event_resource.provider_code
		FROM football.product_serving_fixtures pf
		JOIN football.product_competitions pc ON pc.competition_id = pf.competition_id
		JOIN football.product_teams ht ON ht.team_id = pf.home_team_id
		JOIN football.product_teams at ON at.team_id = pf.away_team_id
		LEFT JOIN LATERAL (
			SELECT f.forecast_id, f.expected_home_goals, f.expected_away_goals, f.probabilities
			FROM football.product_forecasts f WHERE f.fixture_id = pf.fixture_id
			ORDER BY f.created_at DESC LIMIT 1
		) forecast ON true
		LEFT JOIN LATERAL (
			SELECT live.provider_code, live.provider_status, live.canonical_status,
			       live.home_score, live.away_score, live.match_minute, live.added_time,
			       live.period, live.last_fetched_at AS observed_at, live.stale_after
			FROM football.product_provider_fixture_observations live
			WHERE live.canonical_fixture_id = pf.fixture_id
			  AND live.canonical_status = pf.status
			  AND live.home_score IS NOT DISTINCT FROM pf.home_score
			  AND live.away_score IS NOT DISTINCT FROM pf.away_score
			ORDER BY COALESCE(live.source_updated_at, live.observed_at) DESC,
			         (live.stale_after >= clock_timestamp()) DESC,
			         CASE live.provider_code WHEN 'pitchapi' THEN 0 WHEN 'fotmob' THEN 1 ELSE 2 END,
			         live.observed_at DESC, live.observation_id DESC
			LIMIT 1
		) observation ON true
		LEFT JOIN LATERAL (
			SELECT resource.payload, resource.provider_code
			FROM football.product_provider_resource_observations resource
			WHERE resource.canonical_fixture_id = pf.fixture_id
			  AND resource.resource_type = 'NORMALIZED_EVENTS'
			ORDER BY resource.observed_at DESC, resource.resource_observation_id DESC LIMIT 1
		) event_resource ON true
		WHERE pf.kickoff_at >= $1 AND pf.kickoff_at < $2
		  AND lower(btrim(pc.season_label)) <> 'unknown'
`
	args := []any{filters.Start, filters.End}
	query = addFilter(query, &args, "pc.competition_id::text", filters.CompetitionID)
	query = addFilter(query, &args, "COALESCE(pc.geographic_scope, pc.country)", filters.Country)
	query = addFilter(query, &args, "pc.continent", filters.Continent)
	query = addFilter(query, &args, "pf.forecast_availability", filters.ForecastAvailability)
	query += " ORDER BY pc.continent, COALESCE(pc.geographic_scope, pc.country), pc.name, pf.kickoff_at, pf.fixture_id"
	rows, err := store.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	groups := []FixtureGroup{}
	indexes := map[string]int{}
	for rows.Next() {
		competition, fixture, err := scanFixture(rows)
		if err != nil {
			return nil, err
		}
		index, exists := indexes[competition.ID]
		if !exists {
			index = len(groups)
			indexes[competition.ID] = index
			groups = append(groups, FixtureGroup{Competition: competition, Fixtures: []Fixture{}})
		}
		groups[index].Fixtures = append(groups[index].Fixtures, fixture)
	}
	return groups, rows.Err()
}

func (store *PostgresProductStore) LiveFixture(ctx context.Context, fixtureID string) (LiveMatch, error) {
	var item LiveMatch
	var eventsJSON, statisticsJSON []byte
	var scoreProvider, scoreMatchID, eventProvider, eventMatchID, statsProvider, statsMatchID *string
	var scoreObserved, scoreFetched, eventObserved, eventFetched, statsObserved, statsFetched *time.Time
	var scoreStale, eventStale, statsStale *bool
	err := store.pool.QueryRow(ctx, `
		SELECT pf.fixture_id::text, pf.status,
		       home.team_id::text, home.name, home.crest_url,
		       away.team_id::text, away.name, away.crest_url,
		       COALESCE(score.home_score, pf.home_score), COALESCE(score.away_score, pf.away_score),
		       score.match_minute, score.added_time, score.period,
		       score.provider_code, score.provider_match_id, score.observed_at, score.last_fetched_at,
		       CASE WHEN score.stale_after IS NULL THEN NULL ELSE score.stale_after < clock_timestamp() END,
		       COALESCE(events.payload->'events', '[]'::jsonb),
		       events.provider_code, events.provider_match_id, events.observed_at, events.last_fetched_at,
		       CASE WHEN events.last_fetched_at IS NULL THEN NULL ELSE events.last_fetched_at < clock_timestamp() - interval '3 minutes' END,
		       COALESCE(stats.payload->'statistics', '[]'::jsonb),
		       stats.provider_code, stats.provider_match_id, stats.observed_at, stats.last_fetched_at,
		       CASE WHEN stats.last_fetched_at IS NULL THEN NULL ELSE stats.last_fetched_at < clock_timestamp() - interval '3 minutes' END
		FROM football.product_effective_fixtures pf
		JOIN football.product_teams home ON home.team_id = pf.home_team_id
		JOIN football.product_teams away ON away.team_id = pf.away_team_id
		LEFT JOIN LATERAL (
			SELECT live.* FROM football.product_provider_fixture_observations live
			WHERE live.canonical_fixture_id = pf.fixture_id
			  AND live.canonical_status = pf.status
			  AND live.home_score IS NOT DISTINCT FROM pf.home_score
			  AND live.away_score IS NOT DISTINCT FROM pf.away_score
			ORDER BY COALESCE(live.source_updated_at, live.observed_at) DESC,
			         (live.stale_after >= clock_timestamp()) DESC,
			         CASE live.provider_code WHEN 'pitchapi' THEN 0 WHEN 'fotmob' THEN 1 ELSE 2 END,
			         live.observed_at DESC, live.observation_id DESC LIMIT 1
		) score ON true
		LEFT JOIN LATERAL (
			SELECT resource.* FROM football.product_provider_resource_observations resource
			WHERE resource.canonical_fixture_id = pf.fixture_id AND resource.resource_type = 'NORMALIZED_EVENTS'
			ORDER BY resource.observed_at DESC, resource.resource_observation_id DESC LIMIT 1
		) events ON true
		LEFT JOIN LATERAL (
			SELECT resource.* FROM football.product_provider_resource_observations resource
			WHERE resource.canonical_fixture_id = pf.fixture_id AND resource.resource_type = 'NORMALIZED_STATISTICS'
			ORDER BY resource.observed_at DESC, resource.resource_observation_id DESC LIMIT 1
		) stats ON true
		WHERE pf.fixture_id::text = $1`, fixtureID,
	).Scan(
		&item.FixtureID, &item.Status,
		&item.Home.ID, &item.Home.Name, &item.Home.CrestURL,
		&item.Away.ID, &item.Away.Name, &item.Away.CrestURL,
		&item.HomeScore, &item.AwayScore, &item.MatchMinute, &item.AddedTime, &item.Period,
		&scoreProvider, &scoreMatchID, &scoreObserved, &scoreFetched, &scoreStale,
		&eventsJSON, &eventProvider, &eventMatchID, &eventObserved, &eventFetched, &eventStale,
		&statisticsJSON, &statsProvider, &statsMatchID, &statsObserved, &statsFetched, &statsStale,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return LiveMatch{}, errProductNotFound
	}
	if err != nil {
		return LiveMatch{}, err
	}
	if err := json.Unmarshal(eventsJSON, &item.Events); err != nil {
		return LiveMatch{}, err
	}
	if err := json.Unmarshal(statisticsJSON, &item.Statistics); err != nil {
		return LiveMatch{}, err
	}
	attachEventTeams(item.Events, item.Home.ID, item.Away.ID, valueOrEmpty(eventProvider))
	item.ScoreSource = liveSource(scoreProvider, scoreMatchID, scoreObserved, scoreFetched, scoreStale)
	item.EventSource = liveSource(eventProvider, eventMatchID, eventObserved, eventFetched, eventStale)
	item.StatsSource = liveSource(statsProvider, statsMatchID, statsObserved, statsFetched, statsStale)
	item.Availability = map[string]bool{
		"score":      item.HomeScore != nil && item.AwayScore != nil,
		"events":     len(item.Events) > 0,
		"statistics": len(item.Statistics) > 0,
	}
	item.Partial = !item.Availability["score"] || !item.Availability["events"] || !item.Availability["statistics"]
	return item, nil
}

func liveSource(provider, matchID *string, observed, fetched *time.Time, stale *bool) *LiveSource {
	if provider == nil || matchID == nil || observed == nil || fetched == nil {
		return nil
	}
	return &LiveSource{Provider: *provider, ProviderMatchID: *matchID, ObservedAt: *observed, LastFetchedAt: *fetched, Stale: stale != nil && *stale}
}

func valueOrEmpty(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func attachEventTeams(events []LiveEvent, homeID, awayID, provider string) {
	for index := range events {
		events[index].Provider = provider
		if events[index].TeamSide == nil {
			continue
		}
		var teamID string
		switch *events[index].TeamSide {
		case "HOME":
			teamID = homeID
		case "AWAY":
			teamID = awayID
		default:
			continue
		}
		events[index].TeamID = &teamID
	}
}

func (store *PostgresProductStore) FixtureContext(ctx context.Context, fixtureID string) (MatchContext, error) {
	var competitionID string
	var kickoffAt, knowledgeCutoff time.Time
	var payload []byte
	var digest *string
	err := store.pool.QueryRow(ctx, `SELECT f.competition_id::text,
        f.kickoff_at,
        LEAST(f.kickoff_at,statement_timestamp()),report.record_bytes,report.record_sha256
        FROM football.product_fixtures f
        CROSS JOIN LATERAL (SELECT football.public_context_source(f.fixture_id) AS value) source
        LEFT JOIN LATERAL (
            SELECT r.record_bytes,r.record_sha256 FROM football.product_read_reports r
            WHERE r.report_kind='CONTEXT' AND r.scope_id=f.fixture_id AND r.horizon='LATEST'
              AND r.source_fingerprint=encode(sha256(convert_to(source.value::text,'UTF8')),'hex')
            ORDER BY r.source_observed_at DESC,r.registered_at DESC,r.input_sha256 LIMIT 1
        ) report ON true WHERE f.fixture_id=$1::uuid`, fixtureID).Scan(
		&competitionID, &kickoffAt, &knowledgeCutoff, &payload, &digest)
	if err != nil {
		return MatchContext{}, productQueryError(err)
	}
	var item MatchContext
	if err := decodeReadReport(payload, digest, &item); err != nil {
		return item, err
	}
	if item.FixtureID != fixtureID {
		return MatchContext{}, errors.New("stored context report identity mismatch")
	}
	standings, err := store.standingsAt(ctx, competitionID, kickoffAt)
	if err != nil {
		return MatchContext{}, err
	}
	item.Standings = standings
	item.DataStatus = map[string]bool{
		"recent_form": len(item.HomeForm) > 0 && len(item.AwayForm) > 0,
		"h2h":         len(item.H2H) > 0, "standings": len(standings) > 0,
		"team_stats": len(item.HomeForm) > 0 && len(item.AwayForm) > 0,
	}
	if err := store.addLiveContext(ctx, &item, kickoffAt, knowledgeCutoff); err != nil {
		return MatchContext{}, err
	}
	return item, nil
}

func (store *PostgresProductStore) ForecastHistory(ctx context.Context, fixtureID string) ([]ForecastRevision, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT forecast_id::text, fixture_id::text, created_at, football_cutoff,
		       knowledge_cutoff, forecast_horizon, supersedes_forecast_id::text,
		       model_algorithm_version, model_artifact_sha256,
		       predictive_input_snapshot_sha256, context_snapshot_sha256,
		       revision_reason_codes, new_information_ids, expected_home_goals,
               expected_away_goals, probabilities, score_matrix,
               COALESCE(score_matrix_version, 'legacy-compact-index-v1'), payload_sha256
		FROM football.product_forecasts
		WHERE fixture_id::text = $1 AND model_label = 'MVP_FORECAST'
		ORDER BY created_at, forecast_id`, fixtureID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []ForecastRevision{}
	for rows.Next() {
		var item ForecastRevision
		var reasons, information, probabilities, scoreMatrix []byte
		var expectedHomeGoals, expectedAwayGoals float64
		var scoreMatrixVersion string
		if err := rows.Scan(
			&item.ForecastID, &item.FixtureID, &item.IssuedAt, &item.FootballCutoff,
			&item.KnowledgeCutoff, &item.ForecastHorizon, &item.SupersedesForecastID,
			&item.ModelID, &item.ArtifactSHA256, &item.PredictiveInputSnapshotSHA256,
			&item.ContextSnapshotSHA256, &reasons, &information, &expectedHomeGoals,
			&expectedAwayGoals, &probabilities, &scoreMatrix, &scoreMatrixVersion, &item.PayloadSHA256,
		); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(reasons, &item.RevisionReasonCodes); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(information, &item.NewInformationIDs); err != nil {
			return nil, err
		}
		var probabilityValues map[string]float64
		var scoreValues []map[string]any
		if err := json.Unmarshal(probabilities, &probabilityValues); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(scoreMatrix, &scoreValues); err != nil {
			return nil, err
		}
		item.ProbabilityPayload = map[string]any{
			"expected_home_goals":  expectedHomeGoals,
			"expected_away_goals":  expectedAwayGoals,
			"probabilities":        probabilityValues,
			"score_matrix":         scoreValues,
			"score_matrix_version": scoreMatrixVersion,
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (store *PostgresProductStore) Forecast(ctx context.Context, fixtureID, forecastID string) (Forecast, error) {
	var item Forecast
	var probabilities, matrix []byte
	err := store.pool.QueryRow(ctx, `
		SELECT forecast_id::text, fixture_id::text, model_label, model_algorithm_version,
		       created_at, football_cutoff, knowledge_cutoff, knowledge_mode,
		       expected_home_goals, expected_away_goals, probabilities, score_matrix,
		       publication_mode, COALESCE(score_matrix_version, 'legacy-compact-index-v1')
		FROM football.product_forecasts
		WHERE fixture_id::text = $1 AND forecast_id::text = $2`, fixtureID, forecastID,
	).Scan(
		&item.ID, &item.FixtureID, &item.ModelLabel, &item.ModelAlgorithm,
		&item.CreatedAt, &item.FootballCutoff, &item.KnowledgeCutoff, &item.KnowledgeMode,
		&item.ExpectedHomeGoals, &item.ExpectedAwayGoals, &probabilities, &matrix,
		&item.PublicationMode, &item.ScoreMatrixVersion,
	)
	if err != nil {
		return Forecast{}, productQueryError(err)
	}
	if err := json.Unmarshal(probabilities, &item.Probabilities); err != nil {
		return Forecast{}, err
	}
	if err := json.Unmarshal(matrix, &item.ScoreMatrix); err != nil {
		return Forecast{}, err
	}
	return item, nil
}

func (store *PostgresProductStore) Standings(ctx context.Context, competitionID string) ([]StandingRow, error) {
	return store.standingsAt(ctx, competitionID, time.Date(9999, 1, 1, 0, 0, 0, 0, time.UTC))
}

func (store *PostgresProductStore) standingsAt(
	ctx context.Context, competitionID string, cutoff time.Time,
) ([]StandingRow, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT s.position, s.team_id::text, t.name, s.played, s.won, s.drawn, s.lost,
		       s.goals_for, s.goals_against, s.goal_difference, s.points
		FROM football.product_standings s
		JOIN football.product_teams t ON t.team_id = s.team_id
		WHERE s.competition_id::text = $1 AND s.updated_at < $2
		ORDER BY s.position`, competitionID, cutoff)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (StandingRow, error) {
		var item StandingRow
		err := row.Scan(
			&item.Position, &item.TeamID, &item.Team, &item.Played, &item.Won,
			&item.Drawn, &item.Lost, &item.GoalsFor, &item.GoalsAgainst,
			&item.GoalDifference, &item.Points,
		)
		return item, err
	})
}

func filterSortAndPaginatePerformances(items []Performance, filters PerformanceFilters) PerformancePage {
	filtered := make([]Performance, 0, len(items))
	for _, item := range items {
		if performanceMatchesFilter(item, filters) {
			filtered = append(filtered, item)
		}
	}
	sort.Slice(filtered, func(i, j int) bool { return performanceLess(filtered[i], filtered[j]) })
	return paginatePerformances(filtered, filters.Page, filters.PageSize)
}

func paginatePerformances(items []Performance, page, pageSize int) PerformancePage {
	totalItems := len(items)
	totalPages := 0
	if totalItems > 0 {
		totalPages = (totalItems + pageSize - 1) / pageSize
		if page > totalPages {
			page = totalPages
		}
	} else {
		page = 1
	}
	start := (page - 1) * pageSize
	end := min(start+pageSize, totalItems)
	pageItems := items[start:end]
	if pageItems == nil {
		pageItems = []Performance{}
	}
	return PerformancePage{
		Performance: pageItems,
		Pagination: Pagination{
			Page: page, PageSize: pageSize, TotalItems: totalItems, TotalPages: totalPages,
		},
	}
}

func (store *PostgresProductStore) ExternalPredictions(ctx context.Context, filters ExternalPredictionFilters) ([]ExternalPrediction, error) {
	query := `
		SELECT ep.prediction_id::text, eps.name, ep.source_page,
		       ep.prediction_date::text, ep.original_date_text, ep.collected_at,
		       ep.fixture_id::text, pf.kickoff_at, ep.competition_text, ep.home_team_text,
		       ep.away_team_text, ep.market, ep.selection, ep.match_status,
		       comparison.record_bytes,comparison.record_sha256,source.value->>'forecast_id', COALESCE(result.settlement_state, 'PENDING'),
		       result.home_score, result.away_score, result.score_basis, result.provider_code,
		       result.provider_updated_at
		FROM football.external_predictions ep
		JOIN football.external_prediction_sources eps ON eps.source_code = ep.source_code
		LEFT JOIN football.product_fixtures pf ON pf.fixture_id = ep.fixture_id
		LEFT JOIN football.product_competitions pc ON pc.competition_id = pf.competition_id
        CROSS JOIN LATERAL (SELECT football.public_comparison_source(ep.prediction_id) AS value) source
        LEFT JOIN LATERAL (
            SELECT r.record_bytes,r.record_sha256 FROM football.product_read_reports r
            WHERE r.report_kind='COMPARISON' AND r.scope_id=ep.prediction_id AND r.horizon='LATEST'
              AND r.source_fingerprint=encode(sha256(convert_to(source.value::text,'UTF8')),'hex')
            ORDER BY r.source_observed_at DESC,r.registered_at DESC,r.input_sha256 LIMIT 1
        ) comparison ON true
		LEFT JOIN LATERAL (
			SELECT settlement_state, home_score, away_score, score_basis, provider_code,
			       provider_updated_at
			FROM football.external_prediction_result_revisions revision
			WHERE revision.prediction_id = ep.prediction_id
			ORDER BY settled_at DESC, result_revision_id DESC LIMIT 1
		) result ON true
		WHERE true`
	args := []any{}
	if !filters.Date.IsZero() {
		args = append(args, filters.Date)
		query += fmt.Sprintf(" AND ep.prediction_date = $%d", len(args))
	}
	query = addPredictionDateRange(query, &args, filters)
	query = addFilter(query, &args, "ep.source_code", filters.Source)
	query = addFilter(query, &args, "pc.continent", filters.Continent)
	query = addFilter(query, &args, "COALESCE(pc.geographic_scope, pc.country)", filters.Country)
	query = addFilter(query, &args, "ep.competition_text", filters.Competition)
	query = addFilter(query, &args, "ep.market", filters.Market)
	query = addFilter(query, &args, "ep.fixture_id::text", filters.FixtureID)
	query += " ORDER BY ep.prediction_date, ep.collected_at, ep.prediction_id"
	rows, err := store.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []ExternalPrediction{}
	for rows.Next() {
		var item ExternalPrediction
		var comparison []byte
		var digest, forecastID *string
		if err := rows.Scan(
			&item.ID, &item.Source, &item.SourcePage, &item.PredictionDate,
			&item.OriginalDateText, &item.CollectedAt, &item.FixtureID, &item.KickoffAt,
			&item.Competition, &item.HomeTeam, &item.AwayTeam, &item.Market,
			&item.Selection, &item.MatchStatus, &comparison, &digest, &forecastID, &item.SettlementState,
			&item.ActualHomeScore, &item.ActualAwayScore, &item.ResultScoreBasis,
			&item.ResultProvider,
			&item.ResultUpdatedAt,
		); err != nil {
			return nil, err
		}
		if err := attachComparison(&item, forecastID, comparison, digest); err != nil {
			return nil, err
		}
		if filters.Agreement != "" && item.Agreement != filters.Agreement {
			continue
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (store *PostgresProductStore) ExternalPredictionSources(ctx context.Context, filters ExternalPredictionFilters) ([]ExternalPredictionSource, error) {
	query := `
		SELECT source.source_code, source.name, source.base_url,
		       source.public_predictions, source.prediction_date_available,
		       source.login_required, source.paid_content,
		       source.automated_access_status, source.adapter_status,
		       source.known_issues, source.checked_at, COUNT(ep.prediction_id)::int,
		       COUNT(result.prediction_id)::int,
		       COUNT(result.prediction_id) FILTER (WHERE result.correct)::int,
		       (AVG(CASE WHEN result.correct THEN 1.0 ELSE 0.0 END)
		           FILTER (WHERE result.prediction_id IS NOT NULL))::double precision
		FROM football.external_prediction_sources source
		LEFT JOIN football.external_predictions ep ON ep.source_code = source.source_code
		LEFT JOIN football.external_prediction_results result ON result.prediction_id = ep.prediction_id
		LEFT JOIN football.product_fixtures pf ON pf.fixture_id = ep.fixture_id
		LEFT JOIN football.product_competitions pc ON pc.competition_id = pf.competition_id
		WHERE true`
	args := []any{}
	query = addFilter(query, &args, "source.source_code", filters.Source)
	query = addFilter(query, &args, "ep.competition_text", filters.Competition)
	query = addFilter(query, &args, "ep.market", filters.Market)
	query = addFilter(query, &args, "pc.continent", filters.Continent)
	query = addFilter(query, &args, "COALESCE(pc.geographic_scope, pc.country)", filters.Country)
	query = addPredictionDateRange(query, &args, filters)
	query += " GROUP BY source.source_code ORDER BY source.name"
	rows, err := store.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (ExternalPredictionSource, error) {
		var item ExternalPredictionSource
		err := row.Scan(
			&item.Code, &item.Name, &item.URL, &item.PublicPredictions,
			&item.PredictionDate, &item.LoginRequired, &item.PaidContent,
			&item.AutomatedAccessStatus, &item.AdapterStatus, &item.KnownIssues,
			&item.CheckedAt, &item.TrackedSelections, &item.SettledSelections,
			&item.CorrectSelections, &item.SettledHitRate,
		)
		return item, err
	})
	if err != nil {
		return nil, err
	}
	for index := range items {
		sourceFilters := filters
		sourceFilters.Source = items[index].Code
		predictions, err := store.ExternalPredictions(ctx, sourceFilters)
		if err != nil {
			return nil, err
		}
		eligible, agreements := 0, 0
		for _, prediction := range predictions {
			if prediction.Agreement == "UNABLE_TO_EVALUATE" {
				continue
			}
			eligible++
			if prediction.Agreement == "AGREES" {
				agreements++
			}
		}
		if eligible > 0 {
			items[index].AgreementRate = floatPointer(float64(agreements) / float64(eligible))
		}
	}
	return items, nil
}

func (store *PostgresProductStore) addLiveContext(
	ctx context.Context,
	item *MatchContext,
	kickoffAt, knowledgeCutoff time.Time,
) error {
	availability, provenance, err := store.availabilityContext(
		ctx, item.FixtureID, kickoffAt, knowledgeCutoff,
	)
	if err != nil {
		return err
	}
	lineups, lineupProvenance, err := store.lineupContext(
		ctx, item.FixtureID, kickoffAt, knowledgeCutoff,
	)
	if err != nil {
		return err
	}
	item.Availability = availability
	item.ContextProvenance = append(provenance, lineupProvenance...)
	assignLineups(item, lineups)
	item.ContextMissingness = contextMissingness(item, len(availability), len(item.CoachContext))
	item.DataStatus["availability"] = len(availability) > 0
	item.DataStatus["predicted_lineup"] = len(item.PredictedLineups) > 0
	item.DataStatus["confirmed_lineup"] = len(item.ConfirmedLineups) > 0
	item.DataStatus["coach_context"] = len(item.CoachContext) == 2
	item.DataStatus["rest_context"] = len(item.RestContext) == 2
	return nil
}

func assignLineups(item *MatchContext, lineups []LineupContext) {
	item.PredictedLineups = []LineupContext{}
	item.ConfirmedLineups = []LineupContext{}
	for _, lineup := range lineups {
		if lineup.Mode == "CONFIRMED" {
			item.ConfirmedLineups = append(item.ConfirmedLineups, lineup)
		} else if lineup.Mode == "PREDICTED_REPEAT_XI" {
			item.PredictedLineups = append(item.PredictedLineups, lineup)
		}
	}
}

func contextMissingness(item *MatchContext, availabilityCount, coachCount int) []string {
	missingness := []string{}
	if availabilityCount == 0 {
		missingness = append(missingness, "AVAILABILITY_UNVERIFIED")
	}
	if len(item.PredictedLineups) == 0 {
		missingness = append(missingness, "PREDICTED_LINEUP_UNAVAILABLE")
	}
	if len(item.ConfirmedLineups) == 0 {
		missingness = append(missingness, "CONFIRMED_LINEUP_UNAVAILABLE")
	}
	if coachCount < 2 {
		missingness = append(missingness, "COACH_CONTEXT_INCOMPLETE")
	}
	return missingness
}

func (store *PostgresProductStore) availabilityContext(
	ctx context.Context, fixtureID string, kickoffAt, knowledgeCutoff time.Time,
) ([]AvailabilityContext, []ContextProvenance, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT DISTINCT ON (team_id, provider_player_id, availability_type)
		       team_id::text, canonical_player_id::text, provider_player_id,
		       availability_type, availability_state, reason, observed_at, known_at,
		       provider, source_snapshot_id::text, source_checksum
		FROM football.product_availability_observations
		WHERE fixture_id::text = $1 AND observed_at < $2 AND known_at <= $3
		ORDER BY team_id, provider_player_id, availability_type,
		         known_at DESC, observed_at DESC, observation_id DESC`,
		fixtureID, kickoffAt, knowledgeCutoff)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()
	items := []AvailabilityContext{}
	provenance := []ContextProvenance{}
	for rows.Next() {
		var item AvailabilityContext
		var sourceID, checksum string
		if err := rows.Scan(
			&item.TeamID, &item.PlayerID, &item.ProviderPlayerID, &item.Type, &item.State,
			&item.Reason, &item.ObservedAt, &item.KnownAt, &item.Provider, &sourceID, &checksum,
		); err != nil {
			return nil, nil, err
		}
		if knowledgeCutoff.Sub(item.ObservedAt) > 4*time.Hour {
			item.State = "AVAILABILITY_UNVERIFIED"
		}
		items = append(items, item)
		provenance = append(provenance, ContextProvenance{
			Provider: item.Provider, SourceSnapshotID: sourceID,
			SourceChecksum: checksum, KnownAt: item.KnownAt,
		})
	}
	return items, provenance, rows.Err()
}

func (store *PostgresProductStore) lineupContext(
	ctx context.Context, fixtureID string, kickoffAt, knowledgeCutoff time.Time,
) ([]LineupContext, []ContextProvenance, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT lineup_observation_id::text, team_id::text, lineup_mode, formation,
		       coach_id::text, prediction_confidence, coach_context,
		       supersedes_predicted_lineup_id::text, observed_at, known_at,
		       provider, source_snapshot_id::text, source_checksum
		FROM (
			SELECT observation.*, row_number() OVER (
				PARTITION BY team_id, lineup_mode
				ORDER BY known_at DESC, observed_at DESC, lineup_observation_id DESC
			) AS position
			FROM football.product_lineup_observations observation
			WHERE fixture_id::text = $1 AND observed_at < $2 AND known_at <= $3
		) latest WHERE position = 1
		ORDER BY team_id, lineup_mode`, fixtureID, kickoffAt, knowledgeCutoff)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()
	items := []LineupContext{}
	provenance := []ContextProvenance{}
	for rows.Next() {
		var item LineupContext
		var provider, sourceID, checksum string
		if err := rows.Scan(
			&item.ID, &item.TeamID, &item.Mode, &item.Formation, &item.CoachID,
			&item.PredictionConfidence, &item.CoachContext, &item.SupersedesPredictedID,
			&item.ObservedAt, &item.KnownAt, &provider, &sourceID, &checksum,
		); err != nil {
			return nil, nil, err
		}
		players, err := store.lineupPlayers(ctx, item.ID)
		if err != nil {
			return nil, nil, err
		}
		item.Players = players
		items = append(items, item)
		provenance = append(provenance, ContextProvenance{
			Provider: provider, SourceSnapshotID: sourceID,
			SourceChecksum: checksum, KnownAt: item.KnownAt,
		})
	}
	return items, provenance, rows.Err()
}

func (store *PostgresProductStore) lineupPlayers(
	ctx context.Context, lineupID string,
) ([]LineupPlayerContext, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT canonical_player_id::text, provider_player_id, role, position,
		       normalized_position, grid_position, availability_state,
		       selection_reason, replaced_player_id::text, replacement_reason,
		       preference_score, historical_start_count, slot_status
		FROM football.product_lineup_players
		WHERE lineup_observation_id::text = $1 ORDER BY slot_order`, lineupID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (LineupPlayerContext, error) {
		var item LineupPlayerContext
		err := row.Scan(
			&item.PlayerID, &item.ProviderPlayerID, &item.Role, &item.Position,
			&item.NormalizedPosition, &item.GridPosition, &item.AvailabilityState,
			&item.SelectionReason, &item.ReplacedPlayerID, &item.ReplacementReason,
			&item.PreferenceScore, &item.HistoricalStartCount, &item.SlotStatus,
		)
		return item, err
	})
}

func scanCompetition(row pgx.CollectableRow) (Competition, error) {
	var item Competition
	var sourceJSON []byte
	err := row.Scan(
		&item.ID, &item.Name, &item.Country, &item.Continent, &item.Division,
		&item.Type, &item.Season, &item.Availability.Fixtures,
		&item.Availability.Results, &item.Availability.Standings, &item.Availability.H2H,
		&item.Availability.Forecast, &item.Availability.XG, &item.Availability.TeamStats,
		&item.AvailabilityStatus, &sourceJSON,
	)
	if err == nil {
		err = json.Unmarshal(sourceJSON, &item.Sources)
	}
	return item, err
}

func scanFixture(row pgx.Row) (Competition, Fixture, error) {
	var competition Competition
	var fixture Fixture
	var sourceJSON, probabilities, eventJSON []byte
	var eventProvider *string
	var forecastID *string
	var homeMean, awayMean *float64
	err := row.Scan(
		&competition.ID, &competition.Name, &competition.Country, &competition.Continent,
		&competition.Division, &competition.Type, &competition.Season,
		&competition.Availability.Fixtures, &competition.Availability.Results,
		&competition.Availability.Standings, &competition.Availability.H2H,
		&competition.Availability.Forecast, &competition.Availability.XG,
		&competition.Availability.TeamStats, &competition.AvailabilityStatus, &sourceJSON,
		&fixture.ID, &fixture.KickoffAt, &fixture.Status,
		&fixture.Home.ID, &fixture.Home.Name, &fixture.Home.CrestURL,
		&fixture.Away.ID, &fixture.Away.Name, &fixture.Away.CrestURL,
		&fixture.HomeScore, &fixture.AwayScore, &fixture.Venue, &fixture.Round,
		&fixture.ForecastAvailability, &forecastID, &homeMean, &awayMean, &probabilities,
		&fixture.Provider, &fixture.ProviderStatus, &fixture.MatchMinute, &fixture.AddedTime,
		&fixture.Period, &fixture.LastSuccessfulUpdate, &fixture.Stale,
		&eventJSON, &eventProvider,
	)
	if err != nil {
		return Competition{}, Fixture{}, err
	}
	if err := json.Unmarshal(sourceJSON, &competition.Sources); err != nil {
		return Competition{}, Fixture{}, err
	}
	if forecastID != nil && homeMean != nil && awayMean != nil {
		forecast := &ForecastSummary{ID: *forecastID, ExpectedHomeGoals: *homeMean, ExpectedAwayGoals: *awayMean}
		if err := json.Unmarshal(probabilities, &forecast.Probabilities); err != nil {
			return Competition{}, Fixture{}, err
		}
		fixture.Forecast = forecast
	}
	var events []LiveEvent
	if err := json.Unmarshal(eventJSON, &events); err != nil {
		return Competition{}, Fixture{}, err
	}
	attachEventTeams(events, fixture.Home.ID, fixture.Away.ID, valueOrEmpty(eventProvider))
	fixture.GoalScorers = verifiedGoals(events)
	return competition, fixture, nil
}

func verifiedGoals(events []LiveEvent) []LiveEvent {
	goals := []LiveEvent{}
	for _, event := range events {
		if event.Type == "GOAL" && !event.Disallowed {
			goals = append(goals, event)
		}
	}
	return goals
}

func addFilter(query string, args *[]any, column, value string) string {
	if value == "" {
		return query
	}
	*args = append(*args, value)
	return query + fmt.Sprintf(" AND %s = $%d", column, len(*args))
}

func addPredictionDateRange(query string, args *[]any, filters ExternalPredictionFilters) string {
	if !filters.DateFrom.IsZero() {
		*args = append(*args, filters.DateFrom)
		query += fmt.Sprintf(" AND ep.prediction_date >= $%d", len(*args))
	}
	if !filters.DateTo.IsZero() {
		*args = append(*args, filters.DateTo)
		query += fmt.Sprintf(" AND ep.prediction_date <= $%d", len(*args))
	}
	return query
}

func performanceMatchesFilter(item Performance, filters PerformanceFilters) bool {
	return item.Forecasts >= filters.MinimumForecasts &&
		(filters.Rating == "" || item.Rating == filters.Rating)
}

func performanceLess(left, right Performance) bool {
	if left.Continent != right.Continent {
		return left.Continent < right.Continent
	}
	if left.Country != right.Country {
		return left.Country < right.Country
	}
	if left.League != right.League {
		return left.League < right.League
	}
	return left.CompetitionID < right.CompetitionID
}

func productQueryError(err error) error {
	if errors.Is(err, pgx.ErrNoRows) {
		return errProductUnavailable
	}
	return err
}

func floatPointer(value float64) *float64 { return &value }
