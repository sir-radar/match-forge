package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"sort"
	"strconv"

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
	records, err := store.performanceRecords(ctx, scoped, seconds)
	if err != nil {
		return PerformancePage{}, err
	}
	for index, metadata := range scoped {
		if err := ctx.Err(); err != nil {
			return PerformancePage{}, err
		}
		scoped[index] = competitionPerformance(metadata, records[metadata.CompetitionID], filters.Horizon)
	}
	if filters.Rating == "" && filters.MinimumForecasts == 0 {
		page.Performance = scoped
		return page, nil
	}
	return filterSortAndPaginatePerformances(scoped, filters), nil
}

func (store *PostgresProductStore) performanceCompetitions(ctx context.Context, filters PerformanceFilters) ([]Performance, error) {
	query := `SELECT competition_id::text,name,country,continent FROM football.product_competitions WHERE true`
	args := []any{}
	query = addFilter(query, &args, "continent", filters.Continent)
	query = addFilter(query, &args, "country", filters.Country)
	if filters.CompetitionID != "" {
		var id pgtype.UUID
		if err := id.Scan(filters.CompetitionID); err != nil {
			return nil, err
		}
		args = append(args, id)
		query += fmt.Sprintf(" AND competition_id=$%d", len(args))
	}
	query += ` ORDER BY continent COLLATE "C",country COLLATE "C",name COLLATE "C",competition_id`
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

func (store *PostgresProductStore) performanceRecords(ctx context.Context, items []Performance, seconds int) (map[string][]performanceRecord, error) {
	records := map[string][]performanceRecord{}
	if len(items) == 0 {
		return records, nil
	}
	ids := make([]pgtype.UUID, len(items))
	for index, item := range items {
		if err := ids[index].Scan(item.CompetitionID); err != nil {
			return nil, err
		}
	}
	rows, err := store.pool.Query(ctx, `SELECT competition_id::text,probabilities,score_matrix,home_score,away_score,kickoff_at,knowledge_cutoff,outcome_known_at,score_matrix_version,model_algorithm_version FROM football.product_performance_forecasts($1::uuid[],$2) ORDER BY kickoff_at,fixture_id`, ids, seconds)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var id, version, algorithm string
		var probabilities, matrix []byte
		var record performanceRecord
		if err := rows.Scan(&id, &probabilities, &matrix, &record.homeScore, &record.awayScore, &record.kickoff, &record.knowledgeCutoff, &record.outcomeKnownAt, &version, &algorithm); err != nil {
			return nil, err
		}
		if err := record.decode(probabilities, matrix, version, algorithm); err != nil {
			return nil, err
		}
		records[id] = append(records[id], record)
	}
	return records, rows.Err()
}

func qualifyScoreBuckets(cells []scoreCell, version, algorithm string) error {
	if version == "legacy-compact-index-v1" && algorithm != "transferable-rolling-goals-poisson-v1" && algorithm != "transferable-rolling-goals-poisson-v1-rolling10-v2" {
		return errors.New("unsupported legacy score interpretation")
	}
	if version != "legacy-compact-index-v1" && version != "compact-buckets-v2" {
		return errors.New("unsupported score matrix version")
	}
	for index := range cells {
		cell := &cells[index]
		if err := qualifyScoreBucket(cell.HomeGoals, &cell.HomeKind, &cell.HomeLabel, version); err != nil {
			return err
		}
		if err := qualifyScoreBucket(cell.AwayGoals, &cell.AwayKind, &cell.AwayLabel, version); err != nil {
			return err
		}
	}
	return nil
}

func qualifyScoreBucket(goals int, kind, label *string, version string) error {
	if goals < 0 {
		return errors.New("invalid score bucket")
	}
	if version == "legacy-compact-index-v1" {
		if goals > 5 {
			return errors.New("invalid legacy score bucket")
		}
		*kind = "EXACT"
		if goals == 5 {
			*kind = "AT_LEAST"
		}
		*label = strconv.Itoa(goals)
		if *kind == "AT_LEAST" {
			*label += "+"
		}
		return nil
	}
	if *kind != "EXACT" && *kind != "AT_LEAST" {
		return errors.New("invalid score bucket kind")
	}
	expected := strconv.Itoa(goals)
	if *kind == "AT_LEAST" {
		expected += "+"
	}
	if *label != expected {
		return errors.New("inconsistent score bucket label")
	}
	return nil
}

func scoreBucketMatches(minimum int, kind string, goals int) bool {
	if kind == "AT_LEAST" {
		return goals >= minimum
	}
	return goals == minimum
}

// Sweep known outcomes against each forecast's cutoff. Unknown availability is
// excluded; same-kickoff outcomes necessarily become known after that cutoff.
func performanceBaselines(records []performanceRecord) []map[string]float64 {
	events := []int{}
	queries := make([]int, len(records))
	for index, record := range records {
		queries[index] = index
		if record.outcomeKnownAt != nil && record.outcomeKnownAt.After(record.kickoff) {
			events = append(events, index)
		}
	}
	sort.Slice(events, func(i, j int) bool {
		return records[events[i]].outcomeKnownAt.Before(*records[events[j]].outcomeKnownAt)
	})
	sort.Slice(queries, func(i, j int) bool {
		return records[queries[i]].knowledgeCutoff.Before(records[queries[j]].knowledgeCutoff)
	})
	counts := map[string]float64{"home": 1, "draw": 1, "away": 1}
	baselines := make([]map[string]float64, len(records))
	event := 0
	total := 3.0
	for _, index := range queries {
		for event < len(events) && !records[events[event]].outcomeKnownAt.After(records[index].knowledgeCutoff) {
			prior := records[events[event]]
			counts[outcomeKey(prior.homeScore, prior.awayScore)]++
			total++
			event++
		}
		baselines[index] = map[string]float64{"home": counts["home"] / total, "draw": counts["draw"] / total, "away": counts["away"] / total}
	}
	return baselines
}

func qualifyPerformanceProbabilities(values map[string]float64) error {
	for _, key := range []string{"home", "draw", "away", "total_over_2_5", "btts_yes"} {
		value, found := values[key]
		if !found || !validProbability(value) {
			return errors.New("invalid stored performance probabilities")
		}
	}
	if math.Abs(values["home"]+values["draw"]+values["away"]-1) > 1e-10 {
		return errors.New("invalid stored outcome probability sum")
	}
	return nil
}

func (record *performanceRecord) decode(probabilities, matrix []byte, version, algorithm string) error {
	if json.Unmarshal(probabilities, &record.probabilities) != nil || json.Unmarshal(matrix, &record.scores) != nil {
		return errors.New("stored forecast JSON is invalid")
	}
	if err := qualifyPerformanceProbabilities(record.probabilities); err != nil {
		return err
	}
	return qualifyScoreBuckets(record.scores, version, algorithm)
}

func competitionPerformance(metadata Performance, records []performanceRecord, horizon string) Performance {
	item := calculatePerformance(metadata.CompetitionID, records)
	item.League, item.Country, item.Continent = metadata.League, metadata.Country, metadata.Continent
	item.AnalyticsPolicyVersion = analyticsPolicyVersion
	if horizon == "" {
		horizon = "LATEST"
	}
	item.AnalyticsHorizon = horizon
	return item
}
