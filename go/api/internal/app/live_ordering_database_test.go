package app

import (
	"context"
	"fmt"
	"testing"
	"time"
)

func TestLiveMatchClockOrderingAndConflictsDatabase(t *testing.T) {
	pool := servingDatabasePool(t)
	ctx := context.Background()
	competition, home, away, season := seedServingFixtureIdentities(t, pool, "Live ordering")
	kickoff := time.Date(2032, 1, 10, 12, 0, 0, 0, time.UTC)
	fixture := seedFixtureForSeason(t, pool, competition, home, away, season, kickoff)
	_, snapshot := seedFixtureRepairSource(t, pool)
	mustExec(t, pool, `UPDATE football.product_fixtures SET status='LIVE',home_score=1,away_score=0 WHERE fixture_id=$1`, fixture)
	insert := func(key string, minute, score int, observed time.Time) {
		t.Helper()
		mustExec(t, pool, `INSERT INTO football.product_provider_fixture_observations(
            semantic_sha256,provider_code,provider_match_id,provider_competition_id,canonical_fixture_id,
            source_snapshot_id,kickoff_at,canonical_status,home_score,away_score,match_minute,
            observed_at,last_fetched_at,stale_after)
            VALUES(encode(sha256(convert_to($1,'UTF8')),'hex'),'fotmob',$2::text,'league',$2::uuid,$3,$4,'LIVE',$5,0,$6,$7::timestamptz,$7::timestamptz,$7::timestamptz+interval '3 minutes')`,
			fmt.Sprintf("%s-%s", fixture, key), fixture, snapshot, kickoff, score, minute, observed)
	}
	insert("canonical", 20, 1, kickoff.Add(20*time.Minute))
	// Later HTTP data must not replace a more advanced football clock, even for the same score.
	insert("late-cache", 10, 1, kickoff.Add(22*time.Minute))
	insert("old-disagreement", 19, 0, kickoff.Add(23*time.Minute))
	store := NewPostgresProductStore(pool)
	assertLiveClock(t, store, fixture, 20, 1, false)
	groups, err := store.Fixtures(ctx, FixtureFilters{Start: kickoff.Add(-time.Hour), End: kickoff.Add(time.Hour), CompetitionID: competition})
	if err != nil || len(groups) != 1 || len(groups[0].Fixtures) != 1 || *groups[0].Fixtures[0].MatchMinute != 20 {
		t.Fatalf("list/detail drift: %+v %v", groups, err)
	}
	insert("unresolved", 20, 0, kickoff.Add(24*time.Minute))
	assertLiveClock(t, store, fixture, 20, 1, true)
	insert("progress", 21, 2, kickoff.Add(25*time.Minute))
	mustExec(t, pool, `UPDATE football.product_fixtures SET home_score=2 WHERE fixture_id=$1`, fixture)
	assertLiveClock(t, store, fixture, 21, 2, false)
	mustExec(t, pool, `UPDATE football.product_provider_fixture_observations
        SET match_minute=NULL WHERE canonical_fixture_id=$1 AND home_score=0 AND match_minute=20`, fixture)
	assertLiveClock(t, store, fixture, 21, 2, true)
}

func assertLiveClock(t *testing.T, store *PostgresProductStore, fixture string, minute, score int, conflict bool) {
	t.Helper()
	live, err := store.LiveFixture(context.Background(), fixture)
	if err != nil {
		t.Fatal(err)
	}
	if live.MatchMinute == nil || live.HomeScore == nil || live.ScoreSource == nil {
		t.Fatalf("missing live data: %+v", live)
	}
	if *live.MatchMinute != minute || *live.HomeScore != score || live.ScoreConflict != conflict {
		t.Fatalf("unexpected live state: %+v", live)
	}
	if conflict && !live.Partial {
		t.Fatal("conflict must mark partial coverage")
	}
}

func TestLiveScoreSourceFootballEvidence(t *testing.T) {
	provider, match := "fotmob", "native"
	known := time.Date(2032, 1, 1, 12, 0, 0, 0, time.UTC)
	before, future := known.Add(-time.Minute), known.Add(time.Minute)
	minute := 20
	for _, scenario := range []struct {
		name    string
		minute  *int
		updated *time.Time
		want    string
	}{
		{"unknown", nil, nil, "UNKNOWN"},
		{"global clock", &minute, nil, "MATCH_CLOCK"},
		{"native update", nil, &before, "PROVIDER_TIMESTAMP"},
		{"future claim", nil, &future, "UNKNOWN"},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			source := liveScoreSource(&provider, &match, &known, &known, nil, scenario.updated, scenario.minute)
			if source.OrderingBasis != scenario.want {
				t.Fatalf("%+v", source)
			}
		})
	}
	if liveScoreSource(nil, &match, &known, &known, nil, nil, nil) != nil {
		t.Fatal("missing provider fabricated provenance")
	}
}
