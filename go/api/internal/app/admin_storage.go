package app

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"football-forecasting/go/api/internal/storage"
)

type StorageView struct {
	State              string            `json:"state"`
	Message            string            `json:"message"`
	DestructiveEnabled bool              `json:"destructive_cleanup_enabled"`
	Latest             *storage.Review   `json:"latest"`
	WorkID             *string           `json:"work_id"`
	ManifestSHA256     *string           `json:"manifest_sha256"`
	History            []json.RawMessage `json:"history"`
	Approvals          []json.RawMessage `json:"approvals"`
}
type storageReader interface {
	StorageView(context.Context) (StorageView, error)
}

func (runner *CommandSyncRunner) StorageView(ctx context.Context) (StorageView, error) {
	view := StorageView{State: "READY", Message: "Dry-run lifecycle reviews; destructive cleanup is disabled.", History: []json.RawMessage{}, Approvals: []json.RawMessage{}}
	var ready bool
	if err := runner.pool.QueryRow(ctx, `SELECT to_regclass('football.storage_reviews') IS NOT NULL`).Scan(&ready); err != nil {
		return view, err
	}
	if !ready {
		view.State = "MIGRATION_PENDING"
		view.Message = "Storage lifecycle migration has not been deployed."
		return view, nil
	}
	rows, err := runner.pool.Query(ctx, `SELECT work_id::text,manifest_sha256,manifest FROM football.storage_reviews ORDER BY observed_at DESC LIMIT 30`)
	if err != nil {
		return view, err
	}
	defer rows.Close()
	for rows.Next() {
		var id, digest string
		var payload json.RawMessage
		if err = rows.Scan(&id, &digest, &payload); err != nil {
			return view, err
		}
		if view.Latest == nil {
			view.Latest = &storage.Review{}
			if err = json.Unmarshal(payload, view.Latest); err != nil {
				return view, err
			}
			view.WorkID = &id
			view.ManifestSHA256 = &digest
		}
		view.History = append(view.History, payload)
	}
	if err = rows.Err(); err != nil {
		return view, err
	}
	if view.Latest == nil {
		view.State = "EMPTY"
		view.Message = "No storage review has completed. Run a dry-run scan."
	}
	return view, runner.storageApprovals(ctx, &view)
}
func (runner *CommandSyncRunner) storageApprovals(ctx context.Context, view *StorageView) error {
	rows, err := runner.pool.Query(ctx, `SELECT jsonb_build_object('approval_id',approval_id,'work_id',work_id,'manifest_sha256',manifest_sha256,'resource_ids',resource_ids,'approved_at',approved_at,'expires_at',expires_at,'disposition',disposition) FROM football.storage_approvals ORDER BY approved_at DESC LIMIT 30`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var payload json.RawMessage
		if err = rows.Scan(&payload); err != nil {
			return err
		}
		view.Approvals = append(view.Approvals, payload)
	}
	return rows.Err()
}
func (runner *CommandSyncRunner) storageReview(ctx context.Context, runID string) (map[string]interface{}, error) {
	policy, err := storage.LoadPolicy(os.Getenv("MATCHFORGE_STORAGE_POLICY"))
	if err != nil {
		return nil, err
	}
	lease := storage.Lease{WorkID: runID, Owner: runID}
	if err = runner.pool.QueryRow(ctx, `SELECT lease_token::text,generation FROM football.work_items WHERE work_id=$1::uuid AND lease_owner=$1::text AND state='RUNNING'`, runID).Scan(&lease.Token, &lease.Generation); err != nil {
		return nil, err
	}
	review, err := storage.Collect(ctx, policy, runner.pool, runner.repoRoot)
	if err != nil {
		return nil, err
	}
	for i := range review.Resources {
		r := &review.Resources[i]
		r.Blockers = append(r.Blockers, r.Eligibility(review.ObservedAt)...)
	}
	if err = storage.Publish(ctx, runner.pool, lease, review); err != nil {
		return nil, err
	}
	for _, alert := range review.Alerts {
		runner.logger.Warn("storage lifecycle alert", "run_id", runID, "message", alert)
	}
	return map[string]interface{}{"status": "SUCCEEDED", "dry_run": true, "resources": len(review.Resources), "alerts": review.Alerts, "reclaimed_bytes": 0, "work_id": runID, "policy_sha256": review.PolicySHA256}, nil
}
func (application *App) storageView(response http.ResponseWriter, request *http.Request) {
	reader, ok := application.syncRunner.(storageReader)
	if !ok {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	view, err := reader.StorageView(request.Context())
	application.respondOperation(response, view, err)
}
func (application *App) startStorageReview(response http.ResponseWriter, request *http.Request) {
	var body struct {
		DryRun bool `json:"dry_run"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 4096))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&body) != nil || !body.DryRun || decoder.Decode(new(any)) != io.EOF {
		application.publicError(response, 400, "Only an explicit dry-run review is supported.")
		return
	}
	if _, err := storage.LoadPolicy(os.Getenv("MATCHFORGE_STORAGE_POLICY")); err != nil {
		application.publicError(response, 409, "Configure a valid storage policy first.")
		return
	}
	run, err := application.syncRunner.Start(request.Context(), SyncRequest{Type: SyncStorageLifecycle})
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	application.writeJSON(response, 202, run)
}

type storageApproval struct {
	ID          string    `json:"approval_id"`
	WorkID      string    `json:"work_id"`
	Manifest    string    `json:"manifest_sha256"`
	Resources   []string  `json:"resource_ids"`
	ExpiresAt   time.Time `json:"expires_at"`
	Disposition string    `json:"disposition"`
	Confirmed   bool      `json:"confirmed"`
}

func (application *App) reviewStorageApproval(response http.ResponseWriter, request *http.Request) {
	runner, ok := application.syncRunner.(*CommandSyncRunner)
	if !ok {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	var body storageApproval
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&body) != nil || decoder.Decode(new(any)) != io.EOF || !body.valid() {
		application.publicError(response, 400, "Invalid resource-specific review receipt.")
		return
	}
	payload, _ := json.Marshal(body.Resources)
	result, err := runner.pool.Exec(request.Context(), `INSERT INTO football.storage_approvals
 (approval_id,work_id,manifest_sha256,resource_ids,approved_by,expires_at,disposition)
 SELECT $1,work_id,manifest_sha256,$4,'local-owner',$5,$6 FROM football.storage_reviews
 WHERE work_id=$2 AND manifest_sha256=$3 AND NOT EXISTS(
 SELECT 1 FROM jsonb_array_elements_text($4::jsonb) wanted WHERE NOT EXISTS(
 SELECT 1 FROM jsonb_array_elements(manifest->'resources') r WHERE r->>'resource_id'=wanted))
 ON CONFLICT(approval_id) DO NOTHING`, body.ID, body.WorkID, body.Manifest, payload, body.ExpiresAt, body.Disposition)
	if err != nil {
		application.respondOperation(response, nil, err)
		return
	}
	if result.RowsAffected() != 1 {
		application.publicError(response, 409, "Review identity or manifest changed; refresh before recording a new receipt.")
		return
	}
	application.writeJSON(response, 201, map[string]any{"recorded": true, "destructive_cleanup_enabled": false})
}
func (a storageApproval) valid() bool {
	if !a.validIdentity() {
		return false
	}
	if len(a.Resources) == 0 || len(a.Resources) > 100 || !a.ExpiresAt.After(time.Now()) {
		return false
	}
	if a.Disposition != "REVIEWED" && a.Disposition != "REJECTED" {
		return false
	}
	for _, id := range a.Resources {
		if !backupSnapshotID.MatchString(id) {
			return false
		}
	}
	return true
}

// Scheduling uses the existing runner/BULK exclusion and shared work leases. It only
// submits scans or the existing fully verified backup command; never filesystem actions.
func (application *App) runStorageSchedule(ctx context.Context) {
	path := os.Getenv("MATCHFORGE_STORAGE_POLICY")
	if path == "" {
		return
	}
	policy, err := storage.LoadPolicy(path)
	if err != nil {
		application.logger.Error("storage policy invalid", "error", err)
		return
	}
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		application.storageScheduleTick(ctx, policy)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
func (application *App) storageScheduleTick(ctx context.Context, policy storage.Policy) {
	runner, ok := application.syncRunner.(*CommandSyncRunner)
	if !ok {
		return
	}
	var ready bool
	if err := runner.pool.QueryRow(ctx, `SELECT to_regclass('football.storage_reviews') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		return
	}
	application.runAutomaticStorageCleanup(ctx)
	application.runLifecycleCleanup(ctx)
	for _, kind := range []SyncType{SyncStorageLifecycle, SyncManualBackup} {
		request, due, err := runner.storageScheduledRequest(ctx, kind, policy)
		if err == nil && due {
			_, err = runner.Start(ctx, request)
		}
		if err != nil && !errors.Is(err, errSyncAlreadyRunning) {
			application.logger.Warn("storage schedule blocked", "sync_type", kind, "error", err)
		}
	}
}
func (runner *CommandSyncRunner) storageScheduledRequest(ctx context.Context, kind SyncType, policy storage.Policy) (SyncRequest, bool, error) {
	request := SyncRequest{Type: kind}
	interval := policy.IntervalSeconds
	if kind == SyncManualBackup {
		interval = policy.BackupIntervalSeconds
	}
	var due bool
	// Failed attempts are also rate-limited. Successful snapshots still require real restore evidence.
	err := runner.pool.QueryRow(ctx, `SELECT NOT EXISTS(SELECT 1 FROM football.product_sync_runs WHERE sync_type=$1 AND requested_at>clock_timestamp()-make_interval(secs=>$2::integer)), floor(extract(epoch FROM clock_timestamp())/($2::integer))::bigint::text`, kind, interval).Scan(&due, &request.StorageScheduleSlot)
	if err != nil || !due || kind != SyncManualBackup {
		return request, due, err
	}
	view, err := runner.BackupView(ctx, true)
	if err != nil {
		return request, false, err
	}
	if view.Availability.State != "READY" {
		return request, false, errors.New("scheduled backup preflight blocked: " + view.Availability.State)
	}
	request.ManualRequestID = storageScheduleID(kind, request.StorageScheduleSlot)
	request.BackupScope = view.Availability.Scope
	if view.Availability.UnavailableSHA256 != nil {
		request.BackupUnavailableSHA256 = *view.Availability.UnavailableSHA256
	}
	if view.Availability.GovernedSHA256 != nil {
		request.BackupGovernedSHA256 = *view.Availability.GovernedSHA256
	}
	return request, true, err
}

func (a storageApproval) validIdentity() bool {
	return a.Confirmed && backupRequestID.MatchString(a.ID) && backupRequestID.MatchString(a.WorkID) && backupSnapshotID.MatchString(a.Manifest)
}

func storageScheduleID(kind SyncType, slot string) string {
	digest := sha256.Sum256([]byte("matchforge-storage-schedule:" + string(kind) + ":" + slot))
	b := digest[:16]
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
}

// runLifecycleCleanup applies the five-hour policy when the storage policy enables
// it; the manager rate-limits checks to the policy interval and records every
// decision. Failures are logged as alerts and recorded on the next check.
func (application *App) runLifecycleCleanup(ctx context.Context) {
	if application.storage == nil || !application.storageReady(ctx) {
		return
	}
	run, err := application.storage.RunLifecycleCleanup(ctx)
	switch {
	case err != nil:
		application.logger.Error("storage lifecycle cleanup blocked", "error", err)
	case run.Failed > 0:
		application.logger.Error("storage lifecycle deletions failed", "failed", run.Failed, "deleted", run.Deleted)
	case run.Submitted > 0:
		application.logger.Info("storage lifecycle cleanup", "deleted", run.Deleted, "reclaimed_bytes", run.ReclaimedBytes)
	}
}

// runAutomaticStorageCleanup applies only explicitly approved automatic policies.
// Without such a policy, scheduling remains read-only.
func (application *App) runAutomaticStorageCleanup(ctx context.Context) {
	if application.storage == nil || !application.storageReady(ctx) {
		return
	}
	submitted, err := application.storage.RunAutomaticCleanup(ctx)
	if err != nil {
		application.logger.Warn("automatic storage cleanup blocked", "error", err)
	} else if submitted > 0 {
		application.logger.Info("automatic storage cleanup submitted", "resources", submitted)
	}
}
