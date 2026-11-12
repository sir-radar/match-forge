package storage

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"football-forecasting/go/api/internal/testdb"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func databasePool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	url := testdb.URL(t)
	pool, err := pgxpool.New(context.Background(), url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	return pool
}
func testID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
}
func runningWork(t *testing.T, pool *pgxpool.Pool) string {
	t.Helper()
	id := testID()
	ctx := context.Background()
	_, err := pool.Exec(ctx, `SELECT football.enqueue_work($1::uuid,'STORAGE_LIFECYCLE',$1::text,$2,0,clock_timestamp(),3,0::double precision,0::double precision,1::double precision,ARRAY[]::uuid[],NULL::uuid,0::double precision)`, id, strings.Repeat("a", 64))
	if err != nil {
		t.Fatal(err)
	}
	_, err = pool.Exec(ctx, `SELECT * FROM football.claim_work($2::text,interval '10 minutes',ARRAY['STORAGE_LIFECYCLE'],ARRAY[$1::uuid])`, id, id)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `SELECT football.cancel_work($1)`, id) })
	return id
}
func TestDatabaseReviewPublicationFencesCancelledWorkers(t *testing.T) {
	pool := databasePool(t)
	id := runningWork(t, pool)
	lease := testLease(t, pool, id)
	ctx := context.Background()
	r := Review{ObservedAt: time.Now().UTC(), DryRun: true, PolicySHA256: strings.Repeat("b", 64), Resources: []Resource{{ID: Identity("filesystem", id), Backend: "filesystem", Location: id, Kind: "file", Subsystem: "test", Complete: true, Protected: true, State: "PROTECTED", Blockers: []string{}, Details: json.RawMessage(`{}`)}}, Alerts: []string{}}
	if err := Publish(ctx, pool, lease, r); err != nil {
		t.Fatal(err)
	}
	if err := Publish(ctx, pool, lease, r); err != nil {
		t.Fatal("idempotent retry", err)
	}
	if _, err := pool.Exec(ctx, `SELECT football.cancel_work($1)`, id); err != nil {
		t.Fatal(err)
	}
	if err := Publish(ctx, pool, lease, r); err == nil {
		t.Fatal("cancelled owner published")
	}
}

func TestDatabaseArchiveReceiptPreservesVerifiedAccounting(t *testing.T) {
	pool := databasePool(t)
	lease := testLease(t, pool, runningWork(t, pool))
	ctx := context.Background()
	source, out := archiveFixture(t)
	m, err := Pack(source, out, []string{"a.json", "b.json"}, time.Now().UTC().Add(time.Hour).Truncate(time.Second))
	if err != nil {
		t.Fatal(err)
	}
	for range 2 {
		if err = RecordArchive(ctx, pool, lease, out, m); err != nil {
			t.Fatal(err)
		}
	}
	different := m
	different.SourceRoot = out
	if err = RecordArchive(ctx, pool, lease, out, different); err == nil {
		t.Fatal("archive publication accepted different provenance for the same path")
	}
	receipts, err := archiveReceipts(ctx, pool)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.ContainsFunc(receipts, func(r Resource) bool {
		return r.Location == out && r.Complete && r.SHA256 == m.PayloadSHA256
	}) {
		t.Fatal("verified archive receipt missing")
	}
}
func TestDatabaseConcurrentCapacityAdmissionAndExpiredOwnership(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	work := runningWork(t, pool)
	lease := testLease(t, pool, work)
	device := testID()
	var group sync.WaitGroup
	results := make(chan error, 2)
	for range 2 {
		group.Go(func() {
			results <- Reserve(ctx, pool, testID(), lease, device, 600, 100, time.Now().Add(time.Hour), testFreeCapacity)
		})
	}
	group.Wait()
	close(results)
	successes := 0
	for err := range results {
		if err == nil {
			successes++
		}
	}
	if successes != 1 {
		t.Fatalf("capacity oversubscription: %d admissions", successes)
	}
	if _, err := pool.Exec(ctx, `UPDATE football.storage_reservations SET lease_until=clock_timestamp()-interval '1 hour' WHERE backend_identity=$1`, device); err != nil {
		t.Fatal(err)
	}
	if Reserve(ctx, pool, testID(), lease, device, 600, 100, time.Now().Add(time.Hour), testFreeCapacity) == nil {
		t.Fatal("expired resource was silently freed")
	}
}
func TestDatabaseReservationReleaseRequiresExactOwner(t *testing.T) {
	pool := databasePool(t)
	work := runningWork(t, pool)
	lease := testLease(t, pool, work)
	id := testID()
	ctx := context.Background()
	if err := Reserve(ctx, pool, id, lease, testID(), 1, 100, time.Now().Add(time.Hour), testFreeCapacity); err != nil {
		t.Fatal(err)
	}
	if Release(ctx, pool, id, "stranger") == nil {
		t.Fatal("wrong owner released resource")
	}
	if err := Release(ctx, pool, id, work); err != nil {
		t.Fatal(err)
	}
	if Release(ctx, pool, id, work) == nil {
		t.Fatal("duplicate release hid ownership mismatch")
	}
}

func TestDatabaseManagedRehearsalTeardownAfterSuccessAndFailure(t *testing.T) {
	pool := databasePool(t)
	config := pool.Config().ConnConfig
	target := url.URL{Scheme: "postgresql", User: url.UserPassword(config.User, config.Password), Host: net.JoinHostPort(config.Host, strconv.Itoa(int(config.Port))), Path: "/" + config.Database, RawQuery: "sslmode=disable"}
	for _, exit := range []string{"0", "7"} {
		work := runningWork(t, pool)
		lease := testLease(t, pool, work)
		p := testPolicy(t.TempDir())
		p.ReserveBytes = 1
		script := `import os,psycopg; c=psycopg.connect(os.environ['DATABASE_URL'],connect_timeout=5); assert c.info.dbname.startswith('football_managed_'); assert c.execute("SELECT current_setting('matchforge.database_role')").fetchone()[0]=='experimental'; c.close(); raise SystemExit(` + exit + `)`
		ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
		err := RehearseFixtures(ctx, pool, target.String(), lease, p, 1<<20, []string{filepath.Join(os.Getenv("FOOTBALL_PROJECT_ROOT"), ".venv/bin/python"), "-c", script})
		cancel()
		if (err == nil) != (exit == "0") {
			t.Fatalf("child exit %s: %v", exit, err)
		}
		assertRehearsalReleased(t, pool, work)
	}
}
func assertRehearsalReleased(t *testing.T, pool *pgxpool.Pool, work string) {
	t.Helper()
	var total, released, remaining int
	err := pool.QueryRow(context.Background(), `SELECT count(*),count(released_at),count(d.oid) FROM football.storage_reservations r LEFT JOIN pg_database d ON d.datname=r.resource_identity->>'database' WHERE work_id=$1`, work).Scan(&total, &released, &remaining)
	if err != nil {
		t.Fatal(err)
	}
	if total != 2 || released != 2 || remaining != 0 {
		t.Fatalf("owned rehearsal residue: total=%d released=%d remaining=%d", total, released, remaining)
	}
}

func testFreeCapacity(context.Context) (int64, error) { return 1000, nil }

func TestDatabaseAdmissionRemeasuresAfterACompletedAllocation(t *testing.T) {
	pool := databasePool(t)
	work := runningWork(t, pool)
	lease := testLease(t, pool, work)
	ctx := context.Background()
	device := testID()
	first := testID()
	free := int64(1000)
	measure := func(context.Context) (int64, error) { return free, nil }
	if err := Reserve(ctx, pool, first, lease, device, 600, 100, time.Now().Add(time.Hour), measure); err != nil {
		t.Fatal(err)
	}
	free = 400
	if err := Release(ctx, pool, first, work); err != nil {
		t.Fatal(err)
	}
	if Reserve(ctx, pool, testID(), lease, device, 600, 100, time.Now().Add(time.Hour), measure) == nil {
		t.Fatal("stale capacity reused after allocation release")
	}
}

func testLease(t *testing.T, pool *pgxpool.Pool, id string) Lease {
	t.Helper()
	lease := Lease{WorkID: id, Owner: id}
	if err := pool.QueryRow(context.Background(), `SELECT lease_token::text,generation FROM football.work_items WHERE work_id=$1`, id).Scan(&lease.Token, &lease.Generation); err != nil {
		t.Fatal(err)
	}
	return lease
}

func TestDatabaseReclaimedSameOwnerCannotUseAnOldClaim(t *testing.T) {
	pool := databasePool(t)
	work := runningWork(t, pool)
	old := testLease(t, pool, work)
	ctx := context.Background()
	if _, err := pool.Exec(ctx, `UPDATE football.work_items SET heartbeat_at=clock_timestamp()-interval '2 hours',lease_until=clock_timestamp()-interval '1 hour' WHERE work_id=$1`, work); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `SELECT * FROM football.claim_work($2::text,interval '10 minutes',ARRAY['STORAGE_LIFECYCLE'],ARRAY[$1::uuid])`, work, work); err != nil {
		t.Fatal(err)
	}
	current := testLease(t, pool, work)
	if old.Token == current.Token || old.Generation >= current.Generation {
		t.Fatal("work was not reclaimed")
	}
	if Reserve(ctx, pool, testID(), old, testID(), 1, 100, time.Now().Add(time.Hour), testFreeCapacity) == nil {
		t.Fatal("old claim borrowed a new generation with the same owner name")
	}
	if err := Reserve(ctx, pool, testID(), current, testID(), 1, 100, time.Now().Add(time.Hour), testFreeCapacity); err != nil {
		t.Fatal(err)
	}
}
