package storage

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

// Maintenance cadences. Each produces one read-only report per slot.
const (
	CadenceDaily   = "DAILY"
	CadenceWeekly  = "WEEKLY"
	CadenceMonthly = "MONTHLY"
)

// Finding severities. WARNING and CRITICAL count as alerts.
const (
	SeverityInfo     = "INFO"
	SeverityWarning  = "WARNING"
	SeverityCritical = "CRITICAL"
)

// MaintenancePolicy holds the thresholds of the scheduled reports. Capacity and
// backup thresholds come from the existing policy fields.
type MaintenancePolicy struct {
	GrowthWarningBytesPerDay int64 `json:"growth_warning_bytes_per_day"`
	MaxNonOperatingDatabases int   `json:"max_non_operating_databases"`
	StaleAfterDays           int   `json:"stale_after_days"`
}

func (p MaintenancePolicy) validate() error {
	if p.GrowthWarningBytesPerDay <= 0 || p.MaxNonOperatingDatabases < 0 || p.StaleAfterDays < 7 || p.StaleAfterDays > 365 {
		return errors.New("invalid storage maintenance thresholds")
	}
	return nil
}

// Finding is one result of a maintenance check.
type Finding struct {
	Task     string   `json:"task"`
	Severity string   `json:"severity"`
	Message  string   `json:"message"`
	Count    *int     `json:"count,omitempty"`
	Bytes    *int64   `json:"bytes,omitempty"`
	Items    []string `json:"items,omitempty"`
}

// MaintenanceReport is a stored report.
type MaintenanceReport struct {
	RunID      string          `json:"run_id"`
	Cadence    string          `json:"cadence"`
	Slot       string          `json:"slot"`
	State      string          `json:"state"`
	Measures   json.RawMessage `json:"measures"`
	Findings   []Finding       `json:"findings"`
	Alerts     int             `json:"alerts"`
	Error      *string         `json:"error"`
	StartedAt  time.Time       `json:"started_at"`
	FinishedAt *time.Time      `json:"finished_at"`
}

func maintenanceSlot(cadence string, now time.Time) string {
	now = now.UTC()
	switch cadence {
	case CadenceWeekly:
		year, week := now.ISOWeek()
		return fmt.Sprintf("%d-W%02d", year, week)
	case CadenceMonthly:
		return now.Format("2006-01")
	}
	return now.Format("2006-01-02")
}

// RunMaintenance produces every report whose slot has none yet. The unique
// (cadence, slot) row admits one worker; an interrupted report is retried after
// an hour, at most ten times. Reports never delete anything.
func (m *Manager) RunMaintenance(ctx context.Context) ([]MaintenanceReport, error) {
	if m.Policy == nil || m.Policy.Maintenance == nil {
		return nil, nil
	}
	var ready bool
	if err := m.Pool.QueryRow(ctx, `SELECT to_regclass('football.storage_maintenance_runs') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		return nil, err
	}
	var reports []MaintenanceReport
	for _, cadence := range []string{CadenceDaily, CadenceWeekly, CadenceMonthly} {
		report, claimed, err := m.maintain(ctx, cadence)
		if err != nil {
			return reports, err
		}
		if claimed {
			reports = append(reports, report)
		}
	}
	return reports, nil
}

func (m *Manager) maintain(ctx context.Context, cadence string) (MaintenanceReport, bool, error) {
	now := m.now()
	report := MaintenanceReport{Cadence: cadence, Slot: maintenanceSlot(cadence, now), StartedAt: now}
	claimed, err := m.claimMaintenance(ctx, &report)
	if err != nil || !claimed {
		return report, false, err
	}
	measures, findings, checkErr := m.maintenanceChecks(ctx, cadence, now)
	report.Findings, report.State = findings, "SUCCEEDED"
	for _, f := range findings {
		if f.Severity != SeverityInfo {
			report.Alerts++
		}
	}
	if checkErr != nil {
		message := checkErr.Error()
		report.State, report.Error = "FAILED", &message
		report.Alerts++
	}
	report.Measures, _ = json.Marshal(measures)
	payload, _ := json.Marshal(report.Findings)
	finished := m.now()
	report.FinishedAt = &finished
	_, err = m.Pool.Exec(ctx, `UPDATE football.storage_maintenance_runs SET state=$2,measures=$3,findings=$4,alerts=$5,error=$6,finished_at=$7
 WHERE run_id=$1 AND state='RUNNING'`, report.RunID, report.State, report.Measures, payload, report.Alerts, report.Error, finished)
	return report, true, err
}

func (m *Manager) claimMaintenance(ctx context.Context, report *MaintenanceReport) (bool, error) {
	policy, _ := json.Marshal(m.Policy)
	err := m.Pool.QueryRow(ctx, `INSERT INTO football.storage_maintenance_runs(cadence,slot,policy_sha256,started_at)
 VALUES($1,$2,$3,$4) ON CONFLICT (cadence,slot) DO NOTHING RETURNING run_id::text`,
		report.Cadence, report.Slot, Fingerprint(string(policy)), report.StartedAt).Scan(&report.RunID)
	if err == nil {
		return true, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return false, err
	}
	err = m.Pool.QueryRow(ctx, `UPDATE football.storage_maintenance_runs SET attempts=attempts+1,started_at=$3
 WHERE cadence=$1 AND slot=$2 AND state='RUNNING' AND started_at<$3::timestamptz-interval '1 hour' AND attempts<10
 RETURNING run_id::text`, report.Cadence, report.Slot, report.StartedAt).Scan(&report.RunID)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	return err == nil, err
}

// MaintenanceHistory returns the latest reports, newest first.
func (m *Manager) MaintenanceHistory(ctx context.Context, limit int) ([]MaintenanceReport, error) {
	var ready bool
	if err := m.Pool.QueryRow(ctx, `SELECT to_regclass('football.storage_maintenance_runs') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		return []MaintenanceReport{}, err
	}
	rows, err := m.Pool.Query(ctx, `SELECT run_id::text,cadence,slot,state,measures,findings,alerts,error,started_at,finished_at
 FROM football.storage_maintenance_runs ORDER BY started_at DESC, run_id LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (MaintenanceReport, error) {
		var r MaintenanceReport
		var findings []byte
		err := row.Scan(&r.RunID, &r.Cadence, &r.Slot, &r.State, &r.Measures, &findings, &r.Alerts, &r.Error, &r.StartedAt, &r.FinishedAt)
		if err == nil {
			err = json.Unmarshal(findings, &r.Findings)
		}
		return r, err
	})
}
