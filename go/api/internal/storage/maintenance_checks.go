package storage

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
)

type maintenanceContext struct {
	m        *Manager
	now      time.Time
	inv      Inventory
	findings []Finding
}

func (c *maintenanceContext) add(f Finding) { c.findings = append(c.findings, f) }

func intPtr(v int) *int       { return &v }
func bytesPtr(v int64) *int64 { return &v }

// maintenanceChecks runs the read-only checks of one cadence.
func (m *Manager) maintenanceChecks(ctx context.Context, cadence string, now time.Time) (map[string]any, []Finding, error) {
	inv, err := m.Inventory(ctx)
	if err != nil {
		return map[string]any{}, []Finding{}, err
	}
	c := &maintenanceContext{m: m, now: now, inv: inv, findings: []Finding{}}
	measures := map[string]any{"observed_at": now, "postgres_bytes": inv.Summary.PostgresBytes,
		"host_free_bytes": inv.Summary.HostFreeBytes, "host_total_bytes": inv.Summary.HostTotalBytes, "database_count": inv.Summary.DatabaseCount}
	var checks []func(context.Context) error
	switch cadence {
	case CadenceDaily:
		checks = []func(context.Context) error{c.capacity, c.growth, c.abandoned, c.backupHealth}
	case CadenceWeekly:
		checks = []func(context.Context) error{c.staleArtifacts, c.savings}
	case CadenceMonthly:
		checks = []func(context.Context) error{c.recoveryIntegrity, c.redundantDatabases}
	}
	var failures []error
	for _, check := range checks {
		if err := check(ctx); err != nil {
			failures = append(failures, err)
		}
	}
	return measures, c.findings, errors.Join(failures...)
}

// capacity compares host free space with the policy's warning and recovery reserve.
func (c *maintenanceContext) capacity(context.Context) error {
	free := c.inv.Summary.HostFreeBytes
	if free == nil {
		c.add(Finding{Task: "capacity", Severity: SeverityWarning, Message: "host free space could not be measured"})
		return nil
	}
	f := Finding{Task: "capacity", Severity: SeverityInfo, Bytes: free, Message: "host free space is above the warning threshold"}
	switch {
	case *free < c.m.Policy.ReserveBytes:
		f.Severity, f.Message = SeverityCritical, "host free space is below the recovery reserve"
	case *free < c.m.Policy.WarningFreeBytes:
		f.Severity, f.Message = SeverityWarning, "host free space is below the warning threshold"
	}
	c.add(f)
	if c.inv.Summary.PostgresBytes > c.m.Policy.DatabaseCriticalBytes {
		c.add(Finding{Task: "capacity", Severity: SeverityCritical, Bytes: bytesPtr(c.inv.Summary.PostgresBytes), Message: "PostgreSQL cluster exceeds its critical budget"})
	} else if c.inv.Summary.PostgresBytes > c.m.Policy.DatabaseWarningBytes {
		c.add(Finding{Task: "capacity", Severity: SeverityWarning, Bytes: bytesPtr(c.inv.Summary.PostgresBytes), Message: "PostgreSQL cluster exceeds its warning budget"})
	}
	return nil
}

// growth compares with the previous successful daily report.
func (c *maintenanceContext) growth(ctx context.Context) error {
	var raw []byte
	err := c.m.Pool.QueryRow(ctx, `SELECT measures FROM football.storage_maintenance_runs WHERE cadence='DAILY' AND state='SUCCEEDED'
 ORDER BY started_at DESC LIMIT 1`).Scan(&raw)
	if errors.Is(err, pgx.ErrNoRows) {
		c.add(Finding{Task: "growth", Severity: SeverityInfo, Message: "first daily report; growth is measured from the next one"})
		return nil
	}
	if err != nil {
		return err
	}
	var previous struct {
		ObservedAt    time.Time `json:"observed_at"`
		PostgresBytes int64     `json:"postgres_bytes"`
		HostFree      *int64    `json:"host_free_bytes"`
	}
	if err = json.Unmarshal(raw, &previous); err != nil {
		return err
	}
	days := c.now.Sub(previous.ObservedAt).Hours() / 24
	if days <= 0 {
		return nil
	}
	growth := int64(float64(c.inv.Summary.PostgresBytes-previous.PostgresBytes) / days)
	if previous.HostFree != nil && c.inv.Summary.HostFreeBytes != nil {
		if hostGrowth := int64(float64(*previous.HostFree-*c.inv.Summary.HostFreeBytes) / days); hostGrowth > growth {
			growth = hostGrowth
		}
	}
	f := Finding{Task: "growth", Severity: SeverityInfo, Bytes: bytesPtr(growth), Message: "storage growth per day is within the threshold"}
	if growth > c.m.Policy.Maintenance.GrowthWarningBytesPerDay {
		f.Severity, f.Message = SeverityWarning, "abnormal storage growth per day"
	}
	c.add(f)
	return nil
}

// abandoned finds temporary resources that need attention: unregistered test
// databases, blocked lifecycle resources and more non-operating databases than
// the policy allows.
func (c *maintenanceContext) abandoned(ctx context.Context) error {
	unregistered, err := c.m.unregisteredTests(ctx)
	if err != nil {
		return err
	}
	if len(unregistered) > 0 {
		var names []string
		for _, u := range unregistered {
			names = append(names, u.Name)
		}
		c.add(Finding{Task: "abandoned", Severity: SeverityWarning, Count: intPtr(len(names)), Items: firstN(names, 20),
			Message: "test databases without a creation record need an owner disposition"})
	}
	blocked, err := lifecycleRecords(ctx, c.m.Pool, `state='BLOCKED'`)
	if err != nil {
		return err
	}
	if len(blocked) > 0 {
		var items []string
		for _, r := range blocked {
			items = append(items, r.Location+": "+firstOr(r.Blockers, "blocked"))
		}
		sort.Strings(items)
		c.add(Finding{Task: "abandoned", Severity: SeverityWarning, Count: intPtr(len(items)), Items: firstN(items, 20),
			Message: "completed resources are blocked from five-hour cleanup"})
	}
	other := c.inv.Summary.DatabaseCount - 1
	if other > c.m.Policy.Maintenance.MaxNonOperatingDatabases {
		c.add(Finding{Task: "abandoned", Severity: SeverityWarning, Count: intPtr(other), Bytes: bytesPtr(c.inv.Summary.OtherDatabaseBytes),
			Message: fmt.Sprintf("%d non-operating databases exceed the limit of %d", other, c.m.Policy.Maintenance.MaxNonOperatingDatabases)})
	}
	return nil
}

func firstOr(values []string, fallback string) string {
	if len(values) == 0 {
		return fallback
	}
	return values[0]
}

type backupRun struct {
	Status     string
	Summary    map[string]any
	FinishedAt *time.Time
}

// backupHealth requires a verified backup within the policy interval and reports
// a failed attempt after the last success.
func (c *maintenanceContext) backupHealth(ctx context.Context) error {
	rows, err := c.m.Pool.Query(ctx, `SELECT status,coalesce(summary,'{}'::jsonb),finished_at FROM football.product_sync_runs
 WHERE sync_type='MANUAL_BACKUP' AND status IN ('SUCCEEDED','FAILED') ORDER BY requested_at DESC LIMIT 20`)
	if err != nil {
		return err
	}
	runs, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (backupRun, error) {
		var r backupRun
		return r, row.Scan(&r.Status, &r.Summary, &r.FinishedAt)
	})
	if err != nil {
		return err
	}
	c.add(backupFinding(runs, c.now, time.Duration(c.m.Policy.BackupIntervalSeconds)*time.Second))
	return nil
}

func backupFinding(runs []backupRun, now time.Time, interval time.Duration) Finding {
	failedSince := 0
	for _, r := range runs {
		verified, _ := r.Summary["verified"].(bool)
		if r.Status != "SUCCEEDED" || !verified {
			failedSince++
			continue
		}
		status, _ := r.Summary["status"].(string)
		at, _ := time.Parse(time.RFC3339Nano, fmt.Sprint(r.Summary["verified_at"]))
		f := Finding{Task: "backup", Severity: SeverityInfo, Message: "latest verified backup " + status + " at " + at.UTC().Format(time.RFC3339)}
		switch {
		case at.IsZero() || now.Sub(at) > interval:
			f.Severity, f.Message = SeverityWarning, "latest verified backup is older than the backup interval ("+status+")"
		case failedSince > 0:
			f.Severity, f.Message = SeverityWarning, fmt.Sprintf("%d backup attempt(s) failed after the latest verified backup", failedSince)
		}
		return f
	}
	return Finding{Task: "backup", Severity: SeverityCritical, Message: "no verified backup found"}
}

// staleArtifacts lists managed-root children unchanged for longer than the
// threshold. Deletion stays with the approved automatic rules or the owner.
func (c *maintenanceContext) staleArtifacts(context.Context) error {
	limit := time.Duration(c.m.Policy.Maintenance.StaleAfterDays) * 24 * time.Hour
	var items []string
	var total int64
	for _, r := range c.inv.Resources {
		modified, ok := r.Details["modified_at"].(time.Time)
		if r.Backend != "filesystem" || !ok || c.now.Sub(modified) < limit {
			continue
		}
		total += valueOr(r.AllocatedBytes)
		items = append(items, fmt.Sprintf("%s (%s, %d bytes)", r.Location, r.Classification, valueOr(r.AllocatedBytes)))
	}
	sort.Strings(items)
	c.add(Finding{Task: "stale_artifacts", Severity: SeverityInfo, Count: intPtr(len(items)), Bytes: bytesPtr(total), Items: firstN(items, 20),
		Message: fmt.Sprintf("managed logs, caches and generated artifacts unchanged for %d days", c.m.Policy.Maintenance.StaleAfterDays)})
	return nil
}

// savings reports verified reclaimed bytes over the last week.
func (c *maintenanceContext) savings(ctx context.Context) error {
	var operations int
	var reclaimed int64
	err := c.m.Pool.QueryRow(ctx, `SELECT count(*),coalesce(sum(reclaimed_bytes),0)::bigint FROM football.storage_operations
 WHERE state='SUCCEEDED' AND action IN ('DELETE','PURGE') AND finished_at>$1`, c.now.Add(-7*24*time.Hour)).Scan(&operations, &reclaimed)
	if err != nil {
		return err
	}
	c.add(Finding{Task: "savings", Severity: SeverityInfo, Count: intPtr(operations), Bytes: bytesPtr(reclaimed),
		Message: "verified storage reclaimed in the last seven days"})
	return nil
}

// recoveryIntegrity reviews verified backups over the last month. FULL_RECOVERY
// and VERIFIED_GOVERNED_SCOPE are reported as recorded, never upgraded.
func (c *maintenanceContext) recoveryIntegrity(ctx context.Context) error {
	var verified int
	var statuses []string
	err := c.m.Pool.QueryRow(ctx, `SELECT count(*),coalesce(array_agg(DISTINCT summary->>'status') FILTER (WHERE summary->>'status' IS NOT NULL),'{}')
 FROM football.product_sync_runs WHERE sync_type='MANUAL_BACKUP' AND status='SUCCEEDED' AND (summary->>'verified')::boolean
 AND finished_at>$1`, c.now.Add(-31*24*time.Hour)).Scan(&verified, &statuses)
	if err != nil {
		return err
	}
	f := Finding{Task: "recovery_integrity", Severity: SeverityInfo, Count: intPtr(verified), Items: statuses,
		Message: "verified backups with isolated restore in the last month"}
	if verified == 0 {
		f.Severity, f.Message = SeverityWarning, "no verified backup with isolated restore in the last month"
	}
	c.add(f)
	return nil
}

// redundantDatabases lists non-operating databases and what their review needs.
func (c *maintenanceContext) redundantDatabases(context.Context) error {
	var items []string
	for _, r := range c.inv.Resources {
		if r.Backend != "postgres" || r.Role == "AUTHORITATIVE_OPERATING_DATABASE" || r.Role == "SYSTEM_DATABASE" {
			continue
		}
		state := "not compared"
		if r.Evidence != nil {
			state = r.Evidence.Finding
			if !r.Evidence.Current {
				state += " (stale)"
			}
		}
		if r.Disposition != nil {
			state += "; disposition " + r.Disposition.Disposition
		}
		items = append(items, fmt.Sprintf("%s: %s, %d bytes, %s", r.Name, r.Classification, valueOr(r.AllocatedBytes), state))
	}
	sort.Strings(items)
	c.add(Finding{Task: "redundant_databases", Severity: SeverityInfo, Count: intPtr(len(items)), Bytes: bytesPtr(c.inv.Summary.OtherDatabaseBytes),
		Items: firstN(items, 20), Message: "non-operating databases and their review state"})
	return nil
}
