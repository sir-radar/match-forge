package app

import (
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAnalyticsHorizonAndUUIDValidation(t *testing.T) {
	for _, query := range []string{"horizon=CONFIRMED_LINEUP", "horizon=EARLY_GT_7D", "competition=invalid"} {
		application := New(Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, &performanceStoreStub{})
		response := httptest.NewRecorder()
		application.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/v1/performance?"+query, nil))
		if response.Code != 400 {
			t.Fatalf("%s: %d", query, response.Code)
		}
	}
	for label, want := range map[string]int{"": 0, "LATEST": 0, "7D": 604800, "3D": 259200, "24H": 86400, "6H": 21600, "1H": 3600, "15M": 900} {
		got, err := performanceHorizonSeconds(label)
		if got != want || err != nil {
			t.Fatalf("%s %d %v", label, got, err)
		}
	}
}

func TestPerformanceOrderHasStableIdentityTieBreak(t *testing.T) {
	if !performanceLess(Performance{CompetitionID: "a"}, Performance{CompetitionID: "b"}) {
		t.Fatal("metadata tie has no identity order")
	}
}
