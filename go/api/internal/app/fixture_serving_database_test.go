package app

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
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

func TestServingDatabaseFixtureHTTPFiltersUnknownSeasons(t *testing.T) {
	pool := servingDatabasePool(t)
	date := "2026-10-21"
	kickoff, err := time.Parse(time.RFC3339, date+"T12:00:00Z")
	if err != nil {
		t.Fatal(err)
	}
	knownCompetition, knownHome, knownAway, knownSeason := seedServingFixtureIdentities(t, pool, "Known season")
	unknownCompetition, unknownHome, unknownAway, unknownSeason := seedServingFixtureIdentities(t, pool, "Unknown season")
	for _, competition := range []string{knownCompetition, unknownCompetition} {
		setServingCompetitionGeography(t, pool, competition)
	}
	setServingCompetitionUnknownSeason(t, pool, unknownCompetition)
	knownFixture := seedFixtureForSeason(t, pool, knownCompetition, knownHome, knownAway, knownSeason, kickoff)
	seedFixtureForSeason(t, pool, unknownCompetition, unknownHome, unknownAway, unknownSeason, kickoff)
	application := New(Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, NewPostgresProductStore(pool))

	assertFixtureHTTPFiltersUnknownSeason(t, application.Handler(), date, knownCompetition, knownFixture)
	assertCompetitionHTTPFiltersUnknownSeason(t, application.Handler(), knownCompetition)
}

func TestUnknownSeasonFixtureRepairRequiresUniqueExactProviderIdentity(t *testing.T) {
	pool := servingDatabasePool(t)
	providerID, snapshotID := seedFixtureRepairSource(t, pool)
	knownCompetition, home, away, knownSeason := seedServingFixtureIdentities(t, pool, "Known repair season")
	unknownCompetition, _, _, unknownSeason := seedServingFixtureIdentities(t, pool, "Unknown repair season")
	setServingCompetitionUnknownSeason(t, pool, unknownCompetition)
	mustExec(t, pool, `UPDATE football.product_competitions SET metadata_status='PROVISIONAL'
		WHERE competition_id=$1`, unknownCompetition)
	kickoff := time.Date(2031, time.January, 10, 12, 0, 0, 0, time.UTC)
	knownFixture := seedFixtureForSeason(t, pool, knownCompetition, home, away, knownSeason, kickoff)
	unknownFixture := seedFixtureForSeason(t, pool, unknownCompetition, home, away, unknownSeason, kickoff)
	mustExec(t, pool, `UPDATE football.product_fixtures SET identity_status='PROVISIONAL'
		WHERE fixture_id=$1`, unknownFixture)
	uniqueMatchID := "repair-unique-" + snapshotID
	seedFixtureRepairMapping(t, pool, providerID, snapshotID, uniqueMatchID, unknownFixture)
	seedFixtureRepairObservation(t, pool, snapshotID, uniqueMatchID+"-member", uniqueMatchID, "league-unknown", unknownFixture, kickoff)
	seedFixtureRepairObservation(t, pool, snapshotID, uniqueMatchID+"-target", uniqueMatchID, "league-known", knownFixture, kickoff)
	unknownServingRows := queryInt(t, pool, `SELECT count(*) FROM football.product_serving_fixtures WHERE fixture_id=$1`, unknownFixture)
	if unknownServingRows != 1 {
		t.Fatalf("test fixture did not enter the serving read model before repair: %d", unknownServingRows)
	}

	ambiguousCompetition, _, _, ambiguousSeason := seedServingFixtureIdentities(t, pool, "Unknown ambiguous season")
	setServingCompetitionUnknownSeason(t, pool, ambiguousCompetition)
	mustExec(t, pool, `UPDATE football.product_competitions SET metadata_status='PROVISIONAL'
		WHERE competition_id=$1`, ambiguousCompetition)
	ambiguousKickoff := kickoff.Add(time.Hour)
	ambiguousMember := seedFixtureForSeason(t, pool, ambiguousCompetition, home, away, ambiguousSeason, ambiguousKickoff)
	mustExec(t, pool, `UPDATE football.product_fixtures SET identity_status='PROVISIONAL'
		WHERE fixture_id=$1`, ambiguousMember)
	knownCompetitionTwo, _, _, knownSeasonTwo := seedServingFixtureIdentities(t, pool, "Known repair season two")
	knownCompetitionThree, _, _, knownSeasonThree := seedServingFixtureIdentities(t, pool, "Known repair season three")
	knownFixtureTwo := seedFixtureForSeason(t, pool, knownCompetitionTwo, home, away, knownSeasonTwo, ambiguousKickoff)
	knownFixtureThree := seedFixtureForSeason(t, pool, knownCompetitionThree, home, away, knownSeasonThree, ambiguousKickoff)
	ambiguousMatchID := "repair-ambiguous-" + snapshotID
	seedFixtureRepairMapping(t, pool, providerID, snapshotID, ambiguousMatchID, ambiguousMember)
	seedFixtureRepairObservation(t, pool, snapshotID, ambiguousMatchID+"-member", ambiguousMatchID, "league-unknown", ambiguousMember, ambiguousKickoff)
	seedFixtureRepairObservation(t, pool, snapshotID, ambiguousMatchID+"-target-one", ambiguousMatchID, "league-known-one", knownFixtureTwo, ambiguousKickoff)
	seedFixtureRepairObservation(t, pool, snapshotID, ambiguousMatchID+"-target-two", ambiguousMatchID, "league-known-two", knownFixtureThree, ambiguousKickoff)

	repaired := queryInt(t, pool, `SELECT football.reconcile_unknown_season_fixtures()`)
	if repaired != 1 {
		t.Fatalf("expected one exact unique fixture repair, got %d", repaired)
	}
	representative := queryString(t, pool, `SELECT representative_fixture_id::text
		FROM football.fixture_identity_resolutions
		WHERE member_fixture_id=$1 AND active AND resolution_version='UnknownSeasonProviderFixtureV1'`,
		unknownFixture)
	if representative != knownFixture {
		t.Fatalf("unknown-season fixture resolved to %s, want %s", representative, knownFixture)
	}
	unknownServingRows = queryInt(t, pool, `SELECT count(*) FROM football.product_serving_fixtures WHERE fixture_id=$1`, unknownFixture)
	if unknownServingRows != 0 {
		t.Fatalf("repaired unknown-season duplicate remains in serving read model: %d", unknownServingRows)
	}
	ambiguousResolutions := queryInt(t, pool, `SELECT count(*) FROM football.fixture_identity_resolutions
		WHERE member_fixture_id=$1 AND active AND resolution_version='UnknownSeasonProviderFixtureV1'`,
		ambiguousMember)
	if ambiguousResolutions != 0 {
		t.Fatalf("ambiguous unknown-season fixture was resolved %d times", ambiguousResolutions)
	}
	repaired = queryInt(t, pool, `SELECT football.reconcile_unknown_season_fixtures()`)
	if repaired != 0 {
		t.Fatalf("repair was not idempotent: second call repaired %d fixtures", repaired)
	}
}

func mustExec(t *testing.T, pool *pgxpool.Pool, query string, args ...any) {
	t.Helper()
	if _, err := pool.Exec(context.Background(), query, args...); err != nil {
		t.Fatal(err)
	}
}

func queryInt(t *testing.T, pool *pgxpool.Pool, query string, args ...any) int {
	t.Helper()
	var value int
	if err := pool.QueryRow(context.Background(), query, args...).Scan(&value); err != nil {
		t.Fatal(err)
	}
	return value
}

func queryString(t *testing.T, pool *pgxpool.Pool, query string, args ...any) string {
	t.Helper()
	var value string
	if err := pool.QueryRow(context.Background(), query, args...).Scan(&value); err != nil {
		t.Fatal(err)
	}
	return value
}

func seedFixtureRepairSource(t *testing.T, pool *pgxpool.Pool) (string, string) {
	t.Helper()
	ctx := context.Background()
	var providerID, snapshotID string
	if err := pool.QueryRow(ctx, `INSERT INTO football.providers(code,name,source_type)
		VALUES('fixture_repair_test','Fixture repair test','manual')
		ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name RETURNING id::text`).Scan(&providerID); err != nil {
		t.Fatal(err)
	}
	identity := fmt.Sprintf("unknown-season-repair-%d", time.Now().UnixNano())
	if err := pool.QueryRow(ctx, `INSERT INTO football.source_snapshots(
		provider_id,source_identity,source_revision,acquired_at,manifest_path,manifest_sha256,status)
		VALUES($1,$2,'1',now(),$3,repeat('a',64),'validated') RETURNING id::text`,
		providerID, identity, "fixture-repair/"+identity+".json").Scan(&snapshotID); err != nil {
		t.Fatal(err)
	}
	return providerID, snapshotID
}

func seedFixtureRepairMapping(t *testing.T, pool *pgxpool.Pool, providerID, snapshotID, providerMatchID, fixtureID string) {
	t.Helper()
	_, err := pool.Exec(context.Background(), `INSERT INTO football.match_provider_mappings(
		match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,mapping_method,
		mapping_confidence,source_snapshot_id)
		VALUES($1,$2,$3,now(),now(),'manual',1,$4)`, fixtureID, providerID, providerMatchID, snapshotID)
	if err != nil {
		t.Fatal(err)
	}
}

func seedFixtureRepairObservation(t *testing.T, pool *pgxpool.Pool, snapshotID, semantic, providerMatchID, providerCompetitionID, fixtureID string, kickoff time.Time) {
	t.Helper()
	_, err := pool.Exec(context.Background(), `INSERT INTO football.product_provider_fixture_observations(
		semantic_sha256,provider_code,provider_match_id,provider_competition_id,canonical_fixture_id,
		source_snapshot_id,kickoff_at,canonical_status,provider_status,observed_at,stale_after,last_fetched_at)
		VALUES(encode(sha256(convert_to($1,'UTF8')),'hex'), 'fixture_repair_test', $2, $3, $4,
		$5, $6, 'SCHEDULED', 'scheduled', now(), now()+interval '3 minutes', now())`,
		semantic, providerMatchID, providerCompetitionID, fixtureID, snapshotID, kickoff)
	if err != nil {
		t.Fatal(err)
	}
}

func setServingCompetitionGeography(t *testing.T, pool *pgxpool.Pool, competition string) {
	t.Helper()
	_, err := pool.Exec(context.Background(), `UPDATE football.product_competitions
		SET country='Unknown Season Filter Test', geographic_scope='Unknown Season Filter Test'
		WHERE competition_id=$1`, competition)
	if err != nil {
		t.Fatal(err)
	}
}

func setServingCompetitionUnknownSeason(t *testing.T, pool *pgxpool.Pool, competition string) {
	t.Helper()
	_, err := pool.Exec(context.Background(), `UPDATE football.product_competitions SET season_label='  uNkNoWn  '
		WHERE competition_id=$1`, competition)
	if err != nil {
		t.Fatal(err)
	}
}

func assertFixtureHTTPFiltersUnknownSeason(t *testing.T, handler http.Handler, date, knownCompetition, knownFixture string) {
	t.Helper()
	fixtureResponse := httptest.NewRecorder()
	fixtureRequest := httptest.NewRequest(http.MethodGet, "/v1/fixtures?date="+date+"&country=Unknown%20Season%20Filter%20Test", nil)
	handler.ServeHTTP(fixtureResponse, fixtureRequest)
	if fixtureResponse.Code != http.StatusOK {
		t.Fatalf("fixtures status %d: %s", fixtureResponse.Code, fixtureResponse.Body)
	}
	var fixtures struct {
		Groups []FixtureGroup `json:"groups"`
	}
	if err := json.Unmarshal(fixtureResponse.Body.Bytes(), &fixtures); err != nil {
		t.Fatal(err)
	}
	if len(fixtures.Groups) != 1 || fixtures.Groups[0].Competition.ID != knownCompetition {
		t.Fatalf("unknown-season fixture group was returned: %+v", fixtures.Groups)
	}
	if len(fixtures.Groups[0].Fixtures) != 1 || fixtures.Groups[0].Fixtures[0].ID != knownFixture {
		t.Fatalf("unknown-season fixture was returned: %+v", fixtures.Groups[0].Fixtures)
	}
}

func assertCompetitionHTTPFiltersUnknownSeason(t *testing.T, handler http.Handler, knownCompetition string) {
	t.Helper()
	competitionResponse := httptest.NewRecorder()
	competitionRequest := httptest.NewRequest(http.MethodGet, "/v1/competitions?country=Unknown%20Season%20Filter%20Test", nil)
	handler.ServeHTTP(competitionResponse, competitionRequest)
	if competitionResponse.Code != http.StatusOK {
		t.Fatalf("competitions status %d: %s", competitionResponse.Code, competitionResponse.Body)
	}
	var competitions struct {
		Competitions []Competition `json:"competitions"`
	}
	if err := json.Unmarshal(competitionResponse.Body.Bytes(), &competitions); err != nil {
		t.Fatal(err)
	}
	if len(competitions.Competitions) != 1 || competitions.Competitions[0].ID != knownCompetition {
		t.Fatalf("unknown-season competition was returned: %+v", competitions.Competitions)
	}
}

func seedFixtureForSeason(t *testing.T, pool *pgxpool.Pool, competition, home, away, season string, kickoff time.Time) string {
	t.Helper()
	ctx := context.Background()
	var fixture string
	if err := pool.QueryRow(ctx, `INSERT INTO football.matches(competition_id,season_id)
		VALUES($1,$2) RETURNING id::text`, competition, season).Scan(&fixture); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO football.product_fixtures(
		fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,forecast_availability,updated_at)
		VALUES($1,$2,$3,$4,$5,'SCHEDULED','SOURCE_DATA_INCOMPLETE',now())`, fixture, competition, home, away, kickoff); err != nil {
		t.Fatal(err)
	}
	return fixture
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
