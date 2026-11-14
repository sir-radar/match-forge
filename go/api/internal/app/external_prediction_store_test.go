package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"testing"
	"time"
)

func TestExternalPredictionReadersDatabase(t *testing.T) {
	store, counter := performanceDatabaseStore(t)
	first, second := verifyExternalPages(t, store)
	verifyExternalPageIdentities(t, first, second)
	verifyExternalConsensus(t, first)
	verifyExternalSourceMetrics(t, store, counter)
	verifyExternalPendingCorrection(t, store)
}

func verifyExternalPages(t *testing.T, store *PostgresProductStore) (ExternalPredictionPage, ExternalPredictionPage) {
	t.Helper()
	first, err := store.ExternalPredictions(context.Background(), ExternalPredictionFilters{Page: 1, PageSize: 20})
	if err != nil {
		t.Fatal(err)
	}
	second, err := store.ExternalPredictions(context.Background(), ExternalPredictionFilters{Page: 2, PageSize: 20})
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Predictions) != 20 || len(second.Predictions) != 8 || first.Pagination.TotalItems != 28 {
		t.Fatalf("incorrect bounded page counts: %+v %+v", first.Pagination, second.Pagination)
	}
	return first, second
}

func verifyExternalPageIdentities(t *testing.T, pages ...ExternalPredictionPage) {
	t.Helper()
	ids := map[string]bool{}
	for _, page := range pages {
		for _, row := range page.Predictions {
			if ids[row.ID] {
				t.Fatal("duplicate across pages")
			}
			ids[row.ID] = true
		}
	}
}

func verifyExternalConsensus(t *testing.T, page ExternalPredictionPage) {
	t.Helper()
	if len(page.Consensus) != 1 {
		t.Fatalf("invalid consensus groups: %+v", page.Consensus)
	}
	item := page.Consensus[0]
	if item.Count != 2 || item.Total != 2 || item.Market != "RESULT_1X2" {
		t.Fatalf("invalid independent-source consensus: %+v", item)
	}
}

func verifyExternalSourceMetrics(t *testing.T, store *PostgresProductStore, counter *performanceQueryCounter) {
	t.Helper()
	counter.queries.Store(0)
	sources, err := store.ExternalPredictionSources(context.Background(), ExternalPredictionFilters{Source: "r2bet"})
	if err != nil {
		t.Fatal(err)
	}
	if counter.queries.Load() != 1 {
		t.Fatalf("source aggregation uses %d queries", counter.queries.Load())
	}
	if len(sources) != 1 {
		t.Fatalf("unexpected source scope: %+v", sources)
	}
	source := sources[0]
	verifyUnobservedCollection(t, source)
	if source.TrackedSelections != 2 || source.SettledSelections != 1 || source.CorrectSelections != 1 || source.RetrospectiveSelections != 1 {
		t.Fatalf("incorrect current/prospective denominators: %+v", source)
	}
}

func verifyUnobservedCollection(t *testing.T, source ExternalPredictionSource) {
	t.Helper()
	if source.LastCollectionAt != nil || source.LastCollectionStatus != nil {
		t.Fatalf("missing collection evidence was given a health status: %+v", source)
	}
}

func verifyExternalPendingCorrection(t *testing.T, store *PostgresProductStore) {
	t.Helper()
	ctx := context.Background()
	if _, err := store.pool.Exec(ctx, "UPDATE football.product_fixtures SET home_score=0,away_score=3"); err != nil {
		t.Fatal(err)
	}
	sources, err := store.ExternalPredictionSources(ctx, ExternalPredictionFilters{Source: "r2bet"})
	if err != nil {
		t.Fatal(err)
	}
	if len(sources) != 1 || sources[0].SettledSelections != 0 || sources[0].SettledHitRate != nil {
		t.Fatalf("pending correction counted obsolete settlement: %+v", sources)
	}
	verifyExternalPendingReports(t, store)
	cancelled, cancel := context.WithCancel(ctx)
	cancel()
	if _, err := store.ExternalPredictions(cancelled, ExternalPredictionFilters{}); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation lost: %v", err)
	}
}

func TestExternalPredictionCorrectedMetricsDatabase(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	sources, err := store.ExternalPredictionSources(context.Background(), ExternalPredictionFilters{Source: "r2bet"})
	if err != nil {
		t.Fatal(err)
	}
	if len(sources) != 1 || sources[0].SettledSelections != 1 || sources[0].CorrectSelections != 0 || sources[0].SettledHitRate == nil || *sources[0].SettledHitRate != 0 {
		t.Fatalf("source accuracy ignored current correction: %+v", sources)
	}
}

func TestExternalPredictionArchiveBoundDatabase(t *testing.T) {
	store, counter := performanceDatabaseStore(t)
	ctx, cancel := context.WithTimeout(context.Background(), defaultHandlerTimeout)
	defer cancel()
	counter.queries.Store(0)
	started := time.Now()
	page, err := store.ExternalPredictions(ctx, ExternalPredictionFilters{PageSize: 100})
	if err != nil {
		t.Fatal(err)
	}
	elapsed := time.Since(started)
	if len(page.Predictions) != 100 || page.Pagination.TotalItems != 5001 {
		t.Fatalf("archive page is not bounded: %+v rows=%d", page.Pagination, len(page.Predictions))
	}
	t.Logf("5001 current selections: page/aggregate latency=%s queries=%d rows=%d", elapsed, counter.queries.Load(), len(page.Predictions))
	sources, err := store.ExternalPredictionSources(ctx, ExternalPredictionFilters{Source: "manual_import"})
	if err != nil || len(sources) != 1 || sources[0].TrackedSelections != 5000 {
		t.Fatalf("archive source aggregate: %+v %v", sources, err)
	}
}

func TestExternalPredictionContinuousArchiveDatabase(t *testing.T) {
	store, counter := performanceDatabaseStore(t)
	ctx, cancel := context.WithTimeout(context.Background(), defaultHandlerTimeout)
	defer cancel()
	var day time.Time
	if err := store.pool.QueryRow(ctx, "SELECT CURRENT_DATE").Scan(&day); err != nil {
		t.Fatal(err)
	}
	counter.queries.Store(0)
	started := time.Now()
	archive, err := store.ExternalPredictions(ctx, ExternalPredictionFilters{Archive: true, Date: day})
	if err != nil || len(archive.Predictions) != 5001 {
		t.Fatalf("selected day rows=%d error=%v", len(archive.Predictions), err)
	}
	elapsed := time.Since(started)
	payload, err := json.Marshal(archive.Predictions)
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("5001 daily selections: store latency=%s queries=%d records_bytes=%d", elapsed, counter.queries.Load(), len(payload))
	started = time.Now()
	filtered, err := store.ExternalPredictions(ctx, ExternalPredictionFilters{
		Archive: true, Date: day, Search: "Home 5000", Competition: "Synthetic",
		Settlement: "PENDING", Source: "manual_import",
	})
	if err != nil || len(filtered.Predictions) != 1 || filtered.Predictions[0].HomeTeam != "Home 5000" {
		t.Fatalf("filtered rows=%d error=%v", len(filtered.Predictions), err)
	}
	t.Logf("5001 daily selections: filtered store latency=%s", time.Since(started))
}

func TestReviewedExternalAccuracyDatabase(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	sources, err := store.ExternalPredictionSources(context.Background(), ExternalPredictionFilters{Source: "manual_import"})
	if err != nil {
		t.Fatal(err)
	}
	if len(sources) != 1 || sources[0].SettledSelections != 0 || sources[0].RetrospectiveSelections != 1 {
		t.Fatalf("post-kickoff identity review received prospective credit: %+v", sources)
	}
}

func verifyExternalPendingReports(t *testing.T, store *PostgresProductStore) {
	t.Helper()
	page, err := store.ExternalPredictions(context.Background(), ExternalPredictionFilters{Source: "r2bet"})
	if err != nil {
		t.Fatal(err)
	}
	if len(page.Predictions) != 2 {
		t.Fatalf("pending selections disappeared: %+v", page.Pagination)
	}
	for _, prediction := range page.Predictions {
		if prediction.ComparisonStatus != "PENDING" || prediction.MatchForgeProbability != nil {
			t.Fatalf("pending validation exposed an obsolete comparison: %+v", prediction)
		}
	}
	if len(page.Consensus) != 0 {
		t.Fatalf("pending validation contributed consensus: %+v", page.Consensus)
	}
}

// Seeded by tests/integration/test_external_contextual_matching.py: one pre-kickoff
// pick linked by the contextual policy, settled without an internal forecast.
func TestExternalContextualAssociationDatabase(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	ctx := context.Background()
	day := time.Date(2030, 1, 1, 0, 0, 0, 0, time.UTC)
	page, err := store.ExternalPredictions(ctx, ExternalPredictionFilters{Archive: true, Date: day})
	if err != nil || len(page.Predictions) != 1 {
		t.Fatalf("rows=%d error=%v", len(page.Predictions), err)
	}
	item := page.Predictions[0]
	association := item.Association
	got := []string{item.MatchStatus, association.Classification, association.Reason,
		fmt.Sprint(association.SettlementEligible), valueOrEmpty(association.Basis),
		valueOrEmpty(association.Evaluation), valueOrEmpty(association.FixtureHomeTeam), item.SettlementState}
	want := []string{"CONTEXTUAL", "CONTEXTUAL_MATCH", "UNIQUE_SAME_DAY", "true", "POLICY", "PROSPECTIVE", "Home", "WON"}
	if !slices.Equal(got, want) {
		t.Fatalf("contextual association not exposed: got %v want %v", got, want)
	}
	sources, err := store.ExternalPredictionSources(ctx, ExternalPredictionFilters{Source: "manual_import"})
	if err != nil || len(sources) != 1 || sources[0].SettledSelections != 1 || sources[0].ProspectiveSelections != 1 {
		t.Fatalf("contextual prospective settlement not counted: %+v error=%v", sources, err)
	}
}
