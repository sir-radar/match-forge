package app

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"
)

func TestBackupDatabaseContracts(t *testing.T) {
	pool := servingDatabasePool(t)
	ctx := context.Background()
	runner := &CommandSyncRunner{pool: pool, logger: slog.New(slog.NewTextHandler(io.Discard, nil))}
	var ready bool
	if err := pool.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM public.goose_db_version WHERE version_id=202611100300 AND is_applied)").Scan(&ready); err != nil {
		t.Fatal(err)
	}
	if !ready {
		view, err := runner.BackupView(ctx, false)
		if err != nil || view.Availability.State != "MIGRATION_PENDING" || view.SafeToEject {
			t.Fatalf("pending schema view: %+v %v", view, err)
		}
		return
	}
	verifiedAt := time.Now().UTC().Add(-31 * 24 * time.Hour)
	first := backupDatabaseRun(t, runner, "SUCCEEDED", map[string]any{"verified": true, "verified_at": verifiedAt.Format(time.RFC3339Nano), "captured_at": verifiedAt.Add(-time.Minute).Format(time.RFC3339Nano)})
	failed := backupDatabaseRun(t, runner, "FAILED", map[string]any{"verified": false})
	backupReminderAssertions(t, runner, first)
	backupHistoryAssertions(t, runner)
	backupLegacyAssertions(t, runner)
	backupIdentityAssertions(t, runner, first, failed)
}

func backupReminderAssertions(t *testing.T, runner *CommandSyncRunner, first string) {
	t.Helper()
	ctx := context.Background()
	view := BackupView{ReminderDue: true}
	if err := runner.backupReminder(ctx, &view, time.Now()); err != nil {
		t.Fatal(err)
	}
	if view.LastVerified == nil || view.LastVerified.ID != first || !view.ReminderDue {
		t.Fatal("failed attempt replaced verified recovery point")
	}
}

func backupHistoryAssertions(t *testing.T, runner *CommandSyncRunner) {
	t.Helper()
	ctx := context.Background()
	runs, active, err := runner.backupHistory(ctx)
	if err != nil || active || len(runs) < 2 {
		t.Fatalf("backup history: %d %v %v", len(runs), active, err)
	}
	for _, run := range runs {
		if run.LogPath != nil {
			t.Fatal("local log path leaked")
		}
	}
}

func backupLegacyAssertions(t *testing.T, runner *CommandSyncRunner) {
	t.Helper()
	ctx := context.Background()
	legacy, err := runner.List(ctx)
	if err != nil {
		t.Fatal(err)
	}
	for _, run := range legacy {
		if run.Type == SyncManualBackup {
			t.Fatal("new backup enum leaked into legacy sync list")
		}
	}
}

func backupIdentityAssertions(t *testing.T, runner *CommandSyncRunner, first, failed string) {
	t.Helper()
	ctx := context.Background()
	prior, err := runner.enqueueOrJoin(ctx, SyncRequest{Type: SyncManualBackup}, first, "unused", nil, []byte(`{}`))
	if err != nil || prior == nil || prior.ID != first {
		t.Fatal("same request did not join persisted backup")
	}
	if _, err = runner.Retry(ctx, failed); !errors.Is(err, errSyncRunNotRetryable) {
		t.Fatal("generic retry bypassed manual preflight")
	}
}

func backupDatabaseRun(t *testing.T, runner *CommandSyncRunner, status string, summary map[string]any) string {
	t.Helper()
	id, err := newUUID()
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	_, err = runner.pool.Exec(ctx, `INSERT INTO football.product_sync_runs(run_id,sync_type,status,worker_id,heartbeat_at,log_path)
        VALUES ($1::uuid,'MANUAL_BACKUP','QUEUED',$1::text,clock_timestamp(),'/private/example.log')`, id)
	if err != nil {
		t.Fatal(err)
	}
	if !runner.markRunning(ctx, id) {
		t.Fatal("manual work not claimed")
	}
	payload, err := json.Marshal(summary)
	if err != nil {
		t.Fatal(err)
	}
	var message *string
	if status == "FAILED" {
		text := "private failure"
		message = &text
	}
	_, err = runner.pool.Exec(ctx, `UPDATE football.product_sync_runs SET status=$2,summary=$3::jsonb,
        finished_at=clock_timestamp(),error_message=$4 WHERE run_id=$1`, id, status, payload, message)
	if err != nil {
		t.Fatal(err)
	}
	return id
}
