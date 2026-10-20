package app

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestReadReportChecksumAndAbsence(t *testing.T) {
	var item Performance
	if err := decodeReadReport(nil, nil, &item); !errors.Is(err, errProductUnavailable) {
		t.Fatal(err)
	}
	payload := []byte(`{"competition_id":"test","forecasts":7}`)
	sum := sha256.Sum256(payload)
	digest := hex.EncodeToString(sum[:])
	if err := decodeReadReport(payload, &digest, &item); err != nil || item.Forecasts != 7 {
		t.Fatalf("%+v %v", item, err)
	}
	if decodeReadReport(append(payload, ' '), &digest, &item) == nil {
		t.Fatal("corruption accepted")
	}
}

func TestPerformanceReportIdentityAndVerifiedEmptyState(t *testing.T) {
	empty, err := decodePerformanceReport("test", "LATEST", 0, nil, nil)
	if err != nil || empty.Rating != "UNRATED" || empty.Brier != nil {
		t.Fatalf("%+v %v", empty, err)
	}
	if _, err := decodePerformanceReport("test", "LATEST", 1, nil, nil); !errors.Is(err, errProductUnavailable) {
		t.Fatal(err)
	}
	payload := []byte(`{"competition_id":"other","forecasts":1}`)
	sum := sha256.Sum256(payload)
	digest := hex.EncodeToString(sum[:])
	if _, err := decodePerformanceReport("test", "LATEST", 1, payload, &digest); err == nil {
		t.Fatal("wrong identity accepted")
	}
}

func TestUnknownEventSideCannotResolveToAwayTeam(t *testing.T) {
	unknown, home, away := "UNKNOWN", "HOME", "AWAY"
	events := []LiveEvent{{TeamSide: &unknown}, {TeamSide: &home}, {TeamSide: &away}, {}}
	attachEventTeams(events, "home-id", "away-id", "test")
	if events[0].TeamID != nil || events[3].TeamID != nil {
		t.Fatal("unknown identity fabricated")
	}
	if *events[1].TeamID != "home-id" || *events[2].TeamID != "away-id" {
		t.Fatal("canonical side hydration failed")
	}
}

func TestPublicReadReportsDatabase(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	ctx := context.Background()
	competition, fixture := "00000000-0000-0000-0000-000000001fa4", "00000000-0000-0000-0000-000000001fa8"
	verifyPublicPerformance(t, store, competition)
	verifyPublicContext(t, store, fixture)
	verifyPublicComparison(t, store, fixture)
	verifyPublicReportHTTP(t, store)
	if _, err := store.pool.Exec(ctx, `UPDATE football.product_fixtures SET home_score=0,away_score=3 WHERE fixture_id=$1::uuid`, fixture); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Performance(ctx, competition, "LATEST"); !errors.Is(err, errProductUnavailable) {
		t.Fatalf("stale performance served: %v", err)
	}
	if _, err := store.pool.Exec(ctx, `UPDATE football.product_fixtures SET kickoff_at=kickoff_at+interval '1 hour' WHERE fixture_id=$1::uuid`, fixture); err != nil {
		t.Fatal(err)
	}
	if _, err := store.FixtureContext(ctx, fixture); !errors.Is(err, errProductUnavailable) {
		t.Fatalf("stale context served: %v", err)
	}
}

func verifyPublicPerformance(t *testing.T, store *PostgresProductStore, competition string) {
	t.Helper()
	ctx := context.Background()
	item, err := store.Performance(ctx, competition, "LATEST")
	if err != nil || item.Forecasts != 1 || item.Brier == nil {
		t.Fatalf("%+v %v", item, err)
	}
}

func verifyPublicContext(t *testing.T, store *PostgresProductStore, fixture string) {
	t.Helper()
	ctx := context.Background()
	report, err := store.FixtureContext(ctx, fixture)
	if err != nil || report.FixtureID != fixture || len(report.HomeForm) != 0 || len(report.RestContext) != 2 {
		t.Fatalf("%+v %v", report, err)
	}
}

func verifyPublicComparison(t *testing.T, store *PostgresProductStore, fixture string) {
	t.Helper()
	ctx := context.Background()
	predictions, err := store.ExternalPredictions(ctx, ExternalPredictionFilters{FixtureID: fixture})
	if err != nil || len(predictions) != 1 {
		t.Fatalf("%+v %v", predictions, err)
	}
	if predictions[0].Agreement != "AGREES" || predictions[0].MatchForgeProbability == nil || *predictions[0].MatchForgeProbability != .6 {
		t.Fatalf("%+v", predictions[0])
	}
}

func verifyPublicReportHTTP(t *testing.T, store *PostgresProductStore) {
	t.Helper()
	application := New(Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store)
	cases := []struct{ path, schema string }{
		{"/v1/performance", "PerformancePage"},
		{"/v1/fixtures/00000000-0000-4000-8000-000000001fa8/context", "MatchContext"},
		{"/v1/external-predictions", "ExternalPredictionPage"},
	}
	for _, item := range cases {
		response := httptest.NewRecorder()
		application.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, item.path, nil))
		if response.Code != http.StatusOK {
			t.Fatalf("%s: %d %s", item.path, response.Code, response.Body.String())
		}
		fmt.Printf("OPENAPI %s %s", item.schema, response.Body.String())
	}
}
