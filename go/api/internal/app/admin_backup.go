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

const (
	backupFullRecovery    = "FULL_RECOVERY"
	backupRecoverableOnly = "RECOVERABLE_ONLY"
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
	Scope                 string       `json:"scope,omitempty"`
	KnownUnavailable      *int         `json:"known_unavailable_dependencies"`
	PriorVerified         *backupPoint `json:"prior_verified"`
	UnavailableSHA256     *string      `json:"unavailable_sha256"`
	State                 string       `json:"state"`
	Message               string       `json:"message"`
	Drive                 *BackupDrive `json:"drive,omitempty"`
	RepositoryUnlocked    bool         `json:"repository_unlocked"`
	ReferencedFiles       int64        `json:"referenced_files"`
	ReferencedBytes       int64        `json:"referenced_bytes"`
	EstimatedStagingBytes int64        `json:"estimated_staging_bytes"`
	Impact                string       `json:"impact"`
}

type backupPoint struct {
	backupVerification
	LogicalBytes      int64  `json:"logical_bytes"`
	PackedBytes       int64  `json:"data_added_packed_bytes"`
	VolumeChangeBytes *int64 `json:"volume_free_space_change_bytes,omitempty"`
	RepositoryBytes   int64  `json:"repository_file_bytes"`
}

type BackupView struct {
	Availability     BackupAvailability `json:"availability"`
	Runs             []SyncRun          `json:"runs"`
	LastVerified     *SyncRun           `json:"last_verified"`
	NextDueAt        *time.Time         `json:"next_due_at"`
	BackupAgeSeconds *int64             `json:"backup_age_seconds"`
	LastFullRecovery *SyncRun           `json:"last_full_recovery"`
	ReminderDue      bool               `json:"reminder_due"`
	SafeToEject      bool               `json:"safe_to_eject"`
}

type backupInspector interface {
	BackupView(context.Context, bool) (BackupView, error)
}

func (runner *CommandSyncRunner) BackupView(ctx context.Context, preview bool) (BackupView, error) {
	view := BackupView{Runs: []SyncRun{}}
	availability, err := runner.inspectBackup(ctx, preview)
	if err != nil {
		return view, err
	}
	view.Availability = availability
	view.ReminderDue = availability.Scope != ""
	runs, active, err := runner.backupHistory(ctx)
	if err != nil {
		return view, err
	}
	view.Runs = runs
	if err = runner.backupReminder(ctx, &view, time.Now()); err != nil {
		return view, err
	}
	view.SafeToEject = !active && availability.State == "READY" && availability.RepositoryUnlocked
	if preview && active {
		view.Availability.State = "IN_PROGRESS"
		view.Availability.Message = "Wait for the current backup and any cleanup to finish."
	}
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
	command := exec.CommandContext(ctx, ".tools/bin/uv", "run", "--locked", "python", "-m", "scripts.manual_backup", action, "--admin")
	command.Dir, command.Env = runner.repoRoot, os.Environ()
	isolateCommand(command)
	output, err := command.Output()
	if err != nil {
		return result, err
	}
	if err = json.Unmarshal(output, &result); err != nil {
		return result, err
	}
	prior := result.PriorVerified
	if prior != nil && !prior.valid() {
		result.PriorVerified = nil
		result.State = "UNCONFIGURED"
		result.Message = "The prior recovery receipt has incomplete verification evidence."
	}
	return result, nil
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
		hideBackupDiagnostics(&run)
		runner.mu.Lock()
		_, localActive := runner.active[run.ID]
		runner.mu.Unlock()
		active = active || localActive || run.Status == "QUEUED" || run.Status == "RUNNING"
		runs = append(runs, run)
	}
	return runs, active, rows.Err()
}

func hideBackupDiagnostics(run *SyncRun) {
	if run.Type != SyncManualBackup {
		return
	}
	run.LogPath = nil
	delete(run.Summary, "errors")
	if run.Status == "FAILED" && run.ErrorMessage != nil {
		message := "Backup did not finish. Review preflight and retry manually."
		run.ErrorMessage = &message
	}
}

func (runner *CommandSyncRunner) latestVerifiedBackup(ctx context.Context, scope string) (*SyncRun, error) {
	last, err := scanSyncRun(runner.pool.QueryRow(ctx, syncRunSelect+`
		WHERE sync_type='MANUAL_BACKUP' AND status='SUCCEEDED'
		  AND parameters->>'scope'=$1 AND summary->>'scope'=$1 AND summary->>'verified'='true'
		ORDER BY finished_at DESC,run_id DESC LIMIT 1`, scope))
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	hideBackupDiagnostics(&last)
	return &last, nil
}

func (runner *CommandSyncRunner) backupReminder(ctx context.Context, view *BackupView, now time.Time) error {
	full, err := runner.latestVerifiedBackup(ctx, backupFullRecovery)
	if err != nil {
		return err
	}
	view.LastFullRecovery = full
	switch view.Availability.Scope {
	case backupFullRecovery:
		return applySelectedBackupReminder(view, full, now)
	case backupRecoverableOnly:
		last, err := runner.latestVerifiedBackup(ctx, backupRecoverableOnly)
		if err != nil {
			return err
		}
		return applySelectedBackupReminder(view, last, now)
	default:
		return nil
	}
}

func applySelectedBackupReminder(view *BackupView, last *SyncRun, now time.Time) error {
	if prior := view.Availability.PriorVerified; prior != nil && prior.Scope == view.Availability.Scope {
		captured, verified, timeErr := verificationTimes(prior.VerifiedAt, prior.CapturedAt)
		if timeErr != nil || verified.After(now) {
			return errWorkControlConflict
		}
		if last == nil || verified.After(verifiedBackupTime(*last)) {
			return setBackupDue(view, captured, verified, now)
		}
	}
	if last == nil {
		return nil
	}
	return applyBackupReminder(view, *last, now)
}

func applyBackupReminder(view *BackupView, last SyncRun, now time.Time) error {
	verifiedAt, ok := last.Summary["verified_at"].(string)
	capturedAt, _ := last.Summary["captured_at"].(string)
	captured, timestamp, err := verificationTimes(verifiedAt, capturedAt)
	if !ok || err != nil || timestamp.After(now) {
		return errWorkControlConflict
	}
	view.LastVerified = &last
	return setBackupDue(view, captured, timestamp, now)
}

func verifiedBackupTime(run SyncRun) time.Time {
	timestamp, _ := time.Parse(time.RFC3339Nano, stringParameter(run.Summary, "verified_at"))
	return timestamp
}

func setBackupDue(view *BackupView, captured, timestamp, now time.Time) error {
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

type backupRequest struct {
	RequestID         string `json:"request_id"`
	Confirmed         bool   `json:"confirmed"`
	Scope             string `json:"scope"`
	UnavailableSHA256 string `json:"unavailable_sha256"`
}

func (input backupRequest) matches(run SyncRun) bool {
	return stringParameter(run.Parameters, "scope") == input.Scope &&
		stringParameter(run.Parameters, "unavailable_sha256") == input.UnavailableSHA256
}

func (input backupRequest) matchesPreflight(availability BackupAvailability) bool {
	if input.Scope != availability.Scope {
		return false
	}
	if input.Scope == backupFullRecovery {
		return true
	}
	return availability.UnavailableSHA256 != nil && *availability.UnavailableSHA256 == input.UnavailableSHA256
}

func (application *App) startBackup(response http.ResponseWriter, request *http.Request) {
	input, decodeErr := decodeBackupRequest(response, request)
	if decodeErr != nil {
		application.publicError(response, http.StatusBadRequest, "confirmed scope, UUID request_id and recoverable inventory digest required")
		return
	}
	if application.writeExistingBackup(response, request, input) {
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
	if !input.matchesPreflight(view.Availability) {
		application.publicError(response, http.StatusConflict, "backup policy or unavailable dependencies changed; run preflight again")
		return
	}
	run, err := application.syncRunner.Start(request.Context(), SyncRequest{
		Type: SyncManualBackup, ManualRequestID: input.RequestID,
		BackupScope: input.Scope, BackupUnavailableSHA256: input.UnavailableSHA256,
	})
	if errors.Is(err, errWorkControlConflict) {
		application.publicError(response, http.StatusConflict, "request ID already belongs to another operation or recovery scope")
		return
	}
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	hideBackupDiagnostics(&run)
	application.writeJSON(response, http.StatusAccepted, run)
}

func (application *App) writeExistingBackup(response http.ResponseWriter, request *http.Request, input backupRequest) bool {
	previous, err := application.syncRunner.Get(request.Context(), input.RequestID)
	if errors.Is(err, errSyncRunNotFound) {
		return false
	}
	if err != nil {
		application.publicError(response, http.StatusServiceUnavailable, "backup request history unavailable")
		return true
	}
	if previous.Type != SyncManualBackup || !input.matches(previous) {
		application.publicError(response, http.StatusConflict, "request ID already belongs to another operation or recovery scope")
		return true
	}
	hideBackupDiagnostics(&previous)
	application.writeJSON(response, http.StatusAccepted, previous)
	return true
}

func decodeBackupRequest(response http.ResponseWriter, request *http.Request) (backupRequest, error) {
	var input backupRequest
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 4096))
	decoder.DisallowUnknownFields()
	var trailing any
	if decoder.Decode(&input) != nil || decoder.Decode(&trailing) != io.EOF ||
		!input.Confirmed || !backupRequestID.MatchString(input.RequestID) ||
		!validBackupScope(input.Scope, input.UnavailableSHA256) {
		return backupRequest{}, errWorkControlConflict
	}
	return input, nil
}

func validBackupScope(scope, digest string) bool {
	switch scope {
	case backupFullRecovery:
		return digest == ""
	case backupRecoverableOnly:
		return backupSnapshotID.MatchString(digest)
	default:
		return false
	}
}

func (point backupPoint) valid() bool {
	proof := point.backupVerification
	payload, err := json.Marshal(proof)
	return err == nil && point.LogicalBytes >= 0 && point.PackedBytes >= 0 && point.RepositoryBytes >= 0 &&
		validBackupSummary(payload, proof.Scope, proof.UnavailableSHA256)
}

type backupVerification struct {
	Scope                   string `json:"scope"`
	Status                  string `json:"status"`
	Verified                bool   `json:"verified"`
	SnapshotID              string `json:"snapshot_id"`
	VerifiedAt              string `json:"verified_at"`
	CapturedAt              string `json:"captured_at"`
	UnavailableSHA256       string `json:"unavailable_sha256"`
	UnavailableDependencies *int   `json:"unavailable_dependencies"`
	FullRecovery            *bool  `json:"full_recovery"`
	Restore                 struct {
		Status                  string          `json:"status"`
		Isolated                bool            `json:"database_isolated"`
		FullRecovery            *bool           `json:"full_recovery"`
		UnavailableDependencies *int            `json:"unavailable_dependencies"`
		Globals                 json.RawMessage `json:"global_role_restore"`
	} `json:"full_operating_restore_drill"`
}

// Inspect JSON only; backup success requires completed verification, not an exit code.
func validBackupSummary(payload []byte, scope, digest string) bool {
	var summary backupVerification
	decoder := json.NewDecoder(bytes.NewReader(payload))
	if decoder.Decode(&summary) != nil || summary.Scope != scope || summary.UnavailableSHA256 != digest ||
		!validBackupScope(scope, digest) || !summary.Verified || !backupSnapshotID.MatchString(summary.SnapshotID) {
		return false
	}
	_, _, err := verificationTimes(summary.VerifiedAt, summary.CapturedAt)
	return err == nil && summary.validRestore()
}

func (summary backupVerification) validRestore() bool {
	restore := summary.Restore
	if !summary.hasMatchingDrill() {
		return false
	}
	if summary.Scope == backupRecoverableOnly {
		return summary.Status == "VERIFIED_RECOVERABLE" && restore.Status == "PASS_RECOVERABLE" &&
			!*summary.FullRecovery && *summary.UnavailableDependencies >= 0
	}
	return summary.Status == "VERIFIED" && restore.Status == "PASS" &&
		*summary.FullRecovery && *summary.UnavailableDependencies == 0 &&
		validGlobalRestore(restore.Globals)
}

func (summary backupVerification) hasMatchingDrill() bool {
	restore := summary.Restore
	return restore.Isolated && restore.FullRecovery != nil && summary.FullRecovery != nil &&
		restore.UnavailableDependencies != nil && summary.UnavailableDependencies != nil &&
		*restore.FullRecovery == *summary.FullRecovery &&
		*restore.UnavailableDependencies == *summary.UnavailableDependencies
}

func validGlobalRestore(payload []byte) bool {
	var proof struct {
		Status            string `json:"status"`
		Network           string `json:"network"`
		GlobalsApplied    bool   `json:"globals_applied"`
		OwnershipRestored bool   `json:"original_ownership_restored"`
	}
	return json.Unmarshal(payload, &proof) == nil && proof.Status == "PASS" && proof.Network == "none" &&
		proof.GlobalsApplied && proof.OwnershipRestored
}
