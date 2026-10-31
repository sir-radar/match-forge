package app

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
)

const externalAgreementSQL = `COALESCE(convert_from(comparison.record_bytes,'UTF8')::jsonb->>'agreement','UNABLE_TO_EVALUATE')`
const externalEligibleSQL = `(pf.identity_status='VERIFIED' AND ep.effective_match_status='MATCHED'
    AND ep.date_status IN ('VERIFIED','NOT_APPLICABLE') AND NOT ep.source_revision_conflict
    AND ep.collected_at<pf.kickoff_at AND ep.revision_started_at<pf.kickoff_at
    AND ep.last_observed_at<=statement_timestamp()
    AND validation.generation=validation.completed_generation
    AND (binding.evidence->>'method' IS DISTINCT FROM 'REVIEWED_VERIFIED_PROVIDER_ID'
         OR binding.decided_at<pf.kickoff_at))`
const externalPredictionFromSQL = `
    FROM football.external_prediction_current ep
    JOIN football.external_prediction_sources eps ON eps.source_code=ep.source_code
    LEFT JOIN football.external_prediction_bindings binding ON binding.binding_id=ep.binding_id
    LEFT JOIN football.product_fixtures pf ON pf.fixture_id=ep.effective_fixture_id
    LEFT JOIN football.product_competitions pc ON pc.competition_id=pf.competition_id
    LEFT JOIN football.product_teams home ON home.team_id=pf.home_team_id
    LEFT JOIN football.product_teams away ON away.team_id=pf.away_team_id
    LEFT JOIN football.external_prediction_refresh_work validation ON validation.prediction_id=ep.prediction_id
    CROSS JOIN LATERAL (SELECT football.public_comparison_source(ep.prediction_id) AS value) source
    LEFT JOIN LATERAL (
        SELECT r.record_bytes,r.record_sha256 FROM football.product_read_reports r
        WHERE r.report_kind='COMPARISON' AND r.scope_id=ep.prediction_id AND r.horizon='LATEST'
          AND validation.generation=validation.completed_generation
          AND r.source_fingerprint=encode(sha256(convert_to(source.value::text,'UTF8')),'hex')
        ORDER BY r.source_observed_at DESC,r.registered_at DESC,r.input_sha256 LIMIT 1
    ) comparison ON true
    LEFT JOIN football.product_report_refresh_work report_work
      ON report_work.report_kind='COMPARISON' AND report_work.scope_id=ep.prediction_id
      AND report_work.horizon='LATEST'
    LEFT JOIN football.external_prediction_current_results result ON result.prediction_id=ep.prediction_id
    WHERE true`

func filteredExternalPredictions(filters ExternalPredictionFilters) (string, []any) {
	query, args := externalPredictionFromSQL, []any{}
	if !filters.Date.IsZero() {
		args = append(args, filters.Date)
		query += fmt.Sprintf(" AND ep.prediction_date=$%d", len(args))
	}
	query = addPredictionDateRange(query, &args, filters)
	for _, filter := range []struct{ column, value string }{
		{"ep.source_code", filters.Source}, {"pc.continent", filters.Continent},
		{"COALESCE(pc.geographic_scope,pc.country)", filters.Country},
		{"ep.competition_text", filters.Competition}, {"ep.market", filters.Market},
		{"ep.effective_fixture_id::text", filters.FixtureID}, {externalAgreementSQL, filters.Agreement},
	} {
		query = addFilter(query, &args, filter.column, filter.value)
	}
	return query, args
}

func externalPagination(total, page, size int) Pagination {
	if page < 1 {
		page = 1
	}
	if size != 20 && size != 50 && size != 100 {
		size = 20
	}
	pages := total / size
	if total%size != 0 {
		pages++
	}
	if pages == 0 {
		page = 1
	} else if page > pages {
		page = pages
	}
	return Pagination{Page: page, PageSize: size, TotalItems: total, TotalPages: pages}
}

func (store *PostgresProductStore) ExternalPredictions(ctx context.Context, filters ExternalPredictionFilters) (ExternalPredictionPage, error) {
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return ExternalPredictionPage{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	query, args := filteredExternalPredictions(filters)
	var total int
	if err := tx.QueryRow(ctx, "SELECT count(*)"+query, args...).Scan(&total); err != nil {
		return ExternalPredictionPage{}, err
	}
	pagination := externalPagination(total, filters.Page, filters.PageSize)
	items, err := externalPredictionRows(ctx, tx, query, args, pagination)
	if err != nil {
		return ExternalPredictionPage{}, err
	}
	consensus, err := externalConsensus(ctx, tx, query, args)
	if err != nil {
		return ExternalPredictionPage{}, err
	}
	return ExternalPredictionPage{Predictions: items, Pagination: pagination, Consensus: consensus}, tx.Commit(ctx)
}

func externalPredictionRows(ctx context.Context, tx pgx.Tx, query string, args []any, page Pagination) ([]ExternalPrediction, error) {
	columns := `SELECT ep.prediction_id::text,eps.name,ep.source_page,ep.prediction_date::text,
        ep.original_date_text,ep.collected_at,ep.effective_fixture_id::text,pf.kickoff_at,
        ep.competition_text,ep.home_team_text,ep.away_team_text,ep.market,ep.selection,
        ep.effective_match_status,comparison.record_bytes,comparison.record_sha256,
        source.value->>'forecast_id',COALESCE(result.settlement_state,'PENDING'),
        result.home_score,result.away_score,result.score_basis,result.provider_code,
        result.provider_updated_at,report_work.last_error,ep.source_code,pf.identity_status,
        ep.date_status,ep.source_revision_conflict`
	args = append(args, page.PageSize, (page.Page-1)*page.PageSize)
	query += fmt.Sprintf(" ORDER BY ep.prediction_date DESC,ep.collected_at DESC,ep.prediction_id DESC LIMIT $%d OFFSET $%d", len(args)-1, len(args))
	rows, err := tx.Query(ctx, columns+query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, scanExternalPrediction)
}

func scanExternalPrediction(row pgx.CollectableRow) (ExternalPrediction, error) {
	var item ExternalPrediction
	var comparison []byte
	var digest, forecastID, comparisonError *string
	if err := row.Scan(&item.ID, &item.Source, &item.SourcePage, &item.PredictionDate,
		&item.OriginalDateText, &item.CollectedAt, &item.FixtureID, &item.KickoffAt,
		&item.Competition, &item.HomeTeam, &item.AwayTeam, &item.Market, &item.Selection,
		&item.MatchStatus, &comparison, &digest, &forecastID, &item.SettlementState,
		&item.ActualHomeScore, &item.ActualAwayScore, &item.ResultScoreBasis, &item.ResultProvider,
		&item.ResultUpdatedAt, &comparisonError, &item.SourceCode, &item.FixtureIdentityStatus,
		&item.SourceDateStatus, &item.SourceRevisionConflict); err != nil {
		return item, err
	}
	if err := attachComparison(&item, forecastID, comparison, digest); err != nil {
		return item, err
	}
	if item.ComparisonStatus == "PENDING" && comparisonError != nil {
		item.ComparisonStatus = "FAILED"
	}
	if item.SourceDateStatus == "MISMATCH" || item.SourceDateStatus == "UNKNOWN" {
		item.ComparisonStatus = "QUARANTINED"
	}
	return item, nil
}

func externalConsensus(ctx context.Context, tx pgx.Tx, query string, args []any) ([]ExternalConsensus, error) {
	votes := `WITH selections AS (SELECT ep.effective_fixture_id AS fixture_id,ep.market,
        ep.selection,ep.source_code,pf.kickoff_at,home.name||' vs '||away.name AS fixture,
        ` + externalAgreementSQL + ` AS agreement ` + query + `
        AND ` + externalEligibleSQL + ` AND eps.public_predictions AND eps.adapter_status='ENABLED'
        AND convert_from(comparison.record_bytes,'UTF8')::jsonb->>'matchforge_probability' IS NOT NULL
        AND ((ep.market='RESULT_1X2' AND ep.selection IN ('HOME_WIN','DRAW','AWAY_WIN'))
          OR (ep.market='DOUBLE_CHANCE' AND ep.selection IN ('HOME_OR_DRAW','DRAW_OR_AWAY'))
          OR (ep.market='TOTAL_GOALS' AND ep.selection IN ('TOTAL_OVER_1_5','TOTAL_OVER_2_5','TOTAL_UNDER_2_5','TOTAL_UNDER_3_5'))
          OR (ep.market='BTTS' AND ep.selection='BTTS_YES'))
    ), counts AS (SELECT fixture_id,market,selection,count(DISTINCT source_code) AS votes,
        min(kickoff_at) AS kickoff,min(fixture) AS fixture,min(agreement) AS agreement
        FROM selections GROUP BY fixture_id,market,selection), totals AS (
        SELECT *,sum(votes) OVER(PARTITION BY fixture_id,market) AS total FROM counts)
    SELECT fixture_id::text||':'||market,fixture,market,kickoff,selection,votes,total,agreement
    FROM totals WHERE votes>=2 AND votes*2>total ORDER BY votes DESC,fixture_id,market LIMIT 3`
	// Display labels are metadata joined by verified IDs; never grouping keys.
	rows, err := tx.Query(ctx, votes, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (ExternalConsensus, error) {
		var item ExternalConsensus
		err := row.Scan(&item.ID, &item.Fixture, &item.Market, &item.Kickoff, &item.Selection, &item.Count, &item.Total, &item.Agreement)
		return item, err
	})
}

func (store *PostgresProductStore) ExternalPredictionSources(ctx context.Context, filters ExternalPredictionFilters) ([]ExternalPredictionSource, error) {
	query, args := filteredExternalPredictions(filters)
	statement := `WITH filtered AS (SELECT ep.source_code,` + externalEligibleSQL + ` AS prospective,
        ep.collected_at,ep.revision_started_at,pf.kickoff_at,
        (binding.evidence->>'method'='REVIEWED_VERIFIED_PROVIDER_ID' AND binding.decided_at>=pf.kickoff_at) AS reviewed_late,
        result.settlement_state,` + externalAgreementSQL + ` AS agreement ` + query + `),
    metrics AS (SELECT source_code,count(*)::int AS tracked,
        count(*) FILTER(WHERE prospective AND settlement_state IN ('WON','LOST'))::int AS settled,
        count(*) FILTER(WHERE prospective AND settlement_state='WON')::int AS correct,
        avg((settlement_state='WON')::int) FILTER(WHERE prospective AND settlement_state IN ('WON','LOST'))::float8 AS hit_rate,
        avg((agreement='AGREES')::int) FILTER(WHERE prospective AND agreement<>'UNABLE_TO_EVALUATE')::float8 AS agreement_rate,
        count(*) FILTER(WHERE prospective)::int AS prospective_count,
        count(*) FILTER(WHERE collected_at>=kickoff_at OR revision_started_at>=kickoff_at OR reviewed_late)::int AS retrospective_count
        FROM filtered GROUP BY source_code)
    SELECT source.source_code,source.name,source.base_url,source.public_predictions,
        source.prediction_date_available,source.login_required,source.paid_content,
        source.automated_access_status,source.adapter_status,source.known_issues,source.checked_at,
        COALESCE(metrics.tracked,0),COALESCE(metrics.settled,0),COALESCE(metrics.correct,0),
        metrics.hit_rate,metrics.agreement_rate,COALESCE(metrics.prospective_count,0),
        COALESCE(metrics.retrospective_count,0),attempt.collected_at,CASE WHEN attempt.collected_at IS NULL THEN NULL
            WHEN attempt.attempted THEN attempt.status
            WHEN attempt.status='NO_DATE_PAGE' THEN 'OUTSIDE_WINDOW' ELSE 'DISABLED' END,
        attempt.error_message
    FROM football.external_prediction_sources source LEFT JOIN metrics USING(source_code)
    LEFT JOIN LATERAL (SELECT collected_at,status,error_message,attempted
        FROM football.external_prediction_collection_attempts attempt
        WHERE attempt.source_code=source.source_code
        ORDER BY collected_at DESC,attempt_id DESC LIMIT 1) attempt ON true
    WHERE true`
	if filters.Source != "" {
		statement = addFilter(statement, &args, "source.source_code", filters.Source)
	}
	statement += " ORDER BY source.name"
	rows, err := store.pool.Query(ctx, statement, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (ExternalPredictionSource, error) {
		var item ExternalPredictionSource
		err := row.Scan(&item.Code, &item.Name, &item.URL, &item.PublicPredictions, &item.PredictionDate,
			&item.LoginRequired, &item.PaidContent, &item.AutomatedAccessStatus, &item.AdapterStatus,
			&item.KnownIssues, &item.CheckedAt, &item.TrackedSelections, &item.SettledSelections,
			&item.CorrectSelections, &item.SettledHitRate, &item.AgreementRate, &item.ProspectiveSelections,
			&item.RetrospectiveSelections, &item.LastCollectionAt, &item.LastCollectionStatus, &item.CollectionError)
		return item, err
	})
}
