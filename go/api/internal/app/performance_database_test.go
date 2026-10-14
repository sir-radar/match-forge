package app

import (
	"context"
	"os"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type performanceQueryCounter struct{ queries atomic.Int32 }

func (counter *performanceQueryCounter) TraceQueryStart(ctx context.Context, _ *pgx.Conn, _ pgx.TraceQueryStartData) context.Context {
	counter.queries.Add(1)
	return ctx
}
func (*performanceQueryCounter) TraceQueryEnd(context.Context, *pgx.Conn, pgx.TraceQueryEndData) {}

// Invoked by the disposable PostgreSQL regression; never points at production.
func performanceDatabaseStore(t *testing.T) (*PostgresProductStore, *performanceQueryCounter) {
	t.Helper()
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("requires disposable integration database")
	}
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		t.Fatal(err)
	}
	counter := &performanceQueryCounter{}
	config.ConnConfig.Tracer = counter
	pool, err := pgxpool.NewWithConfig(context.Background(), config)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	return NewPostgresProductStore(pool), counter
}

func TestPerformanceBatchDatabase(t *testing.T) {
	store, counter := performanceDatabaseStore(t)
	tests := []PerformanceFilters{
		{Page: 1, PageSize: 20},
		{Page: 2, PageSize: 50},
		{Page: 1, PageSize: 20, MinimumForecasts: 1},
		{Page: 1, PageSize: 20, Rating: "UNRATED"},
	}
	for _, filter := range tests {
		counter.queries.Store(0)
		page, err := store.Performances(context.Background(), filter)
		if err != nil {
			t.Fatal(err)
		}
		if counter.queries.Load() != 2 {
			t.Fatalf("N+1 queries: %d", counter.queries.Load())
		}
		if filter.MinimumForecasts == 1 && (len(page.Performance) != 1 || page.Performance[0].Forecasts != 1) {
			t.Fatalf("revision duplicate denominator: %+v", page)
		}
		for _, item := range page.Performance {
			if item.AnalyticsPolicyVersion != analyticsPolicyVersion || item.AnalyticsHorizon != "LATEST" {
				t.Fatalf("missing version: %+v", item)
			}
		}
	}
}

func TestPerformanceBatchDatabaseCanonicalCountry(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	page, err := store.Performances(context.Background(), PerformanceFilters{Page: 1, PageSize: 20, Country: "International"})
	if err != nil {
		t.Fatal(err)
	}
	if len(page.Performance) != 1 || page.Performance[0].Country != "International" {
		t.Fatalf("canonical country filter: %+v", page)
	}
}

func TestPerformanceBatchDatabaseCancellation(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := store.Performances(ctx, PerformanceFilters{Page: 1, PageSize: 20}); err == nil {
		t.Fatal("cancelled query continued")
	}
	ctx, cancel = context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if _, err := store.Performance(ctx, "invalid", "LATEST"); err == nil {
		t.Fatal("invalid UUID accepted")
	}
}
