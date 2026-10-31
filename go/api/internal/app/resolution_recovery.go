package app

import (
	"context"
	"encoding/json"
	"strings"
	"time"
)

type resolutionRecoveryRunner interface {
	RecoverResolution(context.Context) (bool, error)
}

func (application *App) runResolutionRecoverySchedule(ctx context.Context) {
	var wake <-chan struct{}
	if runner, ok := application.syncRunner.(interface{ ResolutionRecoveryWake() <-chan struct{} }); ok {
		wake = runner.ResolutionRecoveryWake()
	}
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		more, err := application.syncRunner.(resolutionRecoveryRunner).RecoverResolution(ctx)
		if err != nil && ctx.Err() == nil {
			application.logger.Warn("resolution recovery step unavailable", "error", err)
		}
		if more && ctx.Err() == nil {
			continue
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		case <-wake:
		}
	}
}

func (runner *CommandSyncRunner) RecoverResolution(ctx context.Context) (bool, error) {
	owned, err := runner.resolutionOwnedWork(ctx)
	if err != nil {
		return false, err
	}
	if owned == "" {
		return false, nil
	}
	var pending bool
	if err := runner.pool.QueryRow(ctx, `SELECT EXISTS (
  SELECT 1 FROM (`+owned+`) b
  JOIN football.work_items w USING(work_id)
  WHERE w.state IN ('PENDING','RETRY_WAIT') AND w.available_at<=clock_timestamp()
     OR w.state='RUNNING' AND w.lease_until<=clock_timestamp()
 )`).Scan(&pending); err != nil {
		return false, err
	}
	if !pending {
		return false, nil
	}
	result, err := runner.Resolution(ctx, resolutionRequest{Operation: "recover_work"})
	if err != nil {
		return false, err
	}
	if result.StatusCode != 200 {
		return false, errProductUnavailable
	}
	return resolutionRecoveryContinues(result.Data)
}

func (runner *CommandSyncRunner) resolutionOwnedWork(ctx context.Context) (string, error) {
	clauses := []string{}
	for _, table := range []string{"football.resolution_recovery_work", "football.resolution_file_recovery_work", "football.resolution_parity_work"} {
		var ready bool
		if err := runner.pool.QueryRow(ctx, `SELECT to_regclass($1) IS NOT NULL`, table).Scan(&ready); err != nil {
			return "", err
		}
		if ready {
			clauses = append(clauses, "SELECT work_id FROM "+table)
		}
	}
	return strings.Join(clauses, " UNION ALL "), nil
}

func (runner *CommandSyncRunner) ResolutionRecoveryWake() <-chan struct{} {
	return runner.resolutionWake
}

func (runner *CommandSyncRunner) WakeResolutionRecovery() {
	select {
	case runner.resolutionWake <- struct{}{}:
	default:
	}
}

func resolutionRecoveryContinues(data json.RawMessage) (bool, error) {
	var outcome struct {
		Status string `json:"status"`
	}
	if json.Unmarshal(data, &outcome) != nil {
		return false, errProductUnavailable
	}
	switch outcome.Status {
	case "PROCESSED", "PROCESSED_WITH_BLOCKERS":
		return true, nil
	case "IDLE", "BUSY", "RETRY_WAIT", "BLOCKED", "LEASE_LOST":
		return false, nil
	default:
		return false, errProductUnavailable
	}
}

func (application *App) startResolutionRecovery(ctx context.Context) func() {
	if _, ok := application.syncRunner.(resolutionRecoveryRunner); !ok {
		return func() {}
	}
	owned, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	go func() { defer close(done); application.runResolutionRecoverySchedule(owned) }()
	return func() {
		cancel()
		select {
		case <-done:
		case <-time.After(application.config.ShutdownTimeout):
			application.logger.Warn("resolution recovery shutdown timed out")
		}
	}
}
