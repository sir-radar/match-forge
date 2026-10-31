package app

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
)

const analyticsPolicyVersion = "pre-match-revisions-v2"

func performanceHorizonSeconds(horizon string) (int, error) {
	switch horizon {
	case "", "LATEST":
		return 0, nil
	case "7D":
		return 7 * 86400, nil
	case "3D":
		return 3 * 86400, nil
	case "24H":
		return 86400, nil
	case "6H":
		return 6 * 3600, nil
	case "1H":
		return 3600, nil
	case "15M":
		return 900, nil
	default:
		return 0, errors.New("invalid analytics horizon")
	}
}

func (store *PostgresProductStore) Performance(ctx context.Context, competitionID, horizon string) (Performance, error) {
	page, err := store.Performances(ctx, PerformanceFilters{CompetitionID: competitionID, Horizon: horizon, Page: 1, PageSize: 20})
	if err != nil {
		return Performance{}, err
	}
	if len(page.Performance) == 0 {
		return Performance{}, errProductUnavailable
	}
	if page.Performance[0].ReportStatus == "PENDING" || page.Performance[0].ReportStatus == "FAILED" {
		return Performance{}, errProductUnavailable
	}
	return page.Performance[0], nil
}

func (store *PostgresProductStore) Performances(ctx context.Context, filters PerformanceFilters) (PerformancePage, error) {
	seconds, err := performanceHorizonSeconds(filters.Horizon)
	if err != nil {
		return PerformancePage{}, err
	}
	items, err := store.performanceCompetitions(ctx, filters)
	if err != nil {
		return PerformancePage{}, err
	}
	// Rating/count filters depend on the selected forecasts. Otherwise paginate metadata first.
	var page PerformancePage
	scoped := items
	if filters.Rating == "" && filters.MinimumForecasts == 0 {
		page = paginatePerformances(items, filters.Page, filters.PageSize)
		scoped = page.Performance
	}
	reports, err := store.performanceReports(ctx, scoped, seconds, filters.Horizon)
	if err != nil {
		return PerformancePage{}, err
	}
	for index, metadata := range scoped {
		if err := ctx.Err(); err != nil {
			return PerformancePage{}, err
		}
		item := reports[metadata.CompetitionID]
		item.League, item.Country, item.Continent = metadata.League, metadata.Country, metadata.Continent
		scoped[index] = item
	}
	if filters.Rating == "" && filters.MinimumForecasts == 0 {
		page.Performance = scoped
		return page, nil
	}
	return filterSortAndPaginatePerformances(scoped, filters), nil
}

func (store *PostgresProductStore) performanceCompetitions(ctx context.Context, filters PerformanceFilters) ([]Performance, error) {
	query := `SELECT competition_id::text,name,COALESCE(geographic_scope,country),continent FROM football.product_competitions WHERE true`
	args := []any{}
	query = addFilter(query, &args, "continent", filters.Continent)
	query = addFilter(query, &args, "COALESCE(geographic_scope,country)", filters.Country)
	if filters.CompetitionID != "" {
		var id pgtype.UUID
		if err := id.Scan(filters.CompetitionID); err != nil {
			return nil, err
		}
		args = append(args, id)
		query += fmt.Sprintf(" AND competition_id=$%d", len(args))
	}
	query += ` ORDER BY continent COLLATE "C",COALESCE(geographic_scope,country) COLLATE "C",name COLLATE "C",competition_id`
	rows, err := store.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []Performance{}
	for rows.Next() {
		var item Performance
		if err := rows.Scan(&item.CompetitionID, &item.League, &item.Country, &item.Continent); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (store *PostgresProductStore) performanceReports(ctx context.Context, items []Performance, seconds int, horizon string) (map[string]Performance, error) {
	reports := map[string]Performance{}
	if len(items) == 0 {
		return reports, nil
	}
	if horizon == "" {
		horizon = "LATEST"
	}
	ids := make([]pgtype.UUID, len(items))
	for index, item := range items {
		if err := ids[index].Scan(item.CompetitionID); err != nil {
			return nil, err
		}
	}
	rows, err := store.pool.Query(ctx, `SELECT c.id::text,source.record_count,report.record_bytes,report.record_sha256,work.last_error
        FROM unnest($1::uuid[]) c(id)
        CROSS JOIN LATERAL football.public_performance_source(c.id,$2) source
        LEFT JOIN LATERAL (
            SELECT r.record_bytes,r.record_sha256 FROM football.product_read_reports r
            WHERE r.report_kind='PERFORMANCE' AND r.scope_id=c.id AND r.horizon=$3
              AND r.source_fingerprint=source.source_fingerprint
            ORDER BY r.source_observed_at DESC,r.registered_at DESC,r.input_sha256 LIMIT 1
        ) report ON true
        LEFT JOIN football.product_report_refresh_work work
            ON work.report_kind='PERFORMANCE' AND work.scope_id=c.id AND work.horizon=$3`, ids, seconds, horizon)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		item, err := scanPerformanceReport(rows, horizon)
		if err != nil {
			return nil, err
		}
		reports[item.CompetitionID] = item
	}
	return reports, rows.Err()
}

func scanPerformanceReport(row pgx.Row, horizon string) (Performance, error) {
	var id string
	var count int
	var payload []byte
	var digest, failure *string
	if err := row.Scan(&id, &count, &payload, &digest, &failure); err != nil {
		return Performance{}, err
	}
	item, err := decodePerformanceReport(id, horizon, count, payload, digest)
	if err != nil {
		return Performance{}, err
	}
	if item.ReportStatus == "PENDING" && failure != nil {
		item.ReportStatus = "FAILED"
	}
	return item, nil
}

func decodePerformanceReport(id, horizon string, count int, payload []byte, digest *string) (Performance, error) {
	if count == 0 && payload == nil {
		return Performance{CompetitionID: id, AnalyticsPolicyVersion: analyticsPolicyVersion, AnalyticsHorizon: horizon, Rating: "UNRATED", ReportStatus: "EMPTY"}, nil
	}
	if payload == nil || digest == nil {
		return Performance{CompetitionID: id, AnalyticsPolicyVersion: analyticsPolicyVersion, AnalyticsHorizon: horizon, Rating: "UNRATED", Forecasts: count, ReportStatus: "PENDING"}, nil
	}
	var item Performance
	if err := decodeReadReport(payload, digest, &item); err != nil {
		return item, err
	}
	if item.CompetitionID != id || item.Forecasts != count || item.AnalyticsHorizon != horizon || item.AnalyticsPolicyVersion != analyticsPolicyVersion {
		return Performance{}, errors.New("stored performance report identity mismatch")
	}
	item.ReportStatus = "READY"
	return item, nil
}
