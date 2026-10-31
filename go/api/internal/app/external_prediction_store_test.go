package app

import (
	"context"
	"errors"
	"testing"
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
