package storage

import (
	"context"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestMaintenanceSlotsAndPolicy(t *testing.T) {
	at := time.Date(2026, 12, 31, 23, 0, 0, 0, time.UTC)
	expect(t, maintenanceSlot(CadenceDaily, at) == "2026-12-31", "daily slot")
	expect(t, maintenanceSlot(CadenceWeekly, at) == "2026-W53", "weekly slot %s", maintenanceSlot(CadenceWeekly, at))
	expect(t, maintenanceSlot(CadenceMonthly, at) == "2026-12", "monthly slot")
	valid := MaintenancePolicy{GrowthWarningBytesPerDay: 1 << 30, MaxNonOperatingDatabases: 5, StaleAfterDays: 30}
	expect(t, valid.validate() == nil, "valid thresholds rejected")
	for _, bad := range []MaintenancePolicy{{GrowthWarningBytesPerDay: 0, StaleAfterDays: 30}, {GrowthWarningBytesPerDay: 1, StaleAfterDays: 6}, {GrowthWarningBytesPerDay: 1, StaleAfterDays: 30, MaxNonOperatingDatabases: -1}} {
		expect(t, bad.validate() != nil, "invalid thresholds accepted: %+v", bad)
	}
}

func TestBackupFindingSeverity(t *testing.T) {
	now := time.Date(2026, 11, 13, 0, 0, 0, 0, time.UTC)
	ok := func(verifiedAt time.Time) backupRun {
		return backupRun{Status: "SUCCEEDED", Summary: map[string]any{"verified": true, "status": "VERIFIED_GOVERNED_SCOPE", "verified_at": verifiedAt.Format(time.RFC3339Nano)}}
	}
	interval := 30 * 24 * time.Hour
	expect(t, backupFinding(nil, now, interval).Severity == SeverityCritical, "no backup must be critical")
	expect(t, backupFinding([]backupRun{ok(now.Add(-time.Hour))}, now, interval).Severity == SeverityInfo, "fresh backup is healthy")
	expect(t, backupFinding([]backupRun{ok(now.Add(-31 * 24 * time.Hour))}, now, interval).Severity == SeverityWarning, "overdue backup must warn")
	failed := backupRun{Status: "FAILED", Summary: map[string]any{}}
	f := backupFinding([]backupRun{failed, ok(now.Add(-time.Hour))}, now, interval)
	expect(t, f.Severity == SeverityWarning && strings.Contains(f.Message, "1 backup attempt"), "failure after success must warn: %+v", f)
	unverified := backupRun{Status: "SUCCEEDED", Summary: map[string]any{"verified": false}}
	expect(t, backupFinding([]backupRun{unverified}, now, interval).Severity == SeverityCritical, "an unverified capture is not a backup")
}

func TestDatabaseMaintenanceReportsOncePerSlotAndRetriesInterrupted(t *testing.T) {
	pool := databasePool(t)
	ctx := context.Background()
	// Advancing one day must leave the ISO week and month unchanged.
	now := time.Date(2400, time.January, 11, 12, 0, 0, 0, time.UTC)
	policy := &Policy{MaxEntries: 100_000, ReserveBytes: 1, WarningFreeBytes: 2, DatabaseWarningBytes: 1 << 50, DatabaseCriticalBytes: 1 << 51,
		BackupIntervalSeconds: 2592000, Maintenance: &MaintenancePolicy{GrowthWarningBytesPerDay: 1 << 40, MaxNonOperatingDatabases: 0, StaleAfterDays: 30}}
	manager := func() *Manager { return &Manager{Pool: pool, Policy: policy, Now: func() time.Time { return now }} }
	var wg sync.WaitGroup
	counts := make([]int, 3)
	for i := range counts {
		wg.Add(1)
		go func() {
			defer wg.Done()
			reports, err := manager().RunMaintenance(ctx)
			if err == nil {
				counts[i] = len(reports)
			}
		}()
	}
	wg.Wait()
	expect(t, counts[0]+counts[1]+counts[2] == 3, "each cadence must report exactly once: %v", counts)
	reports, err := manager().MaintenanceHistory(ctx, 10)
	must(t, err)
	tasks := map[string]Finding{}
	for _, r := range reports {
		expect(t, r.State == "SUCCEEDED", "report %s %s: %v", r.Cadence, r.State, r.Error)
		for _, f := range r.Findings {
			tasks[f.Task] = f
		}
	}
	for _, task := range []string{"capacity", "growth", "backup", "stale_artifacts", "savings", "recovery_integrity", "redundant_databases"} {
		_, ok := tasks[task]
		expect(t, ok, "missing %s finding: %v", task, tasks)
	}
	expect(t, tasks["backup"].Severity == SeverityCritical, "a database without verified backups must alert: %+v", tasks["backup"])
	_, err = pool.Exec(ctx, `UPDATE football.storage_maintenance_runs SET alerts=0 WHERE state='SUCCEEDED'`)
	expect(t, err != nil, "a final report was rewritten")

	// An interrupted report is retried after an hour; a second day measures growth.
	now = now.Add(24 * time.Hour)
	_, err = pool.Exec(ctx, `INSERT INTO football.storage_maintenance_runs(cadence,slot,policy_sha256,started_at) VALUES('DAILY',$1,$2,$3)`,
		maintenanceSlot(CadenceDaily, now), strings.Repeat("a", 64), now.Add(-2*time.Hour))
	must(t, err)
	reports, err = manager().RunMaintenance(ctx)
	must(t, err)
	expect(t, len(reports) == 1 && reports[0].Cadence == CadenceDaily, "interrupted daily report not retried: %+v", reports)
	growth := false
	for _, f := range reports[0].Findings {
		growth = growth || (f.Task == "growth" && f.Bytes != nil)
	}
	expect(t, growth, "second daily report must measure growth: %+v", reports[0].Findings)
}
