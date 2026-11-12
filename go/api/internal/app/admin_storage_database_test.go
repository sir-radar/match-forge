package app

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"football-forecasting/go/api/internal/storage"
)

func TestStorageDatabaseCommonWorkReviewAndExactApproval(t *testing.T) {
	ctx := context.Background()
	runner, id, _ := storageDatabaseSetup(t)
	summary, err := runner.storageReview(ctx, id)
	if err != nil {
		t.Fatal(err)
	}
	if summary["dry_run"] != true || summary["reclaimed_bytes"] != 0 {
		t.Fatal(summary)
	}
	view, err := runner.StorageView(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if view.Latest == nil || view.DestructiveEnabled {
		t.Fatal(view)
	}
	approvalID, _ := newUUID()
	application := newAdminTestApp(runner)
	approval := storageApproval{ID: approvalID, WorkID: *view.WorkID, Manifest: *view.ManifestSHA256, Resources: []string{view.Latest.Resources[0].ID}, Confirmed: true, Disposition: "REVIEWED", ExpiresAt: time.Now().Add(time.Hour)}
	if status := recordTestApproval(application, approval); status != 201 {
		t.Fatalf("valid review receipt: %d", status)
	}
	approval.ID, _ = newUUID()
	approval.Manifest = strings.Repeat("0", 64)
	if status := recordTestApproval(application, approval); status != 409 {
		t.Fatalf("stale digest accepted: %d", status)
	}
}
func recordTestApproval(app *App, approval storageApproval) int {
	payload, _ := json.Marshal(approval)
	r := httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8080/v1/admin/storage/approvals", strings.NewReader(string(payload)))
	r.RemoteAddr = "127.0.0.1:12345"
	r.Header.Set("Origin", "http://127.0.0.1:3000")
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	app.Handler().ServeHTTP(w, r)
	return w.Code
}

func storageDatabaseSetup(t *testing.T) (*CommandSyncRunner, string, storage.Policy) {
	t.Helper()
	pool := servingDatabasePool(t)
	ctx := context.Background()
	id, _ := newUUID()
	if _, err := pool.Exec(ctx, `INSERT INTO football.product_sync_runs(run_id,sync_type,status,worker_id,heartbeat_at) VALUES($1::uuid,'STORAGE_LIFECYCLE','QUEUED',$2::text,clock_timestamp())`, id, id); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `UPDATE football.product_sync_runs SET status='RUNNING' WHERE run_id=$1`, id); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if _, err := pool.Exec(ctx, `UPDATE football.product_sync_runs SET status='CANCELLED',finished_at=clock_timestamp(),error_message='test cleanup' WHERE run_id=$1`, id); err != nil {
			t.Errorf("test run cleanup: %v", err)
		}
	})
	root := t.TempDir()
	policy := storage.Policy{DatabaseWarningBytes: 1 << 50, DatabaseCriticalBytes: 1 << 51, Roots: []storage.RootPolicy{{Path: root, Subsystem: "test", WarningBytes: 1 << 20, CriticalBytes: 1 << 21}}, ReserveBytes: 1, WarningFreeBytes: 2, MaxEntries: 100, ScanSeconds: 10, IntervalSeconds: 3600, BackupIntervalSeconds: 86400, QuarantineSeconds: 86400}
	encoded, _ := json.Marshal(policy)
	path := filepath.Join(root, "policy.json")
	if err := os.WriteFile(path, encoded, 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("MATCHFORGE_STORAGE_POLICY", path)
	runner := &CommandSyncRunner{pool: pool, ctx: ctx, repoRoot: "../../../..", logger: slog.New(slog.NewTextHandler(io.Discard, nil))}

	return runner, id, policy
}

func TestStorageDatabaseSchedulesUsePersistentAttemptsAndStableIDs(t *testing.T) {
	runner, _, policy := storageDatabaseSetup(t)
	ctx := context.Background()
	request, due, err := runner.storageScheduledRequest(ctx, SyncStorageLifecycle, policy)
	if err != nil || due || request.Type != SyncStorageLifecycle {
		t.Fatalf("duplicate scheduling %v %v", due, err)
	}

	first := storageScheduleID(SyncStorageLifecycle, "42")
	second := storageScheduleID(SyncStorageLifecycle, "42")
	if first != second || !backupRequestID.MatchString(first) {
		t.Fatal("unstable schedule identity")
	}
	if first == storageScheduleID(SyncManualBackup, "42") {
		t.Fatal("schedule identities conflate work types")
	}
}
