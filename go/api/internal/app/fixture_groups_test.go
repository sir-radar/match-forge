package app

import (
	"testing"
	"time"
)

func TestMergeFixtureGroupsNormalizesProviderCompetitionNames(t *testing.T) {
	unknown := testFixtureGroup(Competition{
		ID: "provisional", Name: "LaLiga", Country: "Spain", Type: "UNKNOWN", Season: "Unknown",
	}, "fixture-provisional")
	canonical := testFixtureGroup(Competition{
		ID: "canonical", Name: "La Liga", Country: "Spain", Type: "LEAGUE", Season: "2026",
	}, "fixture-canonical")

	groups := mergeFixtureGroups([]FixtureGroup{unknown, canonical}, "")
	if len(groups) != 1 {
		t.Fatalf("expected equivalent provider competitions to merge, got %d groups", len(groups))
	}
	if groups[0].Competition.ID != "canonical" || groups[0].Competition.Season != "2026" {
		t.Fatalf("expected the more complete competition metadata, got %+v", groups[0].Competition)
	}
	if len(groups[0].Fixtures) != 2 {
		t.Fatalf("expected both fixture IDs to remain, got %+v", groups[0].Fixtures)
	}

	filtered := mergeFixtureGroups([]FixtureGroup{unknown, canonical}, "provisional")
	if len(filtered) != 1 || len(filtered[0].Fixtures) != 2 {
		t.Fatalf("filtering by a merged competition ID should return its full group, got %+v", filtered)
	}
}

func TestMergeFixtureGroupsAppliesScopedCompetitionAliases(t *testing.T) {
	known := testFixtureGroup(Competition{
		ID: "known", Name: "Division 1", Country: "Saudi-Arabia", Type: "LEAGUE", Season: "2026",
	}, "known-fixture")
	provisional := testFixtureGroup(Competition{
		ID: "provider", Name: "Saudi First Division", Country: "Saudi Arabia", Type: "UNKNOWN", Season: "Unknown",
	}, "provider-fixture")

	groups := mergeFixtureGroups([]FixtureGroup{known, provisional}, "")
	if len(groups) != 1 || len(groups[0].Fixtures) != 2 {
		t.Fatalf("expected Saudi provider naming variants to merge, got %+v", groups)
	}
}

func TestMergeFixtureGroupsKeepsDistinctGeographiesAndKnownSeasons(t *testing.T) {
	groups := []FixtureGroup{
		testFixtureGroup(Competition{ID: "spain", Name: "Premier League", Country: "Spain", Type: "LEAGUE", Season: "2025"}, "spain-fixture"),
		testFixtureGroup(Competition{ID: "england", Name: "Premier League", Country: "England", Type: "LEAGUE", Season: "2025"}, "england-fixture"),
		testFixtureGroup(Competition{ID: "new-season", Name: "Premier League", Country: "Spain", Type: "LEAGUE", Season: "2026"}, "new-season-fixture"),
	}

	merged := mergeFixtureGroups(groups, "")
	if len(merged) != 3 {
		t.Fatalf("different countries or known seasons must remain separate, got %+v", merged)
	}
}

func TestMergeFixtureGroupsLeavesAmbiguousUnknownMetadataSeparate(t *testing.T) {
	groups := []FixtureGroup{
		testFixtureGroup(Competition{ID: "unknown", Name: "League One", Country: "England", Type: "UNKNOWN", Season: "Unknown"}, "unknown-fixture"),
		testFixtureGroup(Competition{ID: "2025", Name: "League One", Country: "England", Type: "LEAGUE", Season: "2025"}, "2025-fixture"),
		testFixtureGroup(Competition{ID: "2026", Name: "League One", Country: "England", Type: "LEAGUE", Season: "2026"}, "2026-fixture"),
	}

	merged := mergeFixtureGroups(groups, "")
	if len(merged) != 3 {
		t.Fatalf("an unknown season with multiple possible matches must stay separate, got %+v", merged)
	}
}

func TestMergeFixtureGroupsDeduplicatesRepeatedFixtureIDs(t *testing.T) {
	first := testFixtureGroup(Competition{ID: "first", Name: "WE League", Country: "Japan", Type: "UNKNOWN", Season: "Unknown"}, "same-fixture")
	second := testFixtureGroup(Competition{ID: "second", Name: "WE-League", Country: "Japan", Type: "UNKNOWN", Season: "Unknown"}, "same-fixture")

	groups := mergeFixtureGroups([]FixtureGroup{first, second}, "")
	if len(groups) != 1 || len(groups[0].Fixtures) != 1 {
		t.Fatalf("expected one competition and one fixture identity, got %+v", groups)
	}
}

func TestCompetitionNameNormalizationHandlesProviderSpelling(t *testing.T) {
	pairs := [][2]string{
		{"LaLiga", "La Liga"},
		{"J. League", "J1 League"},
		{"J League 2", "J2 League"},
		{"Taça de Portugal", "Taca-de-Portugal"},
		{"League-One", "League 1"},
	}
	for _, pair := range pairs {
		if normalizeCompetitionName(pair[0]) != normalizeCompetitionName(pair[1]) {
			t.Errorf("%q and %q should normalize equally", pair[0], pair[1])
		}
	}
	if normalizeCompetitionName("AFC Champions League") == normalizeCompetitionName("CAF Champions League") {
		t.Fatal("competition confederations must remain distinct")
	}
}

func TestCurrentFixtureDateReplacesUnknownSeasonOnlyForToday(t *testing.T) {
	location, err := time.LoadLocation("Africa/Lagos")
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, time.October, 21, 12, 0, 0, 0, time.UTC)
	groups := []FixtureGroup{
		{Competition: Competition{Season: " Unknown "}},
		{Competition: Competition{Season: "2026/2027"}},
	}
	applyCurrentFixtureDate(groups, "2026-10-21", now, location)
	if groups[0].Competition.Season != "2026-10-21" || groups[1].Competition.Season != "2026/2027" {
		t.Fatalf("unexpected current-day season labels: %+v", groups)
	}

	applyCurrentFixtureDate(groups, "2026-10-20", now, location)
	if groups[0].Competition.Season != "2026-10-21" {
		t.Fatalf("historical requests should not change season labels: %+v", groups)
	}
}

func testFixtureGroup(competition Competition, fixtureID string) FixtureGroup {
	return FixtureGroup{
		Competition: competition,
		Fixtures: []Fixture{{
			ID:        fixtureID,
			KickoffAt: time.Date(2026, time.October, 21, 12, 0, 0, 0, time.UTC),
		}},
	}
}
