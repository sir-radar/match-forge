package app

import (
	"io"
	"log/slog"
	"math"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPerformanceBaselineKnowledgeAndSameKickoff(t *testing.T) {
	kickoff := time.Date(2026, 10, 13, 12, 0, 0, 0, time.UTC)
	known := kickoff.Add(2 * time.Hour)
	records := []performanceRecord{
		{kickoff: kickoff, knowledgeCutoff: kickoff.Add(-time.Minute), outcomeKnownAt: &known, homeScore: 1},
		{kickoff: kickoff, knowledgeCutoff: kickoff.Add(-time.Minute), outcomeKnownAt: &known, awayScore: 1},
		{kickoff: kickoff.Add(24 * time.Hour), knowledgeCutoff: known, homeScore: 1},
		{kickoff: kickoff.Add(48 * time.Hour), knowledgeCutoff: kickoff.Add(-time.Hour), homeScore: 1},
	}
	baselines := performanceBaselines(records)
	for _, index := range []int{0, 1, 3} {
		if math.Abs(baselines[index]["home"]-1.0/3) > 1e-12 {
			t.Fatalf("future or same kickoff outcome entered baseline %d: %v", index, baselines[index])
		}
	}
	if baselines[2]["home"] != .4 || baselines[2]["draw"] != .2 || baselines[2]["away"] != .4 {
		t.Fatalf("boundary known outcomes missing: %v", baselines[2])
	}
}

func TestPerformanceBucketsPreserveCategoryMeaning(t *testing.T) {
	cells := []scoreCell{{HomeGoals: 5, AwayGoals: 0, Probability: .8}, {HomeGoals: 1, AwayGoals: 0, Probability: .2}}
	if err := qualifyScoreBuckets(cells, "legacy-compact-index-v1", "transferable-rolling-goals-poisson-v1"); err != nil {
		t.Fatal(err)
	}
	for _, home := range []int{5, 6, 9} {
		var result performanceMetrics
		accumulateScoreMetrics(&result, performanceRecord{scores: cells, homeScore: home})
		if result.exact != 0 || result.topThree != 1 || result.topFive != 1 {
			t.Fatalf("5+ treated as exact or lost category: %+v", result)
		}
	}
	cells[0].HomeKind = "EXACT"
	cells[0].HomeLabel = "5"
	if err := qualifyScoreBuckets(cells, "compact-buckets-v2", ""); err != nil {
		t.Fatal(err)
	}
	var result performanceMetrics
	accumulateScoreMetrics(&result, performanceRecord{scores: cells, homeScore: 5})
	if result.exact != 1 {
		t.Fatal("exact category did not count")
	}
	cells[0].HomeLabel = "5+"
	if qualifyScoreBuckets(cells, "compact-buckets-v2", "") == nil {
		t.Fatal("contradictory category accepted")
	}
	if qualifyScoreBuckets(cells, "legacy-compact-index-v1", "unknown") == nil {
		t.Fatal("unknown legacy interpretation accepted")
	}
}

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

func TestPerformanceRejectsInvalidStoredProbabilities(t *testing.T) {
	valid := map[string]float64{"home": .6, "draw": .2, "away": .2, "total_over_2_5": .5, "btts_yes": .5}
	if err := qualifyPerformanceProbabilities(valid); err != nil {
		t.Fatal(err)
	}
	valid["home"] = .7
	if qualifyPerformanceProbabilities(valid) == nil {
		t.Fatal("invalid probability sum accepted")
	}
	delete(valid, "draw")
	if qualifyPerformanceProbabilities(valid) == nil {
		t.Fatal("missing outcome accepted")
	}
}
