package app

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

type syncRunnerStub struct {
	started  []SyncRequest
	runs     []SyncRun
	startErr error
	getErr   error
}

func (runner *syncRunnerStub) Start(_ context.Context, request SyncRequest) (SyncRun, error) {
	runner.started = append(runner.started, request)
	if runner.startErr != nil {
		return SyncRun{}, runner.startErr
	}
	return SyncRun{
		ID: "10000000-0000-4000-8000-000000000001", Type: request.Type,
		Status: "QUEUED", RequestedAt: time.Date(2026, 9, 30, 10, 0, 0, 0, time.UTC),
		Parameters: map[string]interface{}{}, Summary: map[string]interface{}{},
	}, nil
}
func (runner *syncRunnerStub) List(context.Context) ([]SyncRun, error) { return runner.runs, nil }
func (runner *syncRunnerStub) Get(_ context.Context, id string) (SyncRun, error) {
	if runner.getErr != nil {
		return SyncRun{}, runner.getErr
	}
	return SyncRun{ID: id, Type: SyncOpenFootball, Status: "RUNNING", Parameters: map[string]interface{}{}, Summary: map[string]interface{}{}}, nil
}
func (runner *syncRunnerStub) Coverage(context.Context) (Coverage, error) {
	return Coverage{HistoricalMatches: 123}, nil
}

func newAdminTestApp(runner SyncRunner) *App {
	return NewWithSyncRunner(
		Config{AllowedOrigin: "http://127.0.0.1:3000"},
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		readinessStub{},
		unavailableProductStore{},
		runner,
	)
}

func TestAdminSyncStartRoutesUseFixedTypes(t *testing.T) {
	tests := []struct {
		path string
		want SyncType
	}{
		{path: "/v1/admin/sync/mvp", want: SyncMVP},
		{path: "/v1/admin/sync/openfootball", want: SyncOpenFootball},
		{path: "/v1/admin/sync/football-data-uk", want: SyncFootballDataUK},
		{path: "/v1/admin/sync/history", want: SyncHistoryBackfill},
		{path: "/v1/admin/sync/forecast-refresh", want: SyncForecastRefresh},
		{path: "/v1/admin/sync/external-predictions", want: SyncExternalPredictions},
		{path: "/v1/admin/sync/all", want: SyncAllData},
	}
	for _, test := range tests {
		t.Run(string(test.want), func(t *testing.T) {
			runner := &syncRunnerStub{}
			request := httptest.NewRequest(http.MethodPost, test.path, strings.NewReader(`{"date":"2026-09-30"}`))
			request.Header.Set("Content-Type", "application/json")
			response := httptest.NewRecorder()
			newAdminTestApp(runner).Handler().ServeHTTP(response, request)
			if response.Code != http.StatusAccepted {
				t.Fatalf("response = %d %s", response.Code, response.Body.String())
			}
			if len(runner.started) != 1 || runner.started[0].Type != test.want {
				t.Fatalf("started = %+v", runner.started)
			}
		})
	}
}

func TestAdminSyncPassesFixtureBackfillStartDate(t *testing.T) {
	runner := &syncRunnerStub{}
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/admin/sync/mvp",
		strings.NewReader(`{"date":"2026-10-03","from_date":"2026-09-29"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	newAdminTestApp(runner).Handler().ServeHTTP(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf("response = %d %s", response.Code, response.Body.String())
	}
	if len(runner.started) != 1 || runner.started[0].FromDate != "2026-09-29" {
		t.Fatalf("started = %+v", runner.started)
	}
}

func TestValidateSyncDateRangeRejectsReversedRange(t *testing.T) {
	_, err := validateSyncDateRange("2026-10-03", "2026-10-04")
	if err == nil || err.Error() != "from_date must not be after date" {
		t.Fatalf("error = %v", err)
	}
}

func TestCommandFailureIncludesLastLogLine(t *testing.T) {
	logFile, err := os.CreateTemp(t.TempDir(), "sync-run-*.log")
	if err != nil {
		t.Fatal(err)
	}
	defer logFile.Close()
	if _, err = logFile.WriteString("progress\nerror: OpenFootball fetch failed\n"); err != nil {
		t.Fatal(err)
	}

	failure := commandFailure(errors.New("exit status 1"), logFile)
	if failure.Error() != "exit status 1: error: OpenFootball fetch failed" {
		t.Fatalf("failure = %q", failure)
	}
}

func TestSyncCompletionMarksPartialWorkflowFailed(t *testing.T) {
	status, message := syncCompletion(map[string]interface{}{
		"status": "COMPLETED_WITH_ERRORS",
		"errors": map[string]interface{}{"mvp": "API-Football request limit reached"},
	})
	if status != "FAILED" {
		t.Fatalf("status = %q", status)
	}
	if message == nil || *message != "one or more data synchronization operations failed; see summary.errors" {
		t.Fatalf("message = %v", message)
	}

	status, message = syncCompletion(map[string]interface{}{"status": "COMPLETED"})
	if status != "SUCCEEDED" || message != nil {
		t.Fatalf("completion = %q %v", status, message)
	}
}

func TestRunCommandAcceptsStructuredPartialFailure(t *testing.T) {
	logFile, err := os.CreateTemp(t.TempDir(), "sync-run-*.log")
	if err != nil {
		t.Fatal(err)
	}
	defer logFile.Close()
	runner := &CommandSyncRunner{ctx: context.Background(), repoRoot: t.TempDir()}

	summary, err := runner.runCommand(
		"run-id",
		[]string{"/bin/sh", "-c", `echo '{"status":"COMPLETED_WITH_ERRORS","errors":{"mvp":"quota"}}'; exit 1`},
		logFile,
	)
	if err != nil {
		t.Fatal(err)
	}
	if summary["status"] != "COMPLETED_WITH_ERRORS" {
		t.Fatalf("summary = %+v", summary)
	}
}

func TestAdminSyncListGetAndErrors(t *testing.T) {
	runner := &syncRunnerStub{runs: []SyncRun{{ID: "one", Type: SyncMVP, Status: "SUCCEEDED"}}}
	application := newAdminTestApp(runner)
	list := httptest.NewRecorder()
	application.Handler().ServeHTTP(list, httptest.NewRequest(http.MethodGet, "/v1/admin/sync-runs", nil))
	if list.Code != http.StatusOK || !strings.Contains(list.Body.String(), `"historical_matches":123`) {
		t.Fatalf("list = %d %s", list.Code, list.Body.String())
	}
	get := httptest.NewRecorder()
	application.Handler().ServeHTTP(get, httptest.NewRequest(http.MethodGet, "/v1/admin/sync-runs/one", nil))
	if get.Code != http.StatusOK || !strings.Contains(get.Body.String(), `"status":"RUNNING"`) {
		t.Fatalf("get = %d %s", get.Code, get.Body.String())
	}

	runner.getErr = errSyncRunNotFound
	missing := httptest.NewRecorder()
	application.Handler().ServeHTTP(missing, httptest.NewRequest(http.MethodGet, "/v1/admin/sync-runs/missing", nil))
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing = %d %s", missing.Code, missing.Body.String())
	}
}

func TestAdminSyncConflictFailureAndCORSPreflight(t *testing.T) {
	runner := &syncRunnerStub{startErr: syncConflictError{ActiveRun: SyncRun{
		ID: "10000000-0000-4000-8000-000000000001", Type: SyncHistoryBackfill,
		Status: "RUNNING", Parameters: map[string]interface{}{}, Summary: map[string]interface{}{},
	}}}
	application := newAdminTestApp(runner)
	conflict := httptest.NewRecorder()
	application.Handler().ServeHTTP(conflict, httptest.NewRequest(http.MethodPost, "/v1/admin/sync/history", nil))
	if conflict.Code != http.StatusConflict || !strings.Contains(conflict.Body.String(), `"active_run"`) {
		t.Fatalf("conflict = %d %s", conflict.Code, conflict.Body.String())
	}

	runner.startErr = errors.New("database unavailable")
	failure := httptest.NewRecorder()
	application.Handler().ServeHTTP(failure, httptest.NewRequest(http.MethodPost, "/v1/admin/sync/history", nil))
	if failure.Code != http.StatusInternalServerError {
		t.Fatalf("failure = %d %s", failure.Code, failure.Body.String())
	}

	preflightRequest := httptest.NewRequest(http.MethodOptions, "/v1/admin/sync/all", nil)
	preflightRequest.Header.Set("Origin", "http://127.0.0.1:3000")
	preflightRequest.Header.Set("Access-Control-Request-Method", http.MethodPost)
	preflight := httptest.NewRecorder()
	application.Handler().ServeHTTP(preflight, preflightRequest)
	if preflight.Code != http.StatusNoContent || preflight.Header().Get("Access-Control-Allow-Methods") != "GET, POST, OPTIONS" {
		t.Fatalf("preflight = %d headers=%v", preflight.Code, preflight.Header())
	}
}
