package app

import (
	"context"
	"io"
	"log/slog"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type fixtureStoreStub struct {
	unavailableProductStore
	filters FixtureFilters
}

type performanceStoreStub struct {
	unavailableProductStore
	filters PerformanceFilters
}

func (store *performanceStoreStub) Performances(_ context.Context, filters PerformanceFilters) ([]Performance, error) {
	store.filters = filters
	return []Performance{}, nil
}

func (store *fixtureStoreStub) Fixtures(_ context.Context, filters FixtureFilters) ([]FixtureGroup, error) {
	store.filters = filters
	return []FixtureGroup{}, nil
}

func TestFixtureListAPI(t *testing.T) {
	store := &fixtureStoreStub{}
	application := New(
		Config{AllowedOrigin: "http://127.0.0.1:3000"},
		slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store,
	)
	request := httptest.NewRequest(http.MethodGet, "/v1/fixtures?date=2026-09-30&continent=Africa&forecast_availability=NOT_ENOUGH_HISTORY", nil)
	request.Header.Set("Origin", "http://127.0.0.1:3000")
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"groups":[]`) {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
	if store.filters.Date != time.Date(2026, 9, 30, 0, 0, 0, 0, time.UTC) || store.filters.Continent != "Africa" || store.filters.ForecastAvailability != "NOT_ENOUGH_HISTORY" {
		t.Fatalf("filters = %+v", store.filters)
	}
	if response.Header().Get("Access-Control-Allow-Origin") != "http://127.0.0.1:3000" {
		t.Fatal("expected exact configured CORS origin")
	}
}

func TestCalculatePerformanceRatings(t *testing.T) {
	strong := make([]performanceRecord, 100)
	for index := range strong {
		outcomes := []struct {
			home, away int
			key        string
		}{{2, 1, "home"}, {1, 1, "draw"}, {1, 2, "away"}}
		outcome := outcomes[index%len(outcomes)]
		probabilities := map[string]float64{
			"home": 0.1, "draw": 0.1, "away": 0.1,
			"total_over_2_5": 0.7, "btts_yes": 0.7,
		}
		probabilities[outcome.key] = 0.8
		strong[index] = performanceRecord{
			probabilities: probabilities,
			scores:        []scoreCell{{HomeGoals: outcome.home, AwayGoals: outcome.away, Probability: 0.2}},
			homeScore:     outcome.home, awayScore: outcome.away,
		}
	}
	tests := []struct {
		name    string
		records []performanceRecord
		want    string
	}{
		{name: "unrated before fifty", records: strong[:49], want: "UNRATED"},
		{name: "good after fifty", records: strong[:50], want: "GOOD"},
		{name: "strong after one hundred and recent advantage", records: strong, want: "STRONG"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result := calculatePerformance("competition", test.records)
			if result.Rating != test.want {
				t.Fatalf("rating = %s, want %s", result.Rating, test.want)
			}
			if result.Brier == nil || result.BaselineBrier == nil || *result.Brier >= *result.BaselineBrier {
				t.Fatalf("model Brier %v must beat baseline %v", result.Brier, result.BaselineBrier)
			}
		})
	}
}

func TestPerformanceListAPIParsesBrowseFilters(t *testing.T) {
	store := &performanceStoreStub{}
	application := New(
		Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store,
	)
	request := httptest.NewRequest(
		http.MethodGet,
		"/v1/performance?continent=Europe&country=England&rating=GOOD&minimum_forecasts=50",
		nil,
	)
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
	if store.filters.Continent != "Europe" || store.filters.Country != "England" ||
		store.filters.Rating != "GOOD" || store.filters.MinimumForecasts != 50 {
		t.Fatalf("filters = %+v", store.filters)
	}
}

func TestSelectionAgreement(t *testing.T) {
	values := map[string]float64{"home": 0.55, "draw": 0.25, "away": 0.2, "btts_yes": 0.44}
	tests := []struct {
		market, selection, want string
		probability             float64
	}{
		{market: "RESULT_1X2", selection: "HOME_WIN", want: "AGREES", probability: 0.55},
		{market: "BTTS", selection: "BTTS_YES", want: "WEAK_SUPPORT", probability: 0.44},
		{market: "RESULT_1X2", selection: "AWAY_WIN", want: "DISAGREES", probability: 0.2},
	}
	for _, test := range tests {
		probability, agreement := selectionAgreement(test.market, test.selection, values)
		if agreement != test.want || probability == nil || math.Abs(*probability-test.probability) > 1e-12 {
			t.Fatalf("%s = (%v, %s), want (%f, %s)", test.selection, probability, agreement, test.probability, test.want)
		}
	}
	if probability, agreement := selectionAgreement("UNKNOWN", "UNKNOWN", values); probability != nil || agreement != "UNABLE_TO_EVALUATE" {
		t.Fatalf("unsupported selection = (%v, %s)", probability, agreement)
	}
}

func TestContextSummariesUseOnlyStoredMatches(t *testing.T) {
	form := []FormMatch{
		{GoalsFor: 2, GoalsAgainst: 1},
		{GoalsFor: 1, GoalsAgainst: 1},
	}
	stats := summarizeForm(form)
	if stats == nil || stats.RecentMatches != 2 || stats.GoalsFor != 3 || stats.AverageGoalsFor != 1.5 {
		t.Fatalf("team statistics = %+v", stats)
	}
	h2h := summarizeH2H([]H2HMatch{
		{HomeGoals: 2, AwayGoals: 0},
		{HomeGoals: 1, AwayGoals: 1},
	})
	if h2h.Meetings != 2 || h2h.HomeWins != 1 || h2h.Draws != 1 || h2h.HomeGoals != 3 {
		t.Fatalf("h2h summary = %+v", h2h)
	}
}
