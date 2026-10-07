package app

import (
	"context"
	"fmt"
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
	items   []Performance
}

func (store *performanceStoreStub) Performances(_ context.Context, filters PerformanceFilters) (PerformancePage, error) {
	store.filters = filters
	return paginatePerformances(store.items, filters.Page, filters.PageSize), nil
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
		"/v1/performance?continent=Europe&country=England&rating=GOOD&minimum_forecasts=50&page=2&page_size=50",
		nil,
	)
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
	if store.filters.Continent != "Europe" || store.filters.Country != "England" ||
		store.filters.Rating != "GOOD" || store.filters.MinimumForecasts != 50 ||
		store.filters.Page != 2 || store.filters.PageSize != 50 {
		t.Fatalf("filters = %+v", store.filters)
	}
}

func TestPerformanceListAPIPaginationDefaultsAndMetadata(t *testing.T) {
	store := &performanceStoreStub{items: make([]Performance, 45)}
	application := New(
		Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store,
	)
	request := httptest.NewRequest(http.MethodGet, "/v1/performance", nil)
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
	if store.filters.Page != 1 || store.filters.PageSize != 20 {
		t.Fatalf("filters = %+v", store.filters)
	}
	want := `"pagination":{"page":1,"page_size":20,"total_items":45,"total_pages":3}`
	if !strings.Contains(response.Body.String(), want) {
		t.Fatalf("response = %s, want %s", response.Body.String(), want)
	}
}

func TestPerformanceListAPIRejectsInvalidPagination(t *testing.T) {
	tests := []string{
		"page=0", "page=not-a-number", "page_size=0", "page_size=25", "page_size=not-a-number",
	}
	for _, query := range tests {
		t.Run(query, func(t *testing.T) {
			application := New(
				Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, &performanceStoreStub{},
			)
			request := httptest.NewRequest(http.MethodGet, "/v1/performance?"+query, nil)
			response := httptest.NewRecorder()
			application.Handler().ServeHTTP(response, request)
			if response.Code != http.StatusBadRequest {
				t.Fatalf("response = %d %s", response.Code, response.Body.String())
			}
		})
	}
}

func TestPerformanceListAPIAcceptsSupportedPageSizes(t *testing.T) {
	for _, pageSize := range []int{20, 50, 100} {
		t.Run(fmt.Sprintf("page_size_%d", pageSize), func(t *testing.T) {
			store := &performanceStoreStub{}
			application := New(
				Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store,
			)
			request := httptest.NewRequest(http.MethodGet, fmt.Sprintf("/v1/performance?page_size=%d", pageSize), nil)
			response := httptest.NewRecorder()
			application.Handler().ServeHTTP(response, request)
			if response.Code != http.StatusOK || store.filters.PageSize != pageSize {
				t.Fatalf("response = %d %s, filters = %+v", response.Code, response.Body.String(), store.filters)
			}
		})
	}
}

func TestPaginatePerformances(t *testing.T) {
	items := make([]Performance, 45)
	for index := range items {
		items[index].CompetitionID = fmt.Sprintf("competition-%02d", index+1)
	}

	last := paginatePerformances(items, 3, 20)
	if len(last.Performance) != 5 || last.Performance[0].CompetitionID != "competition-41" ||
		last.Pagination != (Pagination{Page: 3, PageSize: 20, TotalItems: 45, TotalPages: 3}) {
		t.Fatalf("last page = %+v", last)
	}

	clamped := paginatePerformances(items, 99, 20)
	if clamped.Pagination.Page != 3 || len(clamped.Performance) != 5 {
		t.Fatalf("clamped page = %+v", clamped)
	}

	empty := paginatePerformances([]Performance{}, 7, 50)
	if empty.Pagination != (Pagination{Page: 1, PageSize: 50, TotalItems: 0, TotalPages: 0}) ||
		len(empty.Performance) != 0 {
		t.Fatalf("empty page = %+v", empty)
	}
}

func TestPerformanceFilteringAndOrderingPrecedePagination(t *testing.T) {
	items := []Performance{
		{CompetitionID: "excluded-rating", League: "League 00", Country: "England", Continent: "Europe", Rating: "WATCH", Forecasts: 80},
		{CompetitionID: "excluded-count", League: "League 00", Country: "England", Continent: "Europe", Rating: "GOOD", Forecasts: 49},
	}
	for index := 23; index >= 1; index-- {
		items = append(items, Performance{
			CompetitionID: fmt.Sprintf("competition-%02d", index), League: fmt.Sprintf("League %02d", index),
			Country: "England", Continent: "Europe", Rating: "GOOD", Forecasts: 60,
		})
	}

	result := filterSortAndPaginatePerformances(items, PerformanceFilters{
		Rating: "GOOD", MinimumForecasts: 50, Page: 2, PageSize: 20,
	})
	if result.Pagination.TotalItems != 23 || result.Pagination.TotalPages != 2 || len(result.Performance) != 3 ||
		result.Performance[0].CompetitionID != "competition-21" {
		t.Fatalf("filtered page = %+v", result)
	}
}

func TestSelectionAgreement(t *testing.T) {
	values := map[string]float64{
		"home": 0.55, "draw": 0.25, "away": 0.2, "btts_yes": 0.44,
		"total_over_1_5": 0.72, "total_under_3_5": 0.68,
	}
	tests := []struct {
		market, selection, want string
		probability             float64
	}{
		{market: "RESULT_1X2", selection: "HOME_WIN", want: "AGREES", probability: 0.55},
		{market: "BTTS", selection: "BTTS_YES", want: "WEAK_SUPPORT", probability: 0.44},
		{market: "RESULT_1X2", selection: "AWAY_WIN", want: "DISAGREES", probability: 0.2},
		{market: "TOTAL_GOALS", selection: "TOTAL_OVER_1_5", want: "AGREES", probability: 0.72},
		{market: "TOTAL_GOALS", selection: "TOTAL_UNDER_3_5", want: "AGREES", probability: 0.68},
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
	if probability, agreement := selectionAgreement("RESULT_1X2", "Draw No Bet", values); probability != nil || agreement != "UNABLE_TO_EVALUATE" {
		t.Fatalf("unmapped selection = (%v, %s)", probability, agreement)
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
