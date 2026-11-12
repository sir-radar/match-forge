package app

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"os"
	"regexp"
	"strings"

	"football-forecasting/go/api/internal/storage"
)

var storageResourceID = regexp.MustCompile(`^[0-9a-f]{64}$`)

// storageManagerFor builds the single resource manager for the operating runner.
// Without a valid policy it still manages databases and worktrees.
func storageManagerFor(runner SyncRunner, logger interface {
	Error(string, ...any)
}) *storage.Manager {
	command, ok := runner.(*CommandSyncRunner)
	if !ok || command.pool == nil {
		return nil
	}
	manager := &storage.Manager{Pool: command.pool, Repository: command.repoRoot, Logger: command.logger}
	if path := os.Getenv("MATCHFORGE_STORAGE_POLICY"); path != "" {
		policy, err := storage.LoadPolicy(path)
		if err != nil {
			logger.Error("storage policy invalid; filesystem management disabled", "error", err)
		} else {
			manager.Policy = &policy
		}
	}
	return manager
}

func (application *App) storageReady(ctx context.Context) bool {
	if application.storage == nil {
		return false
	}
	var ready bool
	err := application.storage.Pool.QueryRow(ctx, `SELECT to_regclass('football.storage_operations') IS NOT NULL`).Scan(&ready)
	return err == nil && ready
}

func (application *App) requireStorage(response http.ResponseWriter, request *http.Request) bool {
	if application.storageReady(request.Context()) {
		return true
	}
	application.publicError(response, http.StatusConflict, "Storage management migration has not been deployed.")
	return false
}

// ownerActor authenticates the owner credential for actions that change what may
// be deleted. The browser Origin check alone is not sufficient for these.
func (application *App) ownerActor(response http.ResponseWriter, request *http.Request) (string, bool) {
	if !validAdminToken(application.config.AdminCLIToken, request.Header.Get("Authorization")) {
		application.publicError(response, http.StatusForbidden, "Owner credential required for this storage action.")
		return "", false
	}
	identity := sha256.Sum256([]byte(application.config.AdminCLIToken))
	return "owner:" + hex.EncodeToString(identity[:8]), true
}

func decodeStorage(response http.ResponseWriter, request *http.Request, body any) bool {
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 64<<10))
	decoder.DisallowUnknownFields()
	return decoder.Decode(body) == nil && decoder.Decode(new(any)) == io.EOF
}

func validResourceIDs(ids []string) bool {
	if len(ids) == 0 || len(ids) > storage.MaxBatch {
		return false
	}
	for _, id := range ids {
		if !storageResourceID.MatchString(id) {
			return false
		}
	}
	return true
}

func (application *App) storageResources(response http.ResponseWriter, request *http.Request) {
	if !application.requireStorage(response, request) {
		return
	}
	if request.URL.Query().Get("refresh") == "1" {
		storage.InvalidateMeasurements()
	}
	// Read the queue first: a comparison reported finished is then already in the inventory.
	comparisons := storage.CompareQueue()
	inventory, err := application.storage.Inventory(request.Context())
	if err != nil {
		application.respondOperation(response, nil, err)
		return
	}
	application.writeJSON(response, http.StatusOK, map[string]any{"inventory": inventory, "comparisons": comparisons})
}

type storageActionBody struct {
	Action      string   `json:"action"`
	ResourceIDs []string `json:"resource_ids"`
}

func (application *App) previewStorageAction(response http.ResponseWriter, request *http.Request) {
	if !application.requireStorage(response, request) {
		return
	}
	var body storageActionBody
	if !decodeStorage(response, request, &body) || !validResourceIDs(body.ResourceIDs) {
		application.publicError(response, http.StatusBadRequest, "Select between 1 and 50 managed resources.")
		return
	}
	plan, _, err := application.storage.Preview(request.Context(), body.Action, body.ResourceIDs)
	if err != nil {
		application.publicError(response, http.StatusBadRequest, err.Error())
		return
	}
	application.writeJSON(response, http.StatusOK, plan)
}

func (application *App) executeStorageAction(response http.ResponseWriter, request *http.Request) {
	// Authenticate before revealing anything about storage readiness.
	actor, ok := application.ownerActor(response, request)
	if !ok {
		return
	}
	if !application.requireStorage(response, request) {
		return
	}
	var body storage.SubmitRequest
	if !decodeStorage(response, request, &body) || !validResourceIDs(body.ResourceIDs) || !storageResourceID.MatchString(body.PlanSHA256) {
		application.publicError(response, http.StatusBadRequest, "Invalid storage action request.")
		return
	}
	batch, err := application.storage.Submit(request.Context(), body, actor)
	if err != nil {
		application.writeStorageError(response, err)
		return
	}
	application.writeJSON(response, http.StatusAccepted, batch)
}

func (application *App) writeStorageError(response http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, storage.ErrStalePlan), errors.Is(err, storage.ErrBusy):
		application.publicError(response, http.StatusConflict, err.Error())
	case errors.Is(err, storage.ErrConfirmation):
		application.publicError(response, http.StatusBadRequest, err.Error())
	case strings.Contains(err.Error(), "protected"):
		application.publicError(response, http.StatusForbidden, "A selected resource is protected; nothing was changed.")
	default:
		application.respondOperation(response, nil, err)
	}
}

func (application *App) storageOperations(response http.ResponseWriter, request *http.Request) {
	if !application.requireStorage(response, request) {
		return
	}
	operations, err := application.storage.Operations(request.Context(), 200)
	if operations == nil {
		operations = []storage.OperationRecord{}
	}
	application.respondOperation(response, map[string]any{"operations": operations}, err)
}

// storageLifecycle reports the five-hour cleanup policy, tracked resources with
// their eligibility, the audit trail and unregistered test databases.
func (application *App) storageLifecycle(response http.ResponseWriter, request *http.Request) {
	if !application.requireStorage(response, request) {
		return
	}
	status, err := application.storage.LifecycleStatus(request.Context())
	application.respondOperation(response, status, err)
}

// storageMaintenance returns the latest daily, weekly and monthly reports.
func (application *App) storageMaintenance(response http.ResponseWriter, request *http.Request) {
	if !application.requireStorage(response, request) {
		return
	}
	reports, err := application.storage.MaintenanceHistory(request.Context(), 60)
	var policy *storage.MaintenancePolicy
	if application.storage.Policy != nil {
		policy = application.storage.Policy.Maintenance
	}
	application.respondOperation(response, map[string]any{"policy": policy, "reports": reports}, err)
}

func (application *App) cancelStorageBatch(response http.ResponseWriter, request *http.Request) {
	if !application.requireStorage(response, request) {
		return
	}
	id := request.PathValue("batch_id")
	if !backupRequestID.MatchString(id) {
		application.publicError(response, http.StatusBadRequest, "Invalid batch identity.")
		return
	}
	cancelled, err := application.storage.Cancel(request.Context(), id)
	application.respondOperation(response, map[string]any{"cancelled": cancelled}, err)
}

func (application *App) compareStorageDatabases(response http.ResponseWriter, request *http.Request) {
	if !application.requireStorage(response, request) {
		return
	}
	var body struct {
		ResourceIDs []string `json:"resource_ids"`
	}
	if !decodeStorage(response, request, &body) || !validResourceIDs(body.ResourceIDs) {
		application.publicError(response, http.StatusBadRequest, "Select between 1 and 50 databases.")
		return
	}
	queued, err := application.storage.StartCompare(request.Context(), body.ResourceIDs)
	if err != nil {
		application.publicError(response, http.StatusConflict, err.Error())
		return
	}
	application.writeJSON(response, http.StatusAccepted, map[string]any{"queued": queued})
}

func (application *App) recordStorageDisposition(response http.ResponseWriter, request *http.Request) {
	// Authenticate before revealing anything about storage readiness.
	actor, ok := application.ownerActor(response, request)
	if !ok {
		return
	}
	if !application.requireStorage(response, request) {
		return
	}
	var body dispositionBody
	if !decodeStorage(response, request, &body) || !body.valid() {
		application.publicError(response, http.StatusBadRequest, "Invalid disposition. Explain the decision in 20 to 4000 characters.")
		return
	}
	rationale := strings.TrimSpace(body.Rationale)
	err := application.storage.Dispose(request.Context(), body.ResourceID, body.Evidence, body.Disposition, rationale, actor)
	if errors.Is(err, storage.ErrStalePlan) {
		application.publicError(response, http.StatusConflict, "Evidence changed since you reviewed it; refresh first.")
		return
	}
	application.respondOperation(response, map[string]any{"recorded": err == nil}, err)
}

func (application *App) protectStorageResource(response http.ResponseWriter, request *http.Request) {
	// Authenticate before revealing anything about storage readiness.
	actor, ok := application.ownerActor(response, request)
	if !ok {
		return
	}
	if !application.requireStorage(response, request) {
		return
	}
	var body struct {
		ResourceID string `json:"resource_id"`
		Reason     string `json:"reason"`
	}
	if !decodeStorage(response, request, &body) || !storageResourceID.MatchString(body.ResourceID) {
		application.publicError(response, http.StatusBadRequest, "Invalid protection request.")
		return
	}
	reason := strings.TrimSpace(body.Reason)
	if len(reason) < 5 || len(reason) > 2000 {
		application.publicError(response, http.StatusBadRequest, "Give a reason of 5 to 2000 characters.")
		return
	}
	err := application.storage.Protect(request.Context(), body.ResourceID, reason, actor)
	application.respondOperation(response, map[string]any{"protected": err == nil}, err)
}

type dispositionBody struct {
	ResourceID  string `json:"resource_id"`
	Evidence    string `json:"evidence_sha256"`
	Disposition string `json:"disposition"`
	Rationale   string `json:"rationale"`
}

func (b dispositionBody) valid() bool {
	rationale := strings.TrimSpace(b.Rationale)
	return storageResourceID.MatchString(b.ResourceID) && storageResourceID.MatchString(b.Evidence) &&
		(b.Disposition == "UNIQUE_DATA_NOT_REQUIRED" || b.Disposition == "PRESERVE") &&
		len(rationale) >= 20 && len(rationale) <= 4000
}

// recoverStorage resolves operations interrupted by a previous shutdown.
func (application *App) recoverStorage(ctx context.Context) {
	if !application.storageReady(ctx) {
		return
	}
	if err := application.storage.Recover(ctx); err != nil {
		application.logger.Error("storage operation recovery failed", "error", err)
	}
}
