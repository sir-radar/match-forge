package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"sort"
	"strings"
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
		SELECT competition_id::text, name, country, continent, division,
		       competition_type, season_label, fixtures_available, results_available,
		       standings_available, h2h_available, forecast_available, xg_available,
		       team_stats_available, availability_status, source_roles
		FROM football.product_competitions WHERE true`
	args := []any{}
	query = addFilter(query, &args, "continent", filters.Continent)
	query = addFilter(query, &args, "country", filters.Country)
	if filters.Division > 0 {
		args = append(args, filters.Division)
		query += fmt.Sprintf(" AND division = $%d", len(args))
	}
	if filters.ForecastAvailable != nil {
		args = append(args, *filters.ForecastAvailable)
		query += fmt.Sprintf(" AND forecast_available = $%d", len(args))
	}
	query += " ORDER BY continent, country, division NULLS LAST, name"
	rows, err := store.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, scanCompetition)
}

func (store *PostgresProductStore) Fixtures(ctx context.Context, filters FixtureFilters) ([]FixtureGroup, error) {
	query := `
		SELECT pc.competition_id::text, pc.name, pc.country, pc.continent, pc.division,
		       pc.competition_type, pc.season_label, pc.fixtures_available,
		       pc.results_available, pc.standings_available, pc.h2h_available,
		       pc.forecast_available, pc.xg_available, pc.team_stats_available,
		       pc.availability_status, pc.source_roles,
		       pf.fixture_id::text, pf.kickoff_at, pf.status,
		       ht.team_id::text, ht.name, ht.crest_url,
		       at.team_id::text, at.name, at.crest_url,
		       pf.home_score, pf.away_score, pf.venue, pf.round_name,
		       pf.forecast_availability,
		       forecast.forecast_id::text, forecast.expected_home_goals,
		       forecast.expected_away_goals, forecast.probabilities
		FROM football.product_fixtures pf
		JOIN football.product_competitions pc ON pc.competition_id = pf.competition_id
		JOIN football.product_teams ht ON ht.team_id = pf.home_team_id
		JOIN football.product_teams at ON at.team_id = pf.away_team_id
		LEFT JOIN LATERAL (
			SELECT f.forecast_id, f.expected_home_goals, f.expected_away_goals, f.probabilities
			FROM football.product_forecasts f WHERE f.fixture_id = pf.fixture_id
			ORDER BY f.created_at DESC LIMIT 1
		) forecast ON true
		WHERE pf.kickoff_at >= $1 AND pf.kickoff_at < $1 + interval '1 day'`
	args := []any{filters.Date.UTC()}
	query = addFilter(query, &args, "pc.competition_id::text", filters.CompetitionID)
	query = addFilter(query, &args, "pc.country", filters.Country)
	query = addFilter(query, &args, "pc.continent", filters.Continent)
	query = addFilter(query, &args, "pf.forecast_availability", filters.ForecastAvailability)
	query += " ORDER BY pc.continent, pc.country, pc.name, pf.kickoff_at, pf.fixture_id"
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

func (store *PostgresProductStore) FixtureContext(ctx context.Context, fixtureID string) (MatchContext, error) {
	var competitionID, homeID, awayID string
	var kickoffAt, knowledgeCutoff time.Time
	err := store.pool.QueryRow(ctx, `
		SELECT competition_id::text, home_team_id::text, away_team_id::text,
		       kickoff_at, LEAST(kickoff_at, clock_timestamp())
		FROM football.product_fixtures WHERE fixture_id::text = $1`, fixtureID,
	).Scan(&competitionID, &homeID, &awayID, &kickoffAt, &knowledgeCutoff)
	if err != nil {
		return MatchContext{}, productQueryError(err)
	}
	homeForm, err := store.form(ctx, homeID, kickoffAt, knowledgeCutoff)
	if err != nil {
		return MatchContext{}, err
	}
	awayForm, err := store.form(ctx, awayID, kickoffAt, knowledgeCutoff)
	if err != nil {
		return MatchContext{}, err
	}
	h2h, err := store.h2h(ctx, homeID, awayID, kickoffAt, knowledgeCutoff)
	if err != nil {
		return MatchContext{}, err
	}
	standings, err := store.standingsAt(ctx, competitionID, kickoffAt)
	if err != nil {
		return MatchContext{}, err
	}
	item := MatchContext{
		FixtureID: fixtureID, HomeForm: homeForm, AwayForm: awayForm, H2H: h2h,
		H2HSummary: summarizeH2H(h2h), HomeStats: summarizeForm(homeForm),
		AwayStats: summarizeForm(awayForm), Standings: standings,
		DataStatus: map[string]bool{
			"recent_form": len(homeForm) > 0 && len(awayForm) > 0,
			"h2h":         len(h2h) > 0, "standings": len(standings) > 0,
			"team_stats": len(homeForm) > 0 && len(awayForm) > 0,
		},
	}
	if err := store.addLiveContext(ctx, &item, homeID, awayID, kickoffAt, knowledgeCutoff); err != nil {
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
		       expected_away_goals, probabilities, score_matrix, payload_sha256
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
		if err := rows.Scan(
			&item.ForecastID, &item.FixtureID, &item.IssuedAt, &item.FootballCutoff,
			&item.KnowledgeCutoff, &item.ForecastHorizon, &item.SupersedesForecastID,
			&item.ModelID, &item.ArtifactSHA256, &item.PredictiveInputSnapshotSHA256,
			&item.ContextSnapshotSHA256, &reasons, &information, &expectedHomeGoals,
			&expectedAwayGoals, &probabilities, &scoreMatrix, &item.PayloadSHA256,
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
			"expected_home_goals": expectedHomeGoals,
			"expected_away_goals": expectedAwayGoals,
			"probabilities":       probabilityValues,
			"score_matrix":        scoreValues,
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
		       publication_mode
		FROM football.product_forecasts
		WHERE fixture_id::text = $1 AND forecast_id::text = $2`, fixtureID, forecastID,
	).Scan(
		&item.ID, &item.FixtureID, &item.ModelLabel, &item.ModelAlgorithm,
		&item.CreatedAt, &item.FootballCutoff, &item.KnowledgeCutoff, &item.KnowledgeMode,
		&item.ExpectedHomeGoals, &item.ExpectedAwayGoals, &probabilities, &matrix,
		&item.PublicationMode,
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

func (store *PostgresProductStore) Performance(ctx context.Context, competitionID string) (Performance, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT f.probabilities, f.score_matrix, pf.home_score, pf.away_score, pf.kickoff_at
		FROM football.product_forecasts f
		JOIN football.product_fixtures pf ON pf.fixture_id = f.fixture_id
		WHERE pf.competition_id::text = $1 AND pf.status = 'FINISHED'
		ORDER BY pf.kickoff_at, pf.fixture_id`, competitionID)
	if err != nil {
		return Performance{}, err
	}
	defer rows.Close()
	records := []performanceRecord{}
	for rows.Next() {
		var probabilities, matrix []byte
		var homeScore, awayScore int
		var kickoff time.Time
		if err := rows.Scan(&probabilities, &matrix, &homeScore, &awayScore, &kickoff); err != nil {
			return Performance{}, err
		}
		var values map[string]float64
		var scores []scoreCell
		if json.Unmarshal(probabilities, &values) != nil || json.Unmarshal(matrix, &scores) != nil {
			return Performance{}, errors.New("stored forecast JSON is invalid")
		}
		records = append(records, performanceRecord{values, scores, homeScore, awayScore})
	}
	item := calculatePerformance(competitionID, records)
	if err := rows.Err(); err != nil {
		return Performance{}, err
	}
	err = store.pool.QueryRow(ctx, `
		SELECT name, country, continent FROM football.product_competitions
		WHERE competition_id::text = $1`, competitionID,
	).Scan(&item.League, &item.Country, &item.Continent)
	return item, productQueryError(err)
}

func (store *PostgresProductStore) Performances(ctx context.Context, filters PerformanceFilters) (PerformancePage, error) {
	competitionFilters := CompetitionFilters{Continent: filters.Continent, Country: filters.Country}
	competitions, err := store.Competitions(ctx, competitionFilters)
	if err != nil {
		return PerformancePage{}, err
	}
	items := make([]Performance, 0, len(competitions))
	for _, competition := range competitions {
		if !competitionMatchesPerformanceFilter(competition, filters) {
			continue
		}
		item, err := store.Performance(ctx, competition.ID)
		if err != nil {
			return PerformancePage{}, err
		}
		items = append(items, item)
	}
	return filterSortAndPaginatePerformances(items, filters), nil
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
		       forecast.probabilities
		FROM football.external_predictions ep
		JOIN football.external_prediction_sources eps ON eps.source_code = ep.source_code
		LEFT JOIN football.product_fixtures pf ON pf.fixture_id = ep.fixture_id
		LEFT JOIN football.product_competitions pc ON pc.competition_id = pf.competition_id
		LEFT JOIN LATERAL (
			SELECT probabilities FROM football.product_forecasts
			WHERE fixture_id = ep.fixture_id ORDER BY created_at DESC LIMIT 1
		) forecast ON true
		WHERE true`
	args := []any{}
	if !filters.Date.IsZero() {
		args = append(args, filters.Date)
		query += fmt.Sprintf(" AND ep.prediction_date = $%d", len(args))
	}
	query = addPredictionDateRange(query, &args, filters)
	query = addFilter(query, &args, "ep.source_code", filters.Source)
	query = addFilter(query, &args, "pc.continent", filters.Continent)
	query = addFilter(query, &args, "pc.country", filters.Country)
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
		var probabilities []byte
		if err := rows.Scan(
			&item.ID, &item.Source, &item.SourcePage, &item.PredictionDate,
			&item.OriginalDateText, &item.CollectedAt, &item.FixtureID, &item.KickoffAt,
			&item.Competition, &item.HomeTeam, &item.AwayTeam, &item.Market,
			&item.Selection, &item.MatchStatus, &probabilities,
		); err != nil {
			return nil, err
		}
		item.Agreement = "UNABLE_TO_EVALUATE"
		if probabilities != nil {
			var values map[string]float64
			if err := json.Unmarshal(probabilities, &values); err != nil {
				return nil, err
			}
			item.MatchForgeProbability, item.Agreement = selectionAgreement(item.Market, item.Selection, values)
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
	query = addFilter(query, &args, "pc.country", filters.Country)
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

func (store *PostgresProductStore) form(
	ctx context.Context, teamID string, kickoffAt, knowledgeCutoff time.Time,
) ([]FormMatch, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT history.kickoff_at,
		       CASE WHEN history.home_team_id::text = $1 THEN away.name ELSE home.name END,
		       CASE WHEN history.home_team_id::text = $1 THEN 'HOME' ELSE 'AWAY' END,
		       CASE WHEN history.home_team_id::text = $1 THEN history.home_goals ELSE history.away_goals END,
		       CASE WHEN history.home_team_id::text = $1 THEN history.away_goals ELSE history.home_goals END
		FROM football.product_team_match_history history
		JOIN football.source_snapshots snapshot ON snapshot.id = history.source_snapshot_id
		JOIN football.product_teams home ON home.team_id = history.home_team_id
		JOIN football.product_teams away ON away.team_id = history.away_team_id
		WHERE (history.home_team_id::text = $1 OR history.away_team_id::text = $1)
		  AND ((history.source_kickoff_precision = 'EXACT' AND history.kickoff_at < $2)
		    OR (history.source_kickoff_precision = 'DATE_ONLY'
		        AND history.kickoff_at::date < $2::date))
		  AND snapshot.acquired_at <= $3
		ORDER BY history.kickoff_at DESC LIMIT 5`, teamID, kickoffAt, knowledgeCutoff)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []FormMatch{}
	for rows.Next() {
		var item FormMatch
		if err := rows.Scan(
			&item.KickoffAt, &item.Opponent, &item.Venue, &item.GoalsFor, &item.GoalsAgainst,
		); err != nil {
			return nil, err
		}
		item.Result = "D"
		if item.GoalsFor > item.GoalsAgainst {
			item.Result = "W"
		} else if item.GoalsFor < item.GoalsAgainst {
			item.Result = "L"
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (store *PostgresProductStore) h2h(
	ctx context.Context, homeID, awayID string, kickoffAt, knowledgeCutoff time.Time,
) ([]H2HMatch, error) {
	rows, err := store.pool.Query(ctx, `
		SELECT history.kickoff_at, home.name, away.name,
		       history.home_goals, history.away_goals, history.home_xg, history.away_xg
		FROM football.product_team_match_history history
		JOIN football.source_snapshots snapshot ON snapshot.id = history.source_snapshot_id
		JOIN football.product_teams home ON home.team_id = history.home_team_id
		JOIN football.product_teams away ON away.team_id = history.away_team_id
		WHERE ((history.home_team_id::text = $1 AND history.away_team_id::text = $2)
		   OR (history.home_team_id::text = $2 AND history.away_team_id::text = $1))
		  AND ((history.source_kickoff_precision = 'EXACT' AND history.kickoff_at < $3)
		    OR (history.source_kickoff_precision = 'DATE_ONLY'
		        AND history.kickoff_at::date < $3::date))
		  AND snapshot.acquired_at <= $4
		ORDER BY history.kickoff_at DESC LIMIT 10`, homeID, awayID, kickoffAt, knowledgeCutoff)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (H2HMatch, error) {
		var item H2HMatch
		err := row.Scan(
			&item.KickoffAt, &item.HomeTeam, &item.AwayTeam, &item.HomeGoals,
			&item.AwayGoals, &item.HomeXG, &item.AwayXG,
		)
		return item, err
	})
}

func (store *PostgresProductStore) addLiveContext(
	ctx context.Context,
	item *MatchContext,
	homeID, awayID string,
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
	coaches, err := store.coachContext(ctx, []string{homeID, awayID}, kickoffAt, knowledgeCutoff)
	if err != nil {
		return err
	}
	rest, err := store.restContext(ctx, []string{homeID, awayID}, kickoffAt, knowledgeCutoff)
	if err != nil {
		return err
	}
	item.Availability = availability
	item.ContextProvenance = append(provenance, lineupProvenance...)
	item.CoachContext = coaches
	item.RestContext = rest
	assignLineups(item, lineups)
	item.ContextMissingness = contextMissingness(item, len(availability), len(coaches))
	item.DataStatus["availability"] = len(availability) > 0
	item.DataStatus["predicted_lineup"] = len(item.PredictedLineups) > 0
	item.DataStatus["confirmed_lineup"] = len(item.ConfirmedLineups) > 0
	item.DataStatus["coach_context"] = len(coaches) == 2
	item.DataStatus["rest_context"] = len(rest) == 2
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

func (store *PostgresProductStore) coachContext(
	ctx context.Context, teamIDs []string, kickoffAt, knowledgeCutoff time.Time,
) ([]CoachContext, error) {
	items := []CoachContext{}
	for _, teamID := range teamIDs {
		var item CoachContext
		var effectiveAt time.Time
		err := store.pool.QueryRow(ctx, `
			SELECT team_id::text, coach_id::text, effective_at
			FROM football.product_coach_observations
			WHERE team_id::text = $1 AND effective_at < $2 AND known_at <= $3
			ORDER BY effective_at DESC, known_at DESC LIMIT 1`,
			teamID, kickoffAt, knowledgeCutoff,
		).Scan(&item.TeamID, &item.CoachID, &effectiveAt)
		if errors.Is(err, pgx.ErrNoRows) {
			continue
		}
		if err != nil {
			return nil, err
		}
		var tenureStart time.Time
		if err := store.pool.QueryRow(ctx, `
			SELECT count(*), COALESCE(min(kickoff_at), $3)
			FROM football.product_lineup_observations
			WHERE team_id::text = $1 AND coach_id::text = $2
			  AND lineup_mode = 'CONFIRMED' AND kickoff_at < $3 AND known_at <= $4`,
			teamID, item.CoachID, kickoffAt, knowledgeCutoff,
		).Scan(&item.MatchesUnderCoach, &tenureStart); err != nil {
			return nil, err
		}
		item.CoachTenureDays = int(kickoffAt.Sub(tenureStart).Hours() / 24)
		item.CoachChangedRecently = item.MatchesUnderCoach < 5
		items = append(items, item)
	}
	return items, nil
}

func (store *PostgresProductStore) restContext(
	ctx context.Context, teamIDs []string, kickoffAt, knowledgeCutoff time.Time,
) (map[string]RestContext, error) {
	items := map[string]RestContext{}
	for _, teamID := range teamIDs {
		var item RestContext
		var last, next *time.Time
		err := store.pool.QueryRow(ctx, `
			SELECT max(kickoff_at) FILTER (WHERE kickoff_at < $2),
			       count(*) FILTER (WHERE kickoff_at >= $2 - interval '3 days' AND kickoff_at < $2),
			       count(*) FILTER (WHERE kickoff_at >= $2 - interval '7 days' AND kickoff_at < $2),
			       count(*) FILTER (WHERE kickoff_at >= $2 - interval '14 days' AND kickoff_at < $2),
			       count(*) FILTER (WHERE kickoff_at >= $2 - interval '30 days' AND kickoff_at < $2)
			FROM football.product_team_match_history history
			JOIN football.source_snapshots snapshot ON snapshot.id = history.source_snapshot_id
			WHERE (home_team_id::text = $1 OR away_team_id::text = $1)
			  AND ((source_kickoff_precision = 'EXACT' AND kickoff_at < $2)
			    OR (source_kickoff_precision = 'DATE_ONLY'
			        AND kickoff_at::date < $2::date))
			  AND snapshot.acquired_at <= $3`,
			teamID, kickoffAt, knowledgeCutoff,
		).Scan(&last, &item.MatchesLast3Days, &item.MatchesLast7Days,
			&item.MatchesLast14Days, &item.MatchesLast30Days)
		if err != nil {
			return nil, err
		}
		if err := store.pool.QueryRow(ctx, `
			SELECT min(kickoff_at) FROM football.product_fixtures
			WHERE (home_team_id::text = $1 OR away_team_id::text = $1)
			  AND kickoff_at > $2 AND updated_at <= $3`,
			teamID, kickoffAt, knowledgeCutoff,
		).Scan(&next); err != nil {
			return nil, err
		}
		if last != nil {
			value := kickoffAt.Sub(*last).Hours() / 24
			item.DaysSinceLastMatch = &value
		}
		if next != nil {
			value := next.Sub(kickoffAt).Hours() / 24
			item.DaysToNextMatch = &value
		}
		items[teamID] = item
	}
	return items, nil
}

func summarizeForm(matches []FormMatch) *TeamStatistics {
	if len(matches) == 0 {
		return nil
	}
	item := &TeamStatistics{RecentMatches: len(matches)}
	for _, match := range matches {
		item.GoalsFor += match.GoalsFor
		item.GoalsAgainst += match.GoalsAgainst
	}
	item.AverageGoalsFor = float64(item.GoalsFor) / float64(item.RecentMatches)
	item.AverageGoalsAgainst = float64(item.GoalsAgainst) / float64(item.RecentMatches)
	return item
}

func summarizeH2H(matches []H2HMatch) H2HSummary {
	result := H2HSummary{Meetings: len(matches)}
	for _, match := range matches {
		result.HomeGoals += match.HomeGoals
		result.AwayGoals += match.AwayGoals
		switch {
		case match.HomeGoals > match.AwayGoals:
			result.HomeWins++
		case match.HomeGoals < match.AwayGoals:
			result.AwayWins++
		default:
			result.Draws++
		}
	}
	return result
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
	var sourceJSON, probabilities []byte
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
	return competition, fixture, nil
}

type scoreCell struct {
	HomeGoals   int     `json:"home_goals"`
	AwayGoals   int     `json:"away_goals"`
	Probability float64 `json:"probability"`
}

type performanceRecord struct {
	probabilities map[string]float64
	scores        []scoreCell
	homeScore     int
	awayScore     int
}

func calculatePerformance(competitionID string, records []performanceRecord) Performance {
	item := Performance{CompetitionID: competitionID, Rating: "UNRATED", Forecasts: len(records)}
	if len(records) == 0 {
		return item
	}
	all := performanceWindow(records, 0)
	item.OutcomeHitRate = floatPointer(all.hits)
	item.Brier = floatPointer(all.brier)
	item.LogLoss = floatPointer(all.logLoss)
	item.BaselineBrier = floatPointer(all.baselineBrier)
	item.BaselineLogLoss = floatPointer(all.baselineLogLoss)
	item.ExactScoreRate = floatPointer(all.exact)
	item.TopThreeRate = floatPointer(all.topThree)
	item.TopFiveRate = floatPointer(all.topFive)
	item.TotalsHitRate = floatPointer(all.totals)
	item.BTTSHitRate = floatPointer(all.btts)
	latestStart := max(0, len(records)-50)
	latest := performanceWindow(records, latestStart)
	item.LatestFiftyBrier = floatPointer(latest.brier)
	item.LatestFiftyLog = floatPointer(latest.logLoss)
	item.LatestBaseBrier = floatPointer(latest.baselineBrier)
	item.LatestBaseLog = floatPointer(latest.baselineLogLoss)
	beatsAll := all.brier < all.baselineBrier && all.logLoss < all.baselineLogLoss
	beatsLatest := latest.brier < latest.baselineBrier && latest.logLoss < latest.baselineLogLoss
	if len(records) >= 50 {
		item.Rating = "WATCH"
		if beatsAll {
			item.Rating = "GOOD"
		}
	}
	if len(records) >= 100 && beatsAll && beatsLatest {
		item.Rating = "STRONG"
	}
	return item
}

type performanceMetrics struct {
	hits, brier, logLoss, baselineBrier, baselineLogLoss float64
	exact, topThree, topFive, totals, btts               float64
}

func performanceWindow(records []performanceRecord, start int) performanceMetrics {
	var result performanceMetrics
	for index := start; index < len(records); index++ {
		record := records[index]
		outcome := outcomeKey(record.homeScore, record.awayScore)
		baseline := leagueBaseline(records[:index])
		accumulateOutcomeMetrics(&result, record, outcome, baseline)
		accumulateScoreMetrics(&result, record)
		accumulateMarketMetrics(&result, record)
	}
	count := float64(len(records) - start)
	result.normalize(count)
	return result
}

func accumulateOutcomeMetrics(result *performanceMetrics, record performanceRecord, outcome string, baseline map[string]float64) {
	if maxOutcome(record.probabilities) == outcome {
		result.hits++
	}
	for _, key := range []string{"home", "draw", "away"} {
		target := boolFloat(key == outcome)
		delta := record.probabilities[key] - target
		result.brier += delta * delta
		baselineDelta := baseline[key] - target
		result.baselineBrier += baselineDelta * baselineDelta
	}
	result.logLoss -= math.Log(math.Max(record.probabilities[outcome], 1e-15))
	result.baselineLogLoss -= math.Log(math.Max(baseline[outcome], 1e-15))
}

func accumulateScoreMetrics(result *performanceMetrics, record performanceRecord) {
	ranked := append([]scoreCell(nil), record.scores...)
	sort.Slice(ranked, func(i, j int) bool { return ranked[i].Probability > ranked[j].Probability })
	position := scorePosition(ranked, record.homeScore, record.awayScore)
	result.exact += boolFloat(position == 0)
	result.topThree += boolFloat(position >= 0 && position < 3)
	result.topFive += boolFloat(position >= 0 && position < 5)
}

func accumulateMarketMetrics(result *performanceMetrics, record performanceRecord) {
	actualOver := record.homeScore+record.awayScore > 2
	result.totals += boolFloat((record.probabilities["total_over_2_5"] >= 0.5) == actualOver)
	actualBTTS := record.homeScore > 0 && record.awayScore > 0
	result.btts += boolFloat((record.probabilities["btts_yes"] >= 0.5) == actualBTTS)
}

func (result *performanceMetrics) normalize(count float64) {
	result.hits /= count
	result.brier /= count
	result.logLoss /= count
	result.baselineBrier /= count
	result.baselineLogLoss /= count
	result.exact /= count
	result.topThree /= count
	result.topFive /= count
	result.totals /= count
	result.btts /= count
}

func boolFloat(value bool) float64 {
	if value {
		return 1
	}
	return 0
}

func leagueBaseline(prior []performanceRecord) map[string]float64 {
	counts := map[string]float64{"home": 1, "draw": 1, "away": 1}
	for _, record := range prior {
		counts[outcomeKey(record.homeScore, record.awayScore)]++
	}
	total := counts["home"] + counts["draw"] + counts["away"]
	for key := range counts {
		counts[key] /= total
	}
	return counts
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

func competitionMatchesPerformanceFilter(item Competition, filters PerformanceFilters) bool {
	return filters.CompetitionID == "" || filters.CompetitionID == item.ID
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
	return left.League < right.League
}

func productQueryError(err error) error {
	if errors.Is(err, pgx.ErrNoRows) {
		return errProductUnavailable
	}
	return err
}

func outcomeKey(home, away int) string {
	if home > away {
		return "home"
	}
	if away > home {
		return "away"
	}
	return "draw"
}

func maxOutcome(values map[string]float64) string {
	best := "home"
	for _, key := range []string{"draw", "away"} {
		if values[key] > values[best] {
			best = key
		}
	}
	return best
}

func scorePosition(values []scoreCell, home, away int) int {
	for index, value := range values {
		if value.HomeGoals == home && value.AwayGoals == away {
			return index
		}
	}
	return -1
}

func floatPointer(value float64) *float64 { return &value }

func selectionAgreement(market, selection string, values map[string]float64) (*float64, string) {
	probability, found := selectionProbability(strings.ToUpper(strings.TrimSpace(selection)), values)
	if !found || !validProbability(probability) {
		return nil, "UNABLE_TO_EVALUATE"
	}
	return floatPointer(probability), agreementLabel(market, probability, values)
}

var directSelectionProbabilityKeys = map[string]string{
	"HOME_WIN":        "home",
	"DRAW":            "draw",
	"AWAY_WIN":        "away",
	"BTTS_YES":        "btts_yes",
	"TOTAL_OVER_1_5":  "total_over_1_5",
	"TOTAL_OVER_2_5":  "total_over_2_5",
	"TOTAL_UNDER_2_5": "total_under_2_5",
	"TOTAL_UNDER_3_5": "total_under_3_5",
}

func selectionProbability(selection string, values map[string]float64) (float64, bool) {
	switch selection {
	case "HOME_OR_DRAW":
		return sumProbabilities(values, "home", "draw")
	case "DRAW_OR_AWAY":
		return sumProbabilities(values, "draw", "away")
	}
	if key, found := directSelectionProbabilityKeys[selection]; found {
		return mapProbability(values, key)
	}
	return 0, false
}

func agreementLabel(market string, probability float64, values map[string]float64) string {
	if probability >= 0.5 && (market != "RESULT_1X2" || probability >= values[maxOutcome(values)]) {
		return "AGREES"
	}
	if probability >= 0.4 {
		return "WEAK_SUPPORT"
	}
	return "DISAGREES"
}

func mapProbability(values map[string]float64, key string) (float64, bool) {
	value, ok := values[key]
	return value, ok
}
func validProbability(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0) && value >= 0 && value <= 1
}

func sumProbabilities(values map[string]float64, first, second string) (float64, bool) {
	a, okA := values[first]
	b, okB := values[second]
	return a + b, okA && okB
}
