package app

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
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

func TestAttachComparisonWithoutCurrentReportKeepsPredictionAvailable(t *testing.T) {
	forecastID := "forecast-id"
	digest := "report-digest"
	payload := []byte(`{"prediction_id":"prediction-id"}`)
	for _, test := range []struct {
		name    string
		payload []byte
		digest  *string
	}{
		{name: "missing payload", digest: &digest},
		{name: "missing digest", payload: payload},
	} {
		t.Run(test.name, func(t *testing.T) {
			item := ExternalPrediction{ID: "prediction-id"}
			if err := attachComparison(&item, &forecastID, test.payload, test.digest); err != nil {
				t.Fatalf("attachComparison() error = %v", err)
			}
			if item.Agreement != "UNABLE_TO_EVALUATE" || item.MatchForgeProbability != nil {
				t.Fatalf("missing comparison report changed result: %+v", item)
			}
		})
	}
}

func TestPerformanceReportIdentityAndVerifiedEmptyState(t *testing.T) {
	empty, err := decodePerformanceReport("test", "LATEST", 0, nil, nil)
	if err != nil || empty.Rating != "UNRATED" || empty.Brier != nil {
		t.Fatalf("%+v %v", empty, err)
	}
	if item, err := decodePerformanceReport("test", "LATEST", 1, nil, nil); err != nil || item.ReportStatus != "PENDING" || item.Forecasts != 1 || item.Brier != nil {
		t.Fatalf("missing report is not pending: %+v %v", item, err)
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

func TestLiveSourceFreshnessRetainsUnknownDeadline(t *testing.T) {
	provider, match := "test", "fixture"
	now := time.Now()
	fresh, stale := false, true
	for _, test := range []struct {
		stale *bool
		want  string
	}{{nil, "UNKNOWN"}, {&fresh, "FRESH"}, {&stale, "STALE"}} {
		source := liveSource(&provider, &match, &now, &now, test.stale)
		if source.Freshness != test.want {
			t.Fatalf("freshness = %q, want %q", source.Freshness, test.want)
		}
	}
}

func TestScheduledPublicReportsDatabase(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	root, err := filepath.Abs("../../../..")
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("DATABASE_URL", os.Getenv("TEST_DATABASE_URL"))
	t.Setenv("PYTHONPATH", filepath.Join(root, "python", "football", "src"))
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	runner := NewCommandSyncRunner(ctx, store.pool, root, logger)
	defer runner.Shutdown(context.Background())
	application := NewWithSyncRunner(Config{}, logger, readinessStub{}, store, runner)
	go application.runPublicReportSchedule(ctx)
	run := waitScheduledPublicReport(t, ctx, runner)
	if run.Status != "SUCCEEDED" {
		detail, err := json.Marshal(run)
		if err != nil {
			t.Fatal(err)
		}
		t.Fatalf("scheduled worker failed: %s", detail)
	}
	verifyPublicPerformance(t, store, "00000000-0000-0000-0000-000000001fa4")
	verifyPublicContext(t, store, "00000000-0000-0000-0000-000000001fa8")
	verifyPublicComparison(t, store, "00000000-0000-0000-0000-000000001fa8")
}

func waitScheduledPublicReport(t *testing.T, ctx context.Context, runner *CommandSyncRunner) SyncRun {
	t.Helper()
	ticker := time.NewTicker(50 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			t.Fatal("scheduled public report worker did not complete")
		case <-ticker.C:
			runs, err := runner.List(ctx)
			if err != nil {
				t.Fatal(err)
			}
			for _, run := range runs {
				if run.Type != SyncPublicReports {
					continue
				}
				if run.Status == "SUCCEEDED" || run.Status == "FAILED" || run.Status == "CANCELLED" {
					return run
				}
			}
		}
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
	if err != nil || len(predictions.Predictions) != 1 {
		t.Fatalf("%+v %v", predictions, err)
	}
	if predictions.Predictions[0].Agreement != "AGREES" || predictions.Predictions[0].MatchForgeProbability == nil || *predictions.Predictions[0].MatchForgeProbability != .6 {
		t.Fatalf("%+v", predictions.Predictions[0])
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

func TestConflictingLiveResourceDatabase(t *testing.T) {
	id := os.Getenv("TEST_CONFLICT_FIXTURE_ID")
	if id == "" {
		t.Skip("requires disposable conflicting resource fixture")
	}
	store, _ := performanceDatabaseStore(t)
	live, err := store.LiveFixture(context.Background(), id)
	if err != nil {
		t.Fatal(err)
	}
	if !live.ResourceIdentityConflict || !live.Partial || len(live.Events) != 0 || live.EventSource != nil {
		t.Fatalf("conflicting resources presented as verified: %+v", live)
	}
}

func TestPrematchFixtureEligibilityDatabase(t *testing.T) {
	store, _ := performanceDatabaseStore(t)
	groups, err := store.Fixtures(context.Background(), FixtureFilters{
		Start: time.Date(2029, 12, 31, 0, 0, 0, 0, time.UTC), End: time.Date(2030, 1, 2, 0, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(groups) != 1 || len(groups[0].Fixtures) != 1 {
		t.Fatalf("unexpected fixture groups: %+v", groups)
	}
	forecast := groups[0].Fixtures[0].Forecast
	expected := os.Getenv("TEST_EXPECTED_FORECAST_ID")
	if expected == "" {
		if forecast != nil || groups[0].Fixtures[0].ForecastAvailability != "SOURCE_DATA_INCOMPLETE" {
			t.Fatalf("ineligible forecast availability is misleading: %+v", groups[0].Fixtures[0])
		}
		return
	}
	if forecast == nil || forecast.ID != expected {
		t.Fatalf("ineligible active forecast selected: %+v expected=%s", forecast, expected)
	}
}
