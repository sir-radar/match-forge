package app

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func TestServingDatabaseFixtureRepresentatives(t *testing.T) {
	pool := servingDatabasePool(t)
	ctx := context.Background()
	for _, scenario := range []struct{ name, date string }{
		{"Europa League", "2026-10-15"},
		{"Conference League", "2026-10-15"},
		{"Botola Pro", "2026-10-14"},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			competition, home, away, season := seedServingFixtureIdentities(t, pool, scenario.name)
			start, ids := seedServingFixtureRepresentatives(t, pool, competition, home, away, season, scenario.date)
			store := NewPostgresProductStore(pool)
			filters := FixtureFilters{Start: start, End: start.Add(24 * time.Hour), CompetitionID: competition}
			for range 2 {
				assertServingRepresentatives(t, store, filters, ids[1:4])
			}
			// Live updates never make an old immutable reference a list representative again.
			_, err := pool.Exec(ctx, `UPDATE football.product_fixtures SET status='LIVE' WHERE fixture_id=$1`, ids[0])
			if err != nil {
				t.Fatal(err)
			}
			assertServingRepresentatives(t, store, filters, ids[1:4])
			if _, err := store.LiveFixture(ctx, ids[0]); err != nil {
				t.Fatalf("historical detail lost: %v", err)
			}
		})
	}
}

func seedServingFixtureIdentities(t *testing.T, pool *pgxpool.Pool, name string) (string, string, string, string) {
	t.Helper()
	ctx := context.Background()
	var competition, home, away, season string
	err := pool.QueryRow(ctx, `WITH c AS (INSERT INTO football.competitions DEFAULT VALUES RETURNING id),
		h AS (INSERT INTO football.teams DEFAULT VALUES RETURNING id),
		a AS (INSERT INTO football.teams DEFAULT VALUES RETURNING id),
		s AS (INSERT INTO football.seasons(competition_id) SELECT id FROM c RETURNING id)
		SELECT c.id::text,h.id::text,a.id::text,s.id::text FROM c,h,a,s`).Scan(&competition, &home, &away, &season)
	if err != nil {
		t.Fatal(err)
	}
	_, err = pool.Exec(ctx, `INSERT INTO football.product_competitions(
		competition_id,name,country,continent,competition_type,season_label,
		availability_status,source_roles,updated_at,geographic_scope)
		VALUES($1,$2,'Test','Test','CUP','2026','SOURCE_DATA_INCOMPLETE','{}',now(),'Test')`, competition, name)
	if err != nil {
		t.Fatal(err)
	}
	for _, team := range []string{home, away} {
		_, err = pool.Exec(ctx, `INSERT INTO football.product_teams(team_id,name,updated_at) VALUES($1,'Club',now())`, team)
		if err != nil {
			t.Fatal(err)
		}
	}
	return competition, home, away, season
}

func seedServingFixtureRepresentatives(t *testing.T, pool *pgxpool.Pool, competition, home, away, season, date string) (time.Time, []string) {
	t.Helper()
	ctx := context.Background()
	day, err := time.Parse("2006-01-02", date)
	if err != nil {
		t.Fatal(err)
	}
	start := day.Add(-time.Hour) // Africa/Lagos midnight.
	ids := make([]string, 5)
	for index := range ids {
		err = pool.QueryRow(ctx, `INSERT INTO football.matches(competition_id,season_id) VALUES($1,$2) RETURNING id::text`, competition, season).Scan(&ids[index])
		if err != nil {
			t.Fatal(err)
		}
		_, err = pool.Exec(ctx, `INSERT INTO football.product_fixtures(
			fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,forecast_availability,updated_at)
			VALUES($1,$2,$3,$4,$5,'SCHEDULED','SOURCE_DATA_INCOMPLETE',now())`, ids[index], competition, home, away, start.Add([]time.Duration{0, 0, 12 * time.Hour, 23 * time.Hour, 24 * time.Hour}[index]))
		if err != nil {
			t.Fatal(err)
		}
	}
	// Version-independent, authoritative equivalence; the other same-club fixtures stay visible.
	_, err = pool.Exec(ctx, `INSERT INTO football.fixture_identity_resolutions(
		canonical_real_fixture_id,member_fixture_id,representative_fixture_id,resolution_status,
		resolution_reason,evidence_json,evidence_sha256,resolution_version,created_at)
		VALUES($1,$2,$1,'DUPLICATE_RESOLVED','Reviewed native fixture IDs','{}',repeat('a',64),'operator-review:test',now())`, ids[1], ids[0])
	if err != nil {
		t.Fatal(err)
	}
	return start, ids
}

func assertServingRepresentatives(t *testing.T, store *PostgresProductStore, filters FixtureFilters, ids []string) {
	t.Helper()
	groups, err := store.Fixtures(context.Background(), filters)
	if err != nil {
		t.Fatal(err)
	}
	if len(groups) != 1 || len(groups[0].Fixtures) != len(ids) {
		t.Fatalf("expected one group with %d representatives, got %+v", len(ids), groups)
	}
	for index, fixture := range groups[0].Fixtures {
		if fixture.ID != ids[index] {
			t.Fatalf("unstable representative ordering: %s", fixture.ID)
		}
	}
}

func TestServingDatabaseRequiresFixtureServingView(t *testing.T) {
	pool := servingDatabasePool(t)
	ctx := context.Background()
	if _, err := pool.Exec(ctx, `ALTER VIEW football.product_serving_fixtures RENAME TO unavailable_fixture_serving`); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if _, err := pool.Exec(ctx, `ALTER VIEW football.unavailable_fixture_serving RENAME TO product_serving_fixtures`); err != nil {
			t.Fatal(err)
		}
	})
	redis := protocolListener(t, "+PONG\r\n")
	readiness := NewDependencyReadiness(Config{RedisAddress: redis, DependencyTimeout: time.Second}, pool)
	if readiness.Ready(ctx) == nil {
		t.Fatal("missing fixture-serving view accepted as ready")
	}
}
