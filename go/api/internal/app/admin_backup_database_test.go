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
	first := backupDatabaseRun(t, runner, "SUCCEEDED", verifiedBackupSummary(backupFullRecovery, verifiedAt))
	recoverable := backupDatabaseRun(t, runner, "SUCCEEDED", verifiedBackupSummary(backupRecoverableOnly, time.Now().Add(-time.Minute)))
	failed := backupDatabaseRun(t, runner, "FAILED", map[string]any{"verified": false})
	backupReminderAssertions(t, runner, first, recoverable)
	backupPriorReceiptAssertions(t, runner, first)
	backupHistoryAssertions(t, runner)
	backupLegacyAssertions(t, runner)
	backupIdentityAssertions(t, runner, first, failed)
}

func backupReminderAssertions(t *testing.T, runner *CommandSyncRunner, first, recoverable string) {
	t.Helper()
	ctx := context.Background()
	for _, check := range []struct {
		scope string
		runID string
		due   bool
	}{{backupFullRecovery, first, true}, {backupRecoverableOnly, recoverable, false}} {
		view := BackupView{Availability: BackupAvailability{Scope: check.scope}, ReminderDue: true}
		if err := runner.backupReminder(ctx, &view, time.Now()); err != nil {
			t.Fatal(err)
		}
		if view.LastVerified == nil || view.LastVerified.ID != check.runID || view.ReminderDue != check.due {
			t.Fatalf("wrong reminder for %s", check.scope)
		}
		if view.LastFullRecovery == nil || view.LastFullRecovery.ID != first {
			t.Fatal("recoverable success changed the full recovery record")
		}
	}
}

func backupPriorReceiptAssertions(t *testing.T, runner *CommandSyncRunner, first string) {
	t.Helper()
	ctx := context.Background()
	now := time.Now()
	payload, err := json.Marshal(verifiedBackupSummary(backupRecoverableOnly, now))
	if err != nil {
		t.Fatal(err)
	}
	var prior backupPoint
	if err = json.Unmarshal(payload, &prior); err != nil || !prior.valid() {
		t.Fatalf("invalid prior receipt: %v", err)
	}
	priorView := BackupView{Availability: BackupAvailability{Scope: backupRecoverableOnly, PriorVerified: &prior}}
	if err = runner.backupReminder(ctx, &priorView, now); err != nil {
		t.Fatal(err)
	}
	if priorView.LastVerified != nil || priorView.NextDueAt == nil ||
		!priorView.NextDueAt.Equal(now.Add(30*24*time.Hour)) ||
		priorView.LastFullRecovery == nil || priorView.LastFullRecovery.ID != first {
		t.Fatal("newer verified operator receipt did not update only the matching policy reminder")
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
	prior, err := runner.enqueueOrJoin(ctx, SyncRequest{Type: SyncManualBackup, BackupScope: backupFullRecovery}, first, "unused", nil, []byte(`{}`))
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
	_, err = runner.pool.Exec(ctx, `INSERT INTO football.product_sync_runs(run_id,sync_type,status,worker_id,heartbeat_at,log_path,parameters)
        VALUES ($1::uuid,'MANUAL_BACKUP','QUEUED',$1::text,clock_timestamp(),'/private/example.log',jsonb_build_object('scope',$2::text))`, id, stringParameter(summary, "scope"))
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
