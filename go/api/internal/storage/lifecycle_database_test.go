package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// lifecycleHarness drives the five-hour policy with a deterministic clock and a
// controllable owner process.
type lifecycleHarness struct {
	t       *testing.T
	pool    *pgxpool.Pool
	m       *Manager
	now     time.Time
	running atomic.Bool
	auth    Authority
}

func newLifecycleHarness(t *testing.T, pool *pgxpool.Pool) *lifecycleHarness {
	t.Helper()
	h := &lifecycleHarness{t: t, pool: pool, now: time.Now().UTC().Truncate(time.Second)}
	h.running.Store(true)
	h.m = h.manager()
	h.auth = VerifyAuthority(context.Background(), pool)
	expect(t, h.auth.Verified, "authority: %s", h.auth.Problem)
	return h
}

func (h *lifecycleHarness) manager() *Manager {
	return &Manager{Pool: h.pool, Now: func() time.Time { return h.now },
		Policy: &Policy{MaxEntries: 100_000, LifecycleCleanup: &LifecyclePolicy{InactivitySeconds: 18000, CheckIntervalSeconds: 900,
			MaxPerRun: 5, TestDatabases: true, ApprovedBy: "owner", ApprovalRecord: "test-approval"}},
		OwnerProcess: func(context.Context, map[string]any) (bool, error) { return h.running.Load(), nil }}
}

func (h *lifecycleHarness) advance(d time.Duration) LifecycleRun {
	h.t.Helper()
	h.now = h.now.Add(d)
	h.m.run.Lock()
	h.m.lastLifecycle = time.Time{} // each step is a scheduled check
	h.m.run.Unlock()
	run, err := h.m.RunLifecycleCleanup(context.Background())
	must(h.t, err)
	expect(h.t, run.Skipped == "", "run skipped: %s", run.Skipped)
	return run
}

func randomMarker(prefix string) string {
	b := make([]byte, 32)
	_, _ = rand.Read(b)
	return prefix + hex.EncodeToString(b)
}

// registeredTestDatabase creates a database the way the integration harness does:
// marked with a run marker and registered with its owner.
func (h *lifecycleHarness) registeredTestDatabase() (string, int64, string) {
	h.t.Helper()
	ctx := context.Background()
	name, oid := disposableDatabase(h.t, h.pool)
	marker := randomMarker(disposableMarkerPrefix)
	_, err := h.pool.Exec(ctx, `COMMENT ON DATABASE `+pgx.Identifier{name}.Sanitize()+` IS `+quote(marker))
	must(h.t, err)
	key := PostgresIdentityKey(h.auth.SystemIdentifier, oid)
	_, err = h.pool.Exec(ctx, `INSERT INTO football.storage_lifecycle_resources(identity_key,resource_class,backend,identity,location,
 owner_kind,owner_ref,created_at,last_activity_at) VALUES($1,'TEST_DATABASE','postgres',$2,$3,'INTEGRATION_HARNESS',$4,$5,$5)`,
		key, map[string]any{"system_identifier": h.auth.SystemIdentifier, "oid": oid, "database": name}, h.auth.SystemIdentifier+"/"+name,
		map[string]any{"host": "test", "pid": 1, "process_started": "x", "marker": marker,
			"owned_marker": strings.Replace(marker, disposableMarkerPrefix, ownedMarkerPrefix, 1)}, h.now)
	must(h.t, err)
	must(h.t, lifecycleEvent(ctx, h.pool, key, "REGISTERED", map[string]any{"owner_kind": "INTEGRATION_HARNESS"}))
	return name, oid, key
}

func quote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }

func (h *lifecycleHarness) record(key string) LifecycleRecord {
	h.t.Helper()
	records, err := lifecycleRecords(context.Background(), h.pool, `identity_key=`+quote(key))
	must(h.t, err)
	r, ok := records[key]
	expect(h.t, ok, "lifecycle record %s missing", key)
	return r
}

func (h *lifecycleHarness) exists(oid int64) bool {
	var exists bool
	must(h.t, h.pool.QueryRow(context.Background(), `SELECT EXISTS(SELECT 1 FROM pg_database WHERE oid=$1::oid)`, oid).Scan(&exists))
	return exists
}

func (h *lifecycleHarness) events(key string) []string {
	rows, err := h.pool.Query(context.Background(), `SELECT event FROM football.storage_lifecycle_events WHERE identity_key=$1 ORDER BY event_id`, key)
	must(h.t, err)
	events, err := pgx.CollectRows(rows, pgx.RowTo[string])
	must(h.t, err)
	return events
}

func TestDatabaseLifecycleDeletesCompletedTestDatabaseAfterFiveHours(t *testing.T) {
	h := newLifecycleHarness(t, databasePool(t))
	_, oid, key := h.registeredTestDatabase()
	h.advance(time.Minute)
	expect(t, h.record(key).State == LifecycleActive, "a running owner keeps the database active")

	h.running.Store(false)
	h.advance(time.Hour)
	r := h.record(key)
	expect(t, r.State == LifecycleWaiting && r.Completion != nil && *r.Completion == "OWNER_EXITED", "owner exit completes the run: %+v", r)
	deadline := *r.EligibleAt

	h.advance(deadline.Sub(h.now) - time.Second)
	expect(t, h.record(key).State == LifecycleWaiting && h.exists(oid), "deleted before five hours")

	run := h.advance(time.Second)
	r = h.record(key)
	expect(t, run.Deleted == 1 && r.State == LifecycleDeleted && !h.exists(oid), "not deleted at five hours: %+v %+v", run, r)
	expect(t, r.ReclaimedBytes != nil && *r.ReclaimedBytes > 0 && run.ReclaimedBytes == *r.ReclaimedBytes, "reclaimed bytes not measured: %+v", r)
	var actor, state string
	must(t, h.pool.QueryRow(context.Background(), `SELECT approved_by,state FROM football.storage_operations WHERE operation_id=$1`, *r.OperationID).Scan(&actor, &state))
	expect(t, actor == "policy:test-approval:owner" && state == "SUCCEEDED", "operation %s %s", actor, state)
	for _, want := range []string{"REGISTERED", "COMPLETED", "ELIGIBLE", "CLAIMED", "SUBMITTED", "DELETED"} {
		expect(t, contains(h.events(key), want), "missing %s event: %v", want, h.events(key))
	}
	// Terminal rows cannot be revived and audit events cannot be rewritten.
	_, err := h.pool.Exec(context.Background(), `UPDATE football.storage_lifecycle_resources SET state='ACTIVE' WHERE identity_key=$1`, key)
	expect(t, err != nil, "terminal lifecycle row was revived")
	_, err = h.pool.Exec(context.Background(), `DELETE FROM football.storage_lifecycle_events WHERE identity_key=$1`, key)
	expect(t, err != nil, "lifecycle audit trail was deleted")
}

func TestDatabaseLifecycleActivityAndSessionsBlockDeletion(t *testing.T) {
	pool := databasePool(t)
	h := newLifecycleHarness(t, pool)
	name, oid, key := h.registeredTestDatabase()
	h.running.Store(false)
	h.advance(time.Minute)
	first := *h.record(key).EligibleAt

	conn := connectTo(t, pool, name)
	var one int
	must(t, conn.QueryRow(context.Background(), `SELECT count(*) FROM pg_class`).Scan(&one))
	h.advance(2 * time.Hour)
	r := h.record(key)
	expect(t, r.State == LifecycleActive && contains(r.Blockers, "1 active PostgreSQL session(s)"), "an open session must keep it active: %+v", r)

	h.advance(10 * time.Hour)
	expect(t, h.exists(oid) && h.record(key).State == LifecycleActive, "a database with a session was deleted")
	must(t, conn.QueryRow(context.Background(), `SELECT 1`).Scan(&one))
	must(t, conn.Close(context.Background()))

	h.advance(time.Hour)
	r = h.record(key)
	expect(t, r.State == LifecycleWaiting && r.EligibleAt.After(first.Add(10*time.Hour)), "the session must restart the window: %+v", r)
}

func TestDatabaseLifecycleRejectsMismatchAndProtection(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	h := newLifecycleHarness(t, pool)
	name, oid, key := h.registeredTestDatabase()
	h.running.Store(false)
	_, err := pool.Exec(ctx, `COMMENT ON DATABASE `+pgx.Identifier{name}.Sanitize()+` IS 'copied by hand'`)
	must(t, err)
	h.advance(time.Minute)
	h.advance(6 * time.Hour)
	r := h.record(key)
	expect(t, r.State == LifecycleBlocked && h.exists(oid), "a marker mismatch must block: %+v", r)

	// A protection recorded after registration blocks; eligibility is refused in SQL.
	_, other, otherKey := h.registeredTestDatabase()
	_, err = pool.Exec(ctx, `INSERT INTO football.storage_protections(backend,identity_key,identity,role,reason,recorded_by)
 VALUES('postgres',$1,$2,'OWNER_PROTECTED','keep','test')`, otherKey, map[string]any{"system_identifier": h.auth.SystemIdentifier, "oid": other})
	must(t, err)
	h.advance(6 * time.Hour)
	expect(t, h.record(otherKey).State == LifecycleBlocked && h.exists(other), "a protected database left the BLOCKED state")
	_, err = pool.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET state='ELIGIBLE',completed_at=now(),completion='OWNER_EXITED',eligible_at=now() WHERE identity_key=$1`, otherKey)
	expect(t, err != nil && strings.Contains(err.Error(), "protected"), "SQL accepted a protected eligible row: %v", err)

	// The authoritative database can never be registered.
	_, err = pool.Exec(ctx, `INSERT INTO football.storage_lifecycle_resources(identity_key,resource_class,backend,identity,location,owner_kind,owner_ref,created_at,last_activity_at)
 VALUES($1,'TEST_DATABASE','postgres',$2,'x','INTEGRATION_HARNESS','{}',now(),now())`, h.auth.IdentityKey(),
		map[string]any{"system_identifier": h.auth.SystemIdentifier, "oid": h.auth.OID})
	expect(t, err != nil, "the authoritative database was registered for cleanup")
}

func TestDatabaseLifecycleStaleEligibilityIsRejected(t *testing.T) {
	h := newLifecycleHarness(t, databasePool(t))
	_, oid, key := h.registeredTestDatabase()
	h.running.Store(false)
	h.advance(time.Minute)
	// Simulate activity between the eligibility decision and execution.
	_, err := h.pool.Exec(context.Background(), `UPDATE football.storage_lifecycle_resources SET state='ELIGIBLE',
 activity_fingerprint='stale',eligible_at=$2 WHERE identity_key=$1`, key, h.now)
	must(t, err)
	rec := h.record(key)
	run := LifecycleRun{}
	h.m.deleteEligible(context.Background(), rec, *h.m.Policy.LifecycleCleanup, &run, h.now)
	expect(t, run.Submitted == 0 && h.exists(oid) && contains(h.events(key), "REJECTED"), "stale eligibility was executed: %+v", run)
}

func TestDatabaseLifecycleConcurrentWorkersDeleteOnce(t *testing.T) {
	pool := databasePool(t)
	h := newLifecycleHarness(t, pool)
	_, oid, key := h.registeredTestDatabase()
	h.running.Store(false)
	h.advance(time.Minute)
	h.now = h.now.Add(6 * time.Hour)
	token, ok, err := claimLifecycle(context.Background(), pool, key, h.now, time.Minute)
	expect(t, err == nil && !ok && token == "", "a WAITING row was claimable: %v", err)

	workers := []*Manager{h.manager(), h.manager(), h.manager()}
	var wg sync.WaitGroup
	results := make([]LifecycleRun, len(workers))
	for i, w := range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			results[i], _ = w.RunLifecycleCleanup(context.Background())
		}()
	}
	wg.Wait()
	deleted := 0
	for _, r := range results {
		deleted += r.Deleted
	}
	var operations int
	must(t, pool.QueryRow(context.Background(), `SELECT count(*) FROM football.storage_operations WHERE identity_key=$1`, key).Scan(&operations))
	expect(t, !h.exists(oid) && operations == 1, "concurrent workers: deleted=%d operations=%d", deleted, operations)
}

func TestDatabaseLifecycleInterruptedDeletionSettles(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	h := newLifecycleHarness(t, pool)
	for _, dropped := range []bool{true, false} {
		name, oid, key := h.registeredTestDatabase()
		operation := newUUID()
		_, err := pool.Exec(ctx, `INSERT INTO football.storage_operations(operation_id,batch_id,action,resource_id,backend,location,identity_key,identity,plan_sha256,approved_by,confirmation,state)
 VALUES($1,$2,'DELETE',$3,'postgres',$4,$5,$6,$7,'policy:test-approval:owner','typed:DELETE 1','PENDING')`, operation, newUUID(),
			Identity("postgres", key), h.auth.SystemIdentifier+"/"+name, key, map[string]any{"system_identifier": h.auth.SystemIdentifier, "oid": oid}, strings.Repeat("c", 64))
		must(t, err)
		_, err = pool.Exec(ctx, `UPDATE football.storage_operations SET state='RUNNING',started_at=now() WHERE operation_id=$1`, operation)
		must(t, err)
		_, err = pool.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET state='DELETING',operation_id=$2,
 completed_at=now(),completion='OWNER_EXITED',eligible_at=now() WHERE identity_key=$1`, key, operation)
		must(t, err)
		if dropped {
			_, err = pool.Exec(ctx, `DROP DATABASE `+pgx.Identifier{name}.Sanitize())
			must(t, err)
		}
		must(t, h.m.Recover(ctx)) // the API restarts
		h.advance(time.Hour)
		want := LifecycleDeleted
		if !dropped {
			want = LifecycleBlocked
		}
		r := h.record(key)
		expect(t, r.State == want, "interrupted deletion (dropped=%v) settled as %s: %+v", dropped, r.State, r)
	}
}

func TestDatabaseLifecycleDiscoversRunChildrenButNotUnregistered(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	h := newLifecycleHarness(t, pool)
	_, _, parent := h.registeredTestDatabase()
	owned := h.record(parent).OwnerRef["owned_marker"].(string)
	child, childOID := disposableDatabase(t, pool)
	_, err := pool.Exec(ctx, `COMMENT ON DATABASE `+pgx.Identifier{child}.Sanitize()+` IS `+quote(owned))
	must(t, err)
	stray, strayOID := disposableDatabase(t, pool)
	_, err = pool.Exec(ctx, `COMMENT ON DATABASE `+pgx.Identifier{stray}.Sanitize()+` IS `+quote(randomMarker(ownedMarkerPrefix)))
	must(t, err)
	h.advance(time.Minute)
	r := h.record(PostgresIdentityKey(h.auth.SystemIdentifier, childOID))
	expect(t, r.OwnerKind == "HARNESS_CHILD" && r.OwnerRef["owned_marker"] == owned, "child not linked to its run: %+v", r)
	records, err := lifecycleRecords(ctx, pool, `identity_key=`+quote(PostgresIdentityKey(h.auth.SystemIdentifier, strayOID)))
	must(t, err)
	expect(t, len(records) == 0, "an unregistered marked database entered the lifecycle")
	status, err := h.m.LifecycleStatus(ctx)
	must(t, err)
	found := false
	for _, u := range status.Unregistered {
		found = found || u.OID == strayOID
	}
	expect(t, found && status.Deployed, "unregistered database not reported: %+v", status.Unregistered)
}

func connectTo(t *testing.T, pool *pgxpool.Pool, database string) *pgx.Conn {
	t.Helper()
	config := pool.Config().ConnConfig.Copy()
	config.Database = database
	conn, err := pgx.ConnectConfig(context.Background(), config)
	must(t, err)
	t.Cleanup(func() { _ = conn.Close(context.Background()) })
	return conn
}

// worktreeRepository builds a repository with a remote and three worktrees under
// one root: merged (its pull request merged at HEAD), dirty and unmerged.
func worktreeRepository(t *testing.T) (repo, root string, paths map[string]string) {
	t.Helper()
	base, err := filepath.EvalSymlinks(t.TempDir())
	must(t, err)
	origin, repo, root := filepath.Join(base, "origin.git"), filepath.Join(base, "repo"), filepath.Join(base, "worktrees")
	must(t, os.MkdirAll(root, 0o755))
	git(t, base, "init", "-q", "--bare", origin)
	git(t, base, "init", "-q", "-b", "main", repo)
	git(t, repo, "config", "user.email", "test@example.invalid")
	git(t, repo, "config", "user.name", "test")
	git(t, repo, "config", "commit.gpgsign", "false")
	must(t, os.WriteFile(filepath.Join(repo, "README"), []byte("x\n"), 0o644))
	git(t, repo, "add", "README")
	git(t, repo, "commit", "-q", "-m", "init")
	git(t, repo, "remote", "add", "origin", origin)
	git(t, repo, "push", "-q", "origin", "main")
	paths = map[string]string{}
	for _, name := range []string{"merged", "dirty", "unmerged"} {
		path := filepath.Join(root, name)
		git(t, repo, "worktree", "add", "-q", "-b", "task/"+name, path)
		must(t, os.WriteFile(filepath.Join(path, name), []byte(name+"\n"), 0o644))
		git(t, path, "add", name)
		git(t, path, "commit", "-q", "-m", name)
		git(t, path, "push", "-q", "origin", "task/"+name)
		paths[name] = path
	}
	git(t, repo, "merge", "-q", "--no-ff", "-m", "merge", "task/merged")
	git(t, repo, "merge", "-q", "--no-ff", "-m", "merge", "task/dirty")
	git(t, repo, "push", "-q", "origin", "main")
	git(t, repo, "fetch", "-q", "origin")
	must(t, os.WriteFile(filepath.Join(paths["dirty"], "notes.txt"), []byte("unsaved\n"), 0o644))
	return repo, root, paths
}

func TestDatabaseLifecycleRemovesOnlyMergedCleanInactiveWorktrees(t *testing.T) {
	h := newLifecycleHarness(t, databasePool(t))
	repo, root, paths := worktreeRepository(t)
	prMerged := atomic.Bool{}
	prMerged.Store(true)
	h.m.Repository = repo
	h.m.Policy.LifecycleCleanup.TestDatabases = false
	h.m.Policy.LifecycleCleanup.Worktrees = &WorktreeLifecycle{TargetRef: "refs/remotes/origin/main", Roots: []string{root}}
	h.m.PRVerifier = func(_ context.Context, _, branch, head, base string) (bool, error) {
		return prMerged.Load() && base == "main" && strings.HasPrefix(branch, "task/") && head != "", nil
	}
	key := func(name string) string {
		return "git:" + git(t, paths[name], "rev-parse", "--path-format=absolute", "--git-dir")
	}
	merged, dirty, unmerged := key("merged"), key("dirty"), key("unmerged")

	// Without a confirmed pull request nothing completes.
	prMerged.Store(false)
	h.advance(time.Minute)
	r := h.record(merged)
	expect(t, r.State == LifecycleActive && r.CompletedAt == nil && contains(r.Blockers, "no merged pull request for this branch at its current HEAD"),
		"an unconfirmed PR must not complete the worktree: %+v", r)
	prMerged.Store(true)
	h.advance(time.Hour)
	r = h.record(merged)
	expect(t, r.State == LifecycleWaiting && *r.Completion == "PR_MERGED", "merged worktree should wait: %+v", r)
	expect(t, h.record(unmerged).State == LifecycleActive, "unmerged worktree must stay active: %+v", h.record(unmerged))
	expect(t, h.record(dirty).State == LifecycleBlocked, "dirty worktree must be blocked: %+v", h.record(dirty))

	// Activity (a reflog entry from a new branch checkout and back) restarts the window.
	h.advance(4 * time.Hour)
	git(t, paths["merged"], "checkout", "-q", "-b", "scratch")
	git(t, paths["merged"], "checkout", "-q", "task/merged")
	git(t, paths["merged"], "branch", "-q", "-D", "scratch")
	h.advance(2 * time.Hour)
	r = h.record(merged)
	expect(t, r.State == LifecycleWaiting && r.LastActivityAt.Equal(h.now), "activity did not reset the window: %+v", r)

	run := h.advance(5 * time.Hour)
	_, err := os.Lstat(paths["merged"])
	expect(t, run.Deleted == 1 && os.IsNotExist(err) && h.record(merged).State == LifecycleDeleted, "merged worktree not removed: %+v %v", run, err)
	expect(t, git(t, repo, "branch", "--list", "task/merged") != "", "the merged branch must be kept")
	h.advance(10 * time.Hour)
	expectPresent(t, paths["dirty"], paths["unmerged"], filepath.Join(paths["dirty"], "notes.txt"))
}

func expectPresent(t *testing.T, paths ...string) {
	t.Helper()
	for _, path := range paths {
		_, err := os.Lstat(path)
		expect(t, err == nil, "%s was removed", path)
	}
}
