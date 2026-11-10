package app

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"time"

	"github.com/jackc/pgx/v5"
)

var backupRequestID = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
var backupSnapshotID = regexp.MustCompile(`^[0-9a-f]{64}$`)

type BackupDrive struct {
	VolumeUUID    string `json:"volume_uuid"`
	Filesystem    string `json:"filesystem"`
	Encrypted     bool   `json:"filesystem_encrypted"`
	FreeBytes     int64  `json:"free_bytes"`
	CapacityBytes int64  `json:"capacity_bytes"`
}

type BackupAvailability struct {
	State                 string       `json:"state"`
	Message               string       `json:"message"`
	Drive                 *BackupDrive `json:"drive,omitempty"`
	RepositoryUnlocked    bool         `json:"repository_unlocked"`
	ReferencedFiles       int64        `json:"referenced_files"`
	ReferencedBytes       int64        `json:"referenced_bytes"`
	EstimatedStagingBytes int64        `json:"estimated_staging_bytes"`
	Impact                string       `json:"impact"`
}

type BackupView struct {
	Availability     BackupAvailability `json:"availability"`
	Runs             []SyncRun          `json:"runs"`
	LastVerified     *SyncRun           `json:"last_verified"`
	NextDueAt        *time.Time         `json:"next_due_at"`
	BackupAgeSeconds *int64             `json:"backup_age_seconds"`
	ReminderDue      bool               `json:"reminder_due"`
	SafeToEject      bool               `json:"safe_to_eject"`
}

type backupInspector interface {
	BackupView(context.Context, bool) (BackupView, error)
}

func (runner *CommandSyncRunner) BackupView(ctx context.Context, preview bool) (BackupView, error) {
	view := BackupView{Runs: []SyncRun{}, ReminderDue: true}
	availability, err := runner.inspectBackup(ctx, preview)
	if err != nil {
		return view, err
	}
	view.Availability = availability
	runs, active, err := runner.backupHistory(ctx)
	if err != nil {
		return view, err
	}
	view.Runs = runs
	if err = runner.backupReminder(ctx, &view, time.Now()); err != nil {
		return view, err
	}
	view.SafeToEject = !active && availability.State == "READY" && availability.RepositoryUnlocked
	return view, nil
}

func (runner *CommandSyncRunner) inspectBackup(ctx context.Context, preview bool) (BackupAvailability, error) {
	var result BackupAvailability
	var schemaReady bool
	if err := runner.pool.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM public.goose_db_version WHERE version_id=202611100300 AND is_applied)").Scan(&schemaReady); err != nil {
		return result, err
	}
	if !schemaReady {
		return BackupAvailability{State: "MIGRATION_PENDING", Message: "Backup migration is pending separate operating approval. Normal MatchForge operation is available."}, nil
	}
	action := "status"
	if preview {
		action = "preview"
	}
	command := exec.CommandContext(ctx, ".tools/bin/uv", "run", "--locked", "python", "-m", "scripts.manual_backup", action)
	command.Dir, command.Env = runner.repoRoot, os.Environ()
	isolateCommand(command)
	output, err := command.Output()
	if err != nil {
		return result, err
	}
	err = json.Unmarshal(output, &result)
	return result, err
}

func (runner *CommandSyncRunner) backupHistory(ctx context.Context) ([]SyncRun, bool, error) {
	runs := []SyncRun{}
	rows, err := runner.pool.Query(ctx, syncRunSelect+" WHERE sync_type='MANUAL_BACKUP' ORDER BY requested_at DESC,run_id DESC LIMIT 20")
	if err != nil {
		return runs, false, err
	}
	defer rows.Close()
	active := false
	for rows.Next() {
		run, scanErr := scanSyncRun(rows)
		if scanErr != nil {
			return runs, active, scanErr
		}
		run.LogPath = nil
		active = active || run.Status == "QUEUED" || run.Status == "RUNNING"
		if run.ErrorMessage != nil {
			message := "Backup did not finish. Review preflight and retry manually."
			run.ErrorMessage = &message
		}
		runs = append(runs, run)
	}
	return runs, active, rows.Err()
}

func (runner *CommandSyncRunner) backupReminder(ctx context.Context, view *BackupView, now time.Time) error {
	last, err := scanSyncRun(runner.pool.QueryRow(ctx, syncRunSelect+" WHERE sync_type='MANUAL_BACKUP' AND status='SUCCEEDED' AND summary->>'verified'='true' ORDER BY finished_at DESC,run_id DESC LIMIT 1"))
	if errors.Is(err, pgx.ErrNoRows) {
		return nil
	}
	if err != nil {
		return err
	}
	last.LogPath = nil
	return applyBackupReminder(view, last, now)
}

func applyBackupReminder(view *BackupView, last SyncRun, now time.Time) error {
	verifiedAt, ok := last.Summary["verified_at"].(string)
	capturedAt, _ := last.Summary["captured_at"].(string)
	captured, timestamp, err := verificationTimes(verifiedAt, capturedAt)
	if !ok || err != nil || timestamp.After(now) {
		return errWorkControlConflict
	}
	view.LastVerified = &last
	next := timestamp.Add(30 * 24 * time.Hour)
	age := int64(now.Sub(captured).Seconds())
	view.NextDueAt, view.BackupAgeSeconds = &next, &age
	view.ReminderDue = !now.Before(next)
	return nil
}

func verificationTimes(verifiedAt, capturedAt string) (time.Time, time.Time, error) {
	verified, err := time.Parse(time.RFC3339Nano, verifiedAt)
	if err != nil {
		return time.Time{}, time.Time{}, err
	}
	captured, err := time.Parse(time.RFC3339Nano, capturedAt)
	if err != nil || captured.After(verified) {
		return time.Time{}, time.Time{}, errWorkControlConflict
	}
	return captured, verified, nil
}

func (application *App) backupView(preview bool) http.HandlerFunc {
	return func(response http.ResponseWriter, request *http.Request) {
		inspector, ok := application.syncRunner.(backupInspector)
		if !ok {
			application.publicError(response, http.StatusServiceUnavailable, "backup inspection unavailable")
			return
		}
		view, err := inspector.BackupView(request.Context(), preview)
		if err != nil {
			application.publicError(response, http.StatusServiceUnavailable, "backup inspection failed; retry after checking local services")
			return
		}
		application.writeJSON(response, http.StatusOK, view)
	}
}

func (application *App) startBackup(response http.ResponseWriter, request *http.Request) {
	requestID, decodeErr := decodeBackupRequest(response, request)
	if decodeErr != nil {
		application.publicError(response, http.StatusBadRequest, "confirmed backup and UUID request_id required")
		return
	}
	if previous, err := application.syncRunner.Get(request.Context(), requestID); err == nil {
		if previous.Type != SyncManualBackup {
			application.publicError(response, http.StatusConflict, "request ID already belongs to another operation")
			return
		}
		previous.LogPath = nil
		application.writeJSON(response, http.StatusAccepted, previous)
		return
	}
	inspector, ok := application.syncRunner.(backupInspector)
	if !ok {
		application.publicError(response, http.StatusServiceUnavailable, "backup unavailable")
		return
	}
	view, err := inspector.BackupView(request.Context(), true)
	if err != nil {
		application.publicError(response, http.StatusServiceUnavailable, "backup preflight failed")
		return
	}
	if view.Availability.State != "READY" {
		application.writeJSON(response, http.StatusConflict, map[string]string{"error": view.Availability.Message})
		return
	}
	run, err := application.syncRunner.Start(request.Context(), SyncRequest{Type: SyncManualBackup, ManualRequestID: requestID})
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	run.LogPath = nil
	application.writeJSON(response, http.StatusAccepted, run)
}

func decodeBackupRequest(response http.ResponseWriter, request *http.Request) (string, error) {
	var input struct {
		RequestID string `json:"request_id"`
		Confirmed bool   `json:"confirmed"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 4096))
	decoder.DisallowUnknownFields()
	var trailing any
	if decoder.Decode(&input) != nil || decoder.Decode(&trailing) != io.EOF || !input.Confirmed || !backupRequestID.MatchString(input.RequestID) {
		return "", errWorkControlConflict
	}
	return input.RequestID, nil
}

// Inspect JSON only; backup success requires completed verification, not an exit code.
func validBackupSummary(payload []byte) bool {
	var summary struct {
		Status     string `json:"status"`
		Verified   bool   `json:"verified"`
		SnapshotID string `json:"snapshot_id"`
		VerifiedAt string `json:"verified_at"`
		CapturedAt string `json:"captured_at"`
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	if decoder.Decode(&summary) != nil {
		return false
	}
	_, _, err := verificationTimes(summary.VerifiedAt, summary.CapturedAt)
	return err == nil && summary.Status == "VERIFIED" && summary.Verified && backupSnapshotID.MatchString(summary.SnapshotID)
}
