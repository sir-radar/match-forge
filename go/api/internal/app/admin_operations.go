package app

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/jackc/pgx/v5"
)

var errWorkControlConflict = errors.New("work cannot be controlled in its current state; terminal work needs a new request from its domain owner")

type OperationPage struct {
	Page     int `json:"page"`
	PageSize int `json:"page_size"`
}
type OperationView struct {
	Domain       string    `json:"domain"`
	Source       string    `json:"source"`
	SourceSHA256 string    `json:"source_sha256,omitempty"`
	ObservedAt   time.Time `json:"observed_at"`
	OperationPage
	HasMore bool              `json:"has_more"`
	Items   []json.RawMessage `json:"items"`
}
type WorkFilters struct {
	OperationPage
	State string
}
type WorkItem struct {
	ID               string     `json:"work_id"`
	Type             string     `json:"work_type"`
	State            string     `json:"state"`
	InputHash        string     `json:"input_hash"`
	Priority         int        `json:"priority"`
	RequestedAt      time.Time  `json:"requested_at"`
	AvailableAt      time.Time  `json:"available_at"`
	StartedAt        *time.Time `json:"started_at"`
	FinishedAt       *time.Time `json:"finished_at"`
	AgeSeconds       float64    `json:"age_seconds"`
	Generation       int64      `json:"generation"`
	LeaseOwner       *string    `json:"lease_owner"`
	LeaseUntil       *time.Time `json:"lease_until"`
	HeartbeatAt      *time.Time `json:"heartbeat_at"`
	Attempts         int        `json:"attempt_count"`
	MaxAttempts      int        `json:"max_attempts"`
	ParentWorkID     *string    `json:"parent_work_id"`
	ParentSyncRunID  *string    `json:"parent_sync_run_id"`
	Dependencies     []string   `json:"dependencies"`
	DependencyCount  int64      `json:"dependency_count"`
	LastErrorCode    *string    `json:"last_error_code"`
	LastErrorMessage *string    `json:"last_error_message"`
}
type WorkPage struct {
	OperationPage
	ObservedAt time.Time  `json:"observed_at"`
	HasMore    bool       `json:"has_more"`
	Items      []WorkItem `json:"items"`
}
type operationsReader interface {
	Operations(context.Context, string, OperationPage) (OperationView, error)
	WorkItems(context.Context, WorkFilters) (WorkPage, error)
	WorkItem(context.Context, string) (WorkItem, error)
	ControlWork(context.Context, string, string) (WorkItem, error)
}

func operationPagination(request *http.Request) (OperationPage, error) {
	page, size, err := performancePagination(request)
	if err != nil {
		return OperationPage{}, err
	}
	if page > math.MaxInt/size {
		return OperationPage{}, errors.New("page offset is too large")
	}
	return OperationPage{Page: page, PageSize: size}, nil
}
func (application *App) operations(response http.ResponseWriter, request *http.Request) {
	domain := request.PathValue("domain")
	if _, ok := operationQueries[domain]; !ok && domain != "r3-audit" {
		application.publicError(response, http.StatusBadRequest, "unsupported operations domain")
		return
	}
	page, err := operationPagination(request)
	if err != nil {
		application.publicError(response, http.StatusBadRequest, err.Error())
		return
	}
	if domain == "r3-audit" {
		view, readErr := application.r3Audit(page)
		application.respondOperation(response, view, readErr)
		return
	}
	reader, ok := application.syncRunner.(operationsReader)
	if !ok {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	view, err := reader.Operations(request.Context(), domain, page)
	application.respondOperation(response, view, err)
}
func (application *App) r3Audit(page OperationPage) (OperationView, error) {
	view := OperationView{Domain: "r3-audit", Source: "TRACKED_PROJECT_STATUS", ObservedAt: time.Now().UTC(), OperationPage: page, Items: []json.RawMessage{}}
	payload, err := os.ReadFile(filepath.Join(application.config.RepoRoot, "docs", "project-status.json"))
	if err != nil {
		return view, errProductUnavailable
	}
	audit, err := decodeProjectAudit(payload)
	if err != nil {
		return view, err
	}
	sum := sha256.Sum256(payload)
	view.SourceSHA256 = hex.EncodeToString(sum[:])
	if page.Page == 1 {
		view.Items = append(view.Items, audit)
	}
	return view, nil
}
func decodeProjectAudit(payload []byte) (json.RawMessage, error) {
	var status struct {
		Contract string `json:"contract"`
		Product  struct {
			Audit json.RawMessage `json:"audit_remediation"`
		} `json:"mvp_product"`
	}
	if json.Unmarshal(payload, &status) != nil || status.Contract != "ProjectStatusV2" {
		return nil, errProductUnavailable
	}
	var audit struct {
		CurrentPhase       string   `json:"current_phase"`
		BlockedFindings    []string `json:"blocked_findings"`
		ResearchAuthorized *bool    `json:"research_execution_authorized"`
	}
	if json.Unmarshal(status.Product.Audit, &audit) != nil || audit.CurrentPhase == "" || audit.BlockedFindings == nil || audit.ResearchAuthorized == nil {
		return nil, errProductUnavailable
	}
	return status.Product.Audit, nil
}

func (application *App) listWork(response http.ResponseWriter, request *http.Request) {
	page, err := operationPagination(request)
	if err != nil {
		application.publicError(response, http.StatusBadRequest, err.Error())
		return
	}
	state := request.URL.Query().Get("state")
	if !workStateFilter(state) {
		application.publicError(response, http.StatusBadRequest, "unsupported work state")
		return
	}
	reader, ok := application.syncRunner.(operationsReader)
	if !ok {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	result, err := reader.WorkItems(request.Context(), WorkFilters{OperationPage: page, State: state})
	application.respondOperation(response, result, err)
}
func workStateFilter(state string) bool {
	switch state {
	case "", "PENDING", "RUNNING", "RETRY_WAIT", "BLOCKED", "FAILED", "CANCELLED", "SUCCEEDED":
		return true
	default:
		return false
	}
}
func (application *App) getWork(response http.ResponseWriter, request *http.Request) {
	if !canonicalIDPattern.MatchString(request.PathValue("work_id")) {
		application.publicError(response, http.StatusBadRequest, "invalid work ID")
		return
	}
	reader, ok := application.syncRunner.(operationsReader)
	if !ok {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	result, err := reader.WorkItem(request.Context(), request.PathValue("work_id"))
	application.respondOperation(response, result, err)
}
func emptyOperationBody(response http.ResponseWriter, request *http.Request) bool {
	if request.ContentLength == 0 {
		return true
	}
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 64*1024))
	var body map[string]json.RawMessage
	if decoder.Decode(&body) != nil || body == nil || len(body) != 0 {
		return false
	}
	var trailing any
	return decoder.Decode(&trailing) == io.EOF
}
func (application *App) controlWork(action string) http.HandlerFunc {
	return func(response http.ResponseWriter, request *http.Request) {
		if !canonicalIDPattern.MatchString(request.PathValue("work_id")) || !emptyOperationBody(response, request) {
			application.publicError(response, http.StatusBadRequest, "work control requires a work UUID and an empty JSON object")
			return
		}
		reader, ok := application.syncRunner.(operationsReader)
		if !ok {
			application.respondOperation(response, nil, errProductUnavailable)
			return
		}
		result, err := reader.ControlWork(request.Context(), request.PathValue("work_id"), action)
		if err != nil {
			application.respondOperation(response, nil, err)
			return
		}
		application.writeJSON(response, http.StatusAccepted, result)
	}
}
func (application *App) respondOperation(response http.ResponseWriter, value any, err error) {
	if err == nil {
		application.writeJSON(response, http.StatusOK, value)
		return
	}
	status, message := http.StatusInternalServerError, "operations request failed"
	for _, failure := range []struct {
		cause   error
		status  int
		message string
	}{
		{context.DeadlineExceeded, http.StatusGatewayTimeout, "request timed out"},
		{pgx.ErrNoRows, http.StatusNotFound, "work not found"},
		{errSyncRunNotFound, http.StatusNotFound, "work not found"},
		{errWorkControlConflict, http.StatusConflict, errWorkControlConflict.Error()},
		{errSyncAlreadyRunning, http.StatusConflict, "a sync run is already active"},
		{errSyncRunNotRetryable, http.StatusConflict, "only failed or cancelled sync runs can be retried"},
		{errSyncRunNotActive, http.StatusConflict, "sync run is not active"},
		{errProductUnavailable, http.StatusServiceUnavailable, "operations data unavailable"},
	} {
		if errors.Is(err, failure.cause) {
			status, message = failure.status, failure.message
			break
		}
	}
	application.publicError(response, status, message)
}
