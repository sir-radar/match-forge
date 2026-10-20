package app

import (
	"context"
	"fmt"
	"io"
	"log/slog"
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

type forecastHistoryStoreStub struct {
	unavailableProductStore
	fixtureID string
}

func (store *forecastHistoryStoreStub) ForecastHistory(
	_ context.Context, fixtureID string,
) ([]ForecastRevision, error) {
	store.fixtureID = fixtureID
	return []ForecastRevision{{ForecastID: "forecast-1", FixtureID: fixtureID}}, nil
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
	if store.filters.Start != time.Date(2026, 9, 30, 0, 0, 0, 0, time.UTC) || store.filters.End != time.Date(2026, 10, 1, 0, 0, 0, 0, time.UTC) || store.filters.Continent != "Africa" || store.filters.ForecastAvailability != "NOT_ENOUGH_HISTORY" {
		t.Fatalf("filters = %+v", store.filters)
	}
	if response.Header().Get("Access-Control-Allow-Origin") != "http://127.0.0.1:3000" {
		t.Fatal("expected exact configured CORS origin")
	}
}

func TestFixtureListAPIAppliesSelectedTimezoneDay(t *testing.T) {
	store := &fixtureStoreStub{}
	application := New(Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store)
	request := httptest.NewRequest(http.MethodGet, "/v1/fixtures?date=2026-09-30&timezone=Africa%2FLagos", nil)
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
	if store.filters.Start != time.Date(2026, 9, 29, 23, 0, 0, 0, time.UTC) || store.filters.End != time.Date(2026, 9, 30, 23, 0, 0, 0, time.UTC) {
		t.Fatalf("filters = %+v", store.filters)
	}
}

type liveStoreStub struct {
	unavailableProductStore
	fixtureID string
}

func (store *liveStoreStub) LiveFixture(_ context.Context, fixtureID string) (LiveMatch, error) {
	store.fixtureID = fixtureID
	zero := 0
	return LiveMatch{FixtureID: fixtureID, Status: "LIVE", HomeScore: &zero, AwayScore: &zero, Events: []LiveEvent{}, Statistics: []LiveStatistic{}, Availability: map[string]bool{"score": true}}, nil
}

func TestLiveFixtureAPIKeepsZeroScore(t *testing.T) {
	store := &liveStoreStub{}
	application := New(Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store)
	request := httptest.NewRequest(http.MethodGet, "/v1/fixtures/ffc284d9-08fe-52b5-bab0-a8fb639daed5/live", nil)
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"home_score":0`) || !strings.Contains(response.Body.String(), `"away_score":0`) {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
}

func TestLiveFixtureAPIRejectsMalformedID(t *testing.T) {
	application := New(Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, &liveStoreStub{})
	request := httptest.NewRequest(http.MethodGet, "/v1/fixtures/not-a-uuid/live", nil)
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
}

func TestForecastHistoryAPI(t *testing.T) {
	store := &forecastHistoryStoreStub{}
	application := New(
		Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, store,
	)
	request := httptest.NewRequest(http.MethodGet, "/v1/fixtures/fixture-1/forecasts", nil)
	response := httptest.NewRecorder()

	application.Handler().ServeHTTP(response, request)

	if response.Code != http.StatusOK || store.fixtureID != "fixture-1" {
		t.Fatalf("response = %d %s, fixture = %s", response.Code, response.Body.String(), store.fixtureID)
	}
	if !strings.Contains(response.Body.String(), `"forecast_id":"forecast-1"`) {
		t.Fatalf("response = %s", response.Body.String())
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
