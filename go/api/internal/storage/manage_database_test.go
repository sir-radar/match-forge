package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// disposableDatabase creates an empty, uniquely named database in the test
// cluster and drops it at cleanup if a test did not.
func disposableDatabase(t *testing.T, pool *pgxpool.Pool) (string, int64) {
	t.Helper()
	b := make([]byte, 6)
	_, _ = rand.Read(b)
	name := "mf_storage_t_" + hex.EncodeToString(b)
	ctx := context.Background()
	if _, err := pool.Exec(ctx, `CREATE DATABASE `+pgx.Identifier{name}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DROP DATABASE IF EXISTS `+pgx.Identifier{name}.Sanitize()+` WITH (FORCE)`)
	})
	var oid int64
	must(t, pool.QueryRow(ctx, `SELECT oid::bigint FROM pg_database WHERE datname=$1`, name).Scan(&oid))
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DROP DATABASE IF EXISTS `+pgx.Identifier{QuarantinePrefix + strconv.FormatInt(oid, 10)}.Sanitize()+` WITH (FORCE)`)
	})
	return name, oid
}

func managedDatabase(t *testing.T, m *Manager, oid int64) ManagedResource {
	t.Helper()
	inv, err := m.Inventory(context.Background())
	must(t, err)
	for _, r := range inv.Resources {
		if r.Backend == "postgres" && r.Identity["oid"] == oid {
			return r
		}
	}
	t.Fatalf("database %d not in inventory", oid)
	return ManagedResource{}
}

func waitTerminal(t *testing.T, pool *pgxpool.Pool, batch string) string {
	t.Helper()
	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		var state, message string
		must(t, pool.QueryRow(context.Background(), `SELECT state,coalesce(error,'') FROM football.storage_operations WHERE batch_id=$1 ORDER BY created_at LIMIT 1`, batch).Scan(&state, &message))
		if state != "PENDING" && state != "RUNNING" {
			return state + ":" + message
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatal("operation did not finish")
	return ""
}

func TestDatabaseAuthoritativeDatabaseCannotBeDeleted(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	m := &Manager{Pool: pool}
	auth := VerifyAuthority(ctx, pool)
	expect(t, auth.Verified, "%s", auth.Problem)
	r := managedDatabase(t, m, auth.OID)
	expect(t, !(r.Classification != Protected || len(r.Actions) != 0 || r.Reasons[0] != AuthoritativeMessage), "authoritative database must be protected without actions: %+v", r)
	plan, _, err := m.Preview(ctx, ActionDelete, []string{r.ResourceID})
	expect(t, !(err != nil || len(plan.Items) != 0 || len(plan.Blocked) != 1), "authoritative database entered a delete plan: %+v %v", plan, err)
	// A forged plan digest for the authoritative resource is rejected before any write.
	_, err = m.Submit(ctx, SubmitRequest{Action: ActionDelete, ResourceIDs: []string{r.ResourceID}, PlanSHA256: strings.Repeat("a", 64), Confirmation: "DELETE 1", Confirmed: true}, "test")
	expect(t, err == ErrStalePlan, "forged submission not rejected: %v", err)
	// Even a direct SQL write bypassing the API is refused by the database.
	_, err = pool.Exec(ctx, `INSERT INTO football.storage_operations(operation_id,batch_id,action,resource_id,backend,location,identity_key,identity,plan_sha256,approved_by,confirmation)
 VALUES(gen_random_uuid(),gen_random_uuid(),'DELETE',$1,'postgres','x',$2,$3,$4,'test','typed')`, r.ResourceID, r.IdentityKey,
		map[string]any{"system_identifier": auth.SystemIdentifier, "oid": auth.OID}, strings.Repeat("b", 64))
	expect(t, !(err == nil || !strings.Contains(err.Error(), "protected")), "database guard accepted an authoritative deletion: %v", err)
	// The registry is append-only: protection cannot be removed through SQL either.
	if _, err = pool.Exec(ctx, `DELETE FROM football.storage_protections WHERE role='AUTHORITATIVE_OPERATING_DATABASE'`); err == nil {
		t.Fatal("authoritative protection was removable")
	}
}

func TestDatabaseVerifiedDisposableDatabaseIsDeletedAndMeasured(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	m := &Manager{Pool: pool}
	name, oid := disposableDatabase(t, pool)
	r := managedDatabase(t, m, oid)
	expect(t, !(r.Classification != ReviewRequired || r.Allows(ActionDelete)), "uncompared database must need review: %+v", r)
	must(t, m.compareOne(ctx, r.ResourceID))
	r = managedDatabase(t, m, oid)
	expect(t, !(r.Classification != Eligible || !r.Allows(ActionDelete) || r.Evidence == nil || r.Evidence.Finding != "NO_UNIQUE_CANONICAL_IDENTITIES"), "empty database with no unique identities should be eligible: %+v", r)
	plan, _, err := m.Preview(ctx, ActionDelete, []string{r.ResourceID})
	expect(t, !(err != nil || len(plan.Items) != 1 || plan.TypedConfirmation != "DELETE 1" || plan.ExpectedUniqueBytes <= 0), "unexpected plan: %+v %v", plan, err)
	_, err = m.Submit(ctx, SubmitRequest{Action: ActionDelete, ResourceIDs: []string{r.ResourceID}, PlanSHA256: plan.PlanSHA256, Confirmation: "delete 1", Confirmed: true}, "test")
	expect(t, err == ErrConfirmation, "wrong typed confirmation accepted: %v", err)
	batch, err := m.Submit(ctx, SubmitRequest{Action: ActionDelete, ResourceIDs: []string{r.ResourceID}, PlanSHA256: plan.PlanSHA256, Confirmation: "DELETE 1", Confirmed: true}, "test")
	must(t, err)
	expect(t, waitTerminal(t, pool, batch.BatchID) == "SUCCEEDED:", "operation did not succeed")
	var exists bool
	var reclaimed *int64
	_ = pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)`, name).Scan(&exists)
	_ = pool.QueryRow(ctx, `SELECT reclaimed_bytes FROM football.storage_operations WHERE batch_id=$1`, batch.BatchID).Scan(&reclaimed)
	expect(t, !(exists || reclaimed == nil || *reclaimed <= 0), "database not verifiably removed: exists=%v reclaimed=%v", exists, reclaimed)
}

func TestDatabaseConnectedRenamedAndLaterProtectedDatabasesAreRefused(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	m := &Manager{Pool: pool}
	name, oid := disposableDatabase(t, pool)
	id := managedDatabase(t, m, oid).ResourceID
	must(t, m.compareOne(ctx, id))
	// An active consumer makes the database protected.
	config := pool.Config().ConnConfig.Copy()
	config.Database = name
	conn, err := pgx.ConnectConfig(ctx, config)
	must(t, err)
	{
		r := managedDatabase(t, m, oid)
		expect(t, !(r.Classification != Protected), "connected database not protected: %+v", r)
	}
	_ = conn.Close(ctx)
	time.Sleep(200 * time.Millisecond)
	plan, _, err := m.Preview(ctx, ActionDelete, []string{id})
	expect(t, !(err != nil || len(plan.Items) != 1), "expected eligible after disconnect: %+v %v", plan, err)
	// Protection recorded after preview makes the old plan stale.
	must(t, m.Protect(ctx, id, "owner keeps this copy", "test"))
	_, err = m.Submit(ctx, SubmitRequest{Action: ActionDelete, ResourceIDs: []string{id}, PlanSHA256: plan.PlanSHA256, Confirmation: "DELETE 1", Confirmed: true}, "test")
	expect(t, err == ErrStalePlan, "stale approval accepted: %v", err)
	// Renaming does not remove OID-bound protection.
	renamed := name + "_renamed"
	if _, err = pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{name}.Sanitize()+` RENAME TO `+pgx.Identifier{renamed}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DROP DATABASE IF EXISTS `+pgx.Identifier{renamed}.Sanitize()+` WITH (FORCE)`)
	})
	{
		r := managedDatabase(t, m, oid)
		expect(t, !(r.Classification != Protected || r.Allows(ActionDelete)), "rename bypassed protection: %+v", r)
	}
}

func TestDatabaseProtectionAddedBeforeExecutionBlocksPendingOperation(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	m := &Manager{Pool: pool}
	name, oid := disposableDatabase(t, pool)
	r := managedDatabase(t, m, oid)
	must(t, m.compareOne(ctx, r.ResourceID))
	r = managedDatabase(t, m, oid)
	op := operationRow{ID: newUUID(), Action: ActionDelete, ResourceID: r.ResourceID, Backend: "postgres", Location: r.Location, IdentityKey: r.IdentityKey,
		Identity: map[string]any{"system_identifier": r.Identity["system_identifier"], "oid": oid, "evidence_sha256": r.EvidenceSHA256}}
	if _, err := pool.Exec(ctx, `INSERT INTO football.storage_operations(operation_id,batch_id,action,resource_id,backend,location,identity_key,identity,plan_sha256,approved_by,confirmation)
 VALUES($1,gen_random_uuid(),'DELETE',$2,'postgres',$3,$4,$5,$6,'test','typed:DELETE 1')`, op.ID, op.ResourceID, op.Location, op.IdentityKey, op.Identity, strings.Repeat("c", 64)); err != nil {
		t.Fatal(err)
	}
	must(t, m.Protect(ctx, r.ResourceID, "classification changed concurrently", "test"))
	m.executeOne(ctx, op)
	var state string
	var exists bool
	_ = pool.QueryRow(ctx, `SELECT state FROM football.storage_operations WHERE operation_id=$1`, op.ID).Scan(&state)
	_ = pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)`, name).Scan(&exists)
	expect(t, !(state != "BLOCKED" || !exists), "protected database was processed: state=%s exists=%v", state, exists)
}

func TestDatabaseQuarantineRestoreAndMixedBatch(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	m := &Manager{Pool: pool}
	name, oid := disposableDatabase(t, pool)
	_, protectedOID := disposableDatabase(t, pool)
	eligible := managedDatabase(t, m, oid)
	other := managedDatabase(t, m, protectedOID)
	for _, id := range []string{eligible.ResourceID, other.ResourceID} {
		must(t, m.compareOne(ctx, id))
	}
	must(t, m.Protect(ctx, other.ResourceID, "independently required copy", "test"))
	plan, _, err := m.Preview(ctx, ActionQuarantine, []string{eligible.ResourceID, other.ResourceID})
	expect(t, !(err != nil || len(plan.Items) != 1 || len(plan.Blocked) != 1 || plan.Items[0].ResourceID != eligible.ResourceID), "mixed batch should keep the eligible item only: %+v %v", plan, err)
	batch, err := m.Submit(ctx, SubmitRequest{Action: ActionQuarantine, ResourceIDs: []string{eligible.ResourceID}, PlanSHA256: plan.PlanSHA256, Confirmed: true}, "test")
	must(t, err)
	expect(t, waitTerminal(t, pool, batch.BatchID) == "SUCCEEDED:", "operation did not succeed")
	q := managedDatabase(t, m, oid)
	expect(t, !(q.Quarantine == nil || q.Name != QuarantinePrefix+strconv.FormatInt(oid, 10) || !q.Allows(ActionRestore) || q.ResourceID != eligible.ResourceID), "quarantined database not tracked by identity: %+v", q)
	plan, _, err = m.Preview(ctx, ActionRestore, []string{q.ResourceID})
	expect(t, !(err != nil || len(plan.Items) != 1), "restore plan: %+v %v", plan, err)
	batch, err = m.Submit(ctx, SubmitRequest{Action: ActionRestore, ResourceIDs: []string{q.ResourceID}, PlanSHA256: plan.PlanSHA256, Confirmed: true}, "test")
	must(t, err)
	expect(t, waitTerminal(t, pool, batch.BatchID) == "SUCCEEDED:", "operation did not succeed")
	restored := managedDatabase(t, m, oid)
	expect(t, !(restored.Name != name || restored.Quarantine != nil), "restore did not return the original name: %+v", restored)
}

func TestDatabaseUniqueRowsNeedOwnerDispositionBoundToEvidence(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	m := &Manager{Pool: pool}
	name, oid := disposableDatabase(t, pool)
	config := pool.Config().ConnConfig.Copy()
	config.Database = name
	conn, err := pgx.ConnectConfig(ctx, config)
	must(t, err)
	_, err = conn.Exec(ctx, `CREATE SCHEMA football; CREATE TABLE football.teams(id uuid PRIMARY KEY); INSERT INTO football.teams VALUES (gen_random_uuid())`)
	_ = conn.Close(ctx)
	must(t, err)
	time.Sleep(200 * time.Millisecond)
	r := managedDatabase(t, m, oid)
	must(t, m.compareOne(ctx, r.ResourceID))
	r = managedDatabase(t, m, oid)
	expect(t, !(r.Classification != ReviewRequired || r.Evidence == nil || r.Evidence.Finding != "UNIQUE_CANONICAL_IDENTITIES_PRESENT"), "unique row must require review: %+v", r)
	err = m.Dispose(ctx, r.ResourceID, strings.Repeat("d", 64), "UNIQUE_DATA_NOT_REQUIRED", "synthetic test row created by this test", "test")
	expect(t, err == ErrStalePlan, "disposition for other evidence accepted: %v", err)
	must(t, m.Dispose(ctx, r.ResourceID, r.EvidenceSHA256, "UNIQUE_DATA_NOT_REQUIRED", "synthetic test row created by this test", "test"))
	{
		r = managedDatabase(t, m, oid)
		expect(t, !(r.Classification != Eligible), "disposition did not resolve the review: %+v", r)
	}
	// Unchanged evidence keeps the binding; changed content invalidates it.
	must(t, m.compareOne(ctx, r.ResourceID))
	{
		r = managedDatabase(t, m, oid)
		expect(t, !(r.Classification != Eligible), "identical evidence lost its disposition: %+v", r)
	}
	conn, err = pgx.ConnectConfig(ctx, config)
	must(t, err)
	_, err = conn.Exec(ctx, `INSERT INTO football.teams VALUES (gen_random_uuid())`)
	_ = conn.Close(ctx)
	must(t, err)
	time.Sleep(200 * time.Millisecond)
	must(t, m.compareOne(ctx, r.ResourceID))
	{
		r = managedDatabase(t, m, oid)
		expect(t, !(r.Classification != ReviewRequired), "disposition survived new evidence: %+v", r)
	}
}

func TestUnverifiedAuthorityDisablesDatabaseDeletion(t *testing.T) {
	auth := Authority{SystemIdentifier: "1", OID: 5, Verified: false, Problem: "mismatch"}
	r := assessDatabase(databaseRow{name: "football_old_copy", oid: 99, size: 1}, auth, databaseFacts{evidence: map[string]storedEvidence{
		PostgresIdentityKey("1", 99): {Evidence: Evidence{Finding: "NO_UNIQUE_CANONICAL_IDENTITIES", SHA256: strings.Repeat("e", 64), ObservedAt: time.Now()}, oid: 99, size: 1},
	}}, time.Now(), time.Hour)
	r.finish()
	expect(t, !(r.Classification != Protected || r.Allows(ActionDelete)), "unverified authority must fail closed: %+v", r)
	auth.Verified = true
	r = assessDatabase(databaseRow{name: "football", oid: 5, size: 1}, auth, databaseFacts{}, time.Now(), time.Hour)
	r.finish()
	expect(t, !(r.Classification != Protected || r.Allows(ActionDelete) || r.Role != "AUTHORITATIVE_OPERATING_DATABASE"), "authoritative OID not protected: %+v", r)
}

func TestDatabaseAutomaticCleanupDeletesOnlyApprovedAgedDisposableFiles(t *testing.T) {
	pool := databasePool(t)
	InvalidateMeasurements()
	p, root := managedPolicy(t, "disposable")
	p.IntervalSeconds = 3600
	p.AutomaticCleanup = []AutomaticPolicy{{Action: "DELETE_DISPOSABLE", Root: root, MinAgeSeconds: 86400, MaxPerRun: 10, ApprovedBy: "owner", ApprovalRecord: "test-approval"}}
	old := time.Now().Add(-72 * time.Hour)
	for _, name := range []string{"aged", "evidence", "fresh"} {
		write(t, filepath.Join(root, name, "x.bin"), 1000)
		if name != "fresh" {
			must(t, os.Chtimes(filepath.Join(root, name), old, old))
		}
	}
	m := &Manager{Pool: pool, Policy: &p}
	submitted, err := m.RunAutomaticCleanup(context.Background())
	must(t, err)
	expect(t, submitted == 1, "submitted %d", submitted)
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		if _, err = os.Stat(filepath.Join(root, "aged")); os.IsNotExist(err) {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	_, agedErr := os.Stat(filepath.Join(root, "aged"))
	_, evidenceErr := os.Stat(filepath.Join(root, "evidence", "x.bin"))
	_, freshErr := os.Stat(filepath.Join(root, "fresh", "x.bin"))
	expect(t, os.IsNotExist(agedErr) && evidenceErr == nil && freshErr == nil, "automatic cleanup outcome aged=%v evidence=%v fresh=%v", agedErr, evidenceErr, freshErr)
	again, err := m.RunAutomaticCleanup(context.Background())
	expect(t, err == nil && again == 0, "automatic cleanup ignored its interval: %d %v", again, err)
}
