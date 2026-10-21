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

func TestMergeFixtureGroupsCombinesJapaneseProviderVariants(t *testing.T) {
	firstDivision := 1
	secondDivision := 2
	groups := []FixtureGroup{
		testFixtureGroup(Competition{ID: "j1", Name: "J1 League", Country: "Japan", Type: "LEAGUE", Season: "2026", Division: &firstDivision}, "j1-fixture"),
		testFixtureGroup(Competition{ID: "j-league", Name: "J. League", Country: "Japan", Type: "UNKNOWN", Season: "Unknown"}, "j1-alias-fixture"),
		testFixtureGroup(Competition{ID: "j-league-2", Name: "J. League 2", Country: "Japan", Type: "LEAGUE", Season: "2026", Division: &secondDivision}, "j2-fixture"),
		testFixtureGroup(Competition{ID: "j2", Name: "J2 League", Country: "Japan", Type: "UNKNOWN", Season: "Unknown"}, "j2-alias-fixture"),
	}

	merged := mergeFixtureGroups(groups, "")
	if len(merged) != 2 {
		t.Fatalf("expected one J1 and one J2 group, got %+v", merged)
	}
	for _, group := range merged {
		if len(group.Fixtures) != 2 {
			t.Errorf("expected both provider fixtures in %q, got %+v", group.Competition.Name, group.Fixtures)
		}
		if group.Competition.Name != "J1 League" && group.Competition.Name != "J2 League" {
			t.Errorf("expected canonical Japanese league name, got %q", group.Competition.Name)
		}
	}
}

func TestMergeFixtureGroupsKeepsKnownCompetitionTypesAndDivisionsDistinct(t *testing.T) {
	firstDivision := 1
	secondDivision := 2
	groups := []FixtureGroup{
		testFixtureGroup(Competition{ID: "league", Name: "Cup", Country: "England", Type: "LEAGUE", Season: "2026"}, "league-fixture"),
		testFixtureGroup(Competition{ID: "cup", Name: "Cup", Country: "England", Type: "CUP", Season: "2026"}, "cup-fixture"),
		testFixtureGroup(Competition{ID: "division-1", Name: "National League", Country: "England", Type: "LEAGUE", Season: "2026", Division: &firstDivision}, "division-1-fixture"),
		testFixtureGroup(Competition{ID: "division-2", Name: "National League", Country: "England", Type: "LEAGUE", Season: "2026", Division: &secondDivision}, "division-2-fixture"),
	}

	merged := mergeFixtureGroups(groups, "")
	if len(merged) != 4 {
		t.Fatalf("different known competition types and divisions must remain separate, got %+v", merged)
	}
}

func TestMergeFixtureGroupsRemovesEmbeddedSeasonAndUnknownSuffixAcrossLeagues(t *testing.T) {
	groups := []FixtureGroup{
		testFixtureGroup(Competition{ID: "we-2026", Name: "WE League 2026", Country: "Japan", Type: "LEAGUE", Season: "Unknown"}, "we-2026-fixture"),
		testFixtureGroup(Competition{ID: "we-unknown", Name: "WE LeagueUnknown", Country: "Japan", Type: "UNKNOWN", Season: "Unknown"}, "we-unknown-fixture"),
		testFixtureGroup(Competition{ID: "league-one", Name: "League-One 2025/26", Country: "England", Type: "LEAGUE", Season: "Unknown"}, "league-one-fixture"),
		testFixtureGroup(Competition{ID: "league-1", Name: "League 1Unknown", Country: "England", Type: "UNKNOWN", Season: "Unknown"}, "league-1-fixture"),
		testFixtureGroup(Competition{ID: "la-liga", Name: "LaLiga 2025-26", Country: "Spain", Type: "LEAGUE", Season: "Unknown"}, "la-liga-fixture"),
		testFixtureGroup(Competition{ID: "la-liga-unknown", Name: "La LigaUnknown", Country: "Spain", Type: "UNKNOWN", Season: "Unknown"}, "la-liga-unknown-fixture"),
	}

	merged := mergeFixtureGroups(groups, "")
	if len(merged) != 3 {
		t.Fatalf("expected WE League, League One, and La Liga groups, got %+v", merged)
	}
	for _, group := range merged {
		if len(group.Fixtures) != 2 {
			t.Errorf("expected both provider fixtures in %q, got %+v", group.Competition.Name, group.Fixtures)
		}
		if knownCompetitionValue(group.Competition.Season) == "" {
			t.Errorf("expected embedded season to fill unknown season for %q", group.Competition.Name)
		}
		if normalizeCompetitionText(group.Competition.Name) == "we league 2026" || normalizeCompetitionText(group.Competition.Name) == "we leagueunknown" {
			t.Errorf("expected season/unknown suffix stripped from display name, got %q", group.Competition.Name)
		}
	}
}

func TestMergeFixtureGroupsKeepsDifferentEmbeddedSeasonsSeparate(t *testing.T) {
	groups := []FixtureGroup{
		testFixtureGroup(Competition{ID: "2025", Name: "Ligue 1 2025", Country: "France", Type: "LEAGUE", Season: "Unknown"}, "2025-fixture"),
		testFixtureGroup(Competition{ID: "2026", Name: "Ligue 1 2026", Country: "France", Type: "LEAGUE", Season: "Unknown"}, "2026-fixture"),
	}

	merged := mergeFixtureGroups(groups, "")
	if len(merged) != 2 {
		t.Fatalf("different embedded seasons must remain separate, got %+v", merged)
	}
	seasons := map[string]bool{}
	for _, group := range merged {
		seasons[group.Competition.Season] = true
	}
	if !seasons["2025"] || !seasons["2026"] {
		t.Fatalf("expected embedded seasons to be retained, got %+v", seasons)
	}
}

func TestCompetitionSeasonKeyNormalizesProviderSeasonRanges(t *testing.T) {
	pairs := [][2]string{
		{"2025/26", "2025/2026"},
		{"2025-26", "2025-2026"},
	}
	for _, pair := range pairs {
		left, right := competitionSeasonKey(pair[0]), competitionSeasonKey(pair[1])
		if left != right {
			t.Errorf("season labels %q and %q should normalize equally, got %q and %q", pair[0], pair[1], left, right)
		}
	}
	if !seasonValuesCompatible(competitionSeasonKey("2026"), competitionSeasonKey("2025/26")) {
		t.Fatal("a single-year label should match a compatible endpoint of a season range")
	}

	merged := mergeFixtureGroups([]FixtureGroup{
		testFixtureGroup(Competition{ID: "range", Name: "LaLiga 2025/26", Country: "Spain", Type: "LEAGUE", Season: "Unknown"}, "range-fixture"),
		testFixtureGroup(Competition{ID: "single", Name: "La Liga 2026", Country: "Spain", Type: "LEAGUE", Season: "Unknown"}, "single-fixture"),
	}, "")
	if len(merged) != 1 || len(merged[0].Fixtures) != 2 {
		t.Fatalf("equivalent single-year and range season labels should merge uniquely, got %+v", merged)
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
