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
	stopped  []string
	retried  []string
	runs     []SyncRun
	startErr error
	getErr   error
}

func (runner *syncRunnerStub) Stop(_ context.Context, id string) (SyncRun, error) {
	runner.stopped = append(runner.stopped, id)
	return SyncRun{ID: id, Type: SyncMVP, Status: "CANCELLED", Parameters: map[string]interface{}{}, Summary: map[string]interface{}{}}, nil
}
func (runner *syncRunnerStub) Retry(_ context.Context, id string) (SyncRun, error) {
	runner.retried = append(runner.retried, id)
	return SyncRun{ID: "10000000-0000-4000-8000-000000000002", Type: SyncMVP, Status: "QUEUED", Parameters: map[string]interface{}{}, Summary: map[string]interface{}{}}, nil
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

func TestCommandSyncRunnerShutdownCancelsAndWaitsForWorkers(t *testing.T) {
	workerContext, cancelWorker := context.WithCancel(context.Background())
	control := &syncRunControl{cancel: cancelWorker, done: make(chan struct{})}
	runner := &CommandSyncRunner{active: map[string]*syncRunControl{"run-1": control}}
	go func() {
		<-workerContext.Done()
		close(control.done)
	}()

	shutdownContext, cancelShutdown := context.WithTimeout(context.Background(), time.Second)
	defer cancelShutdown()
	runner.Shutdown(shutdownContext)

	if workerContext.Err() != context.Canceled {
		t.Fatalf("worker context error = %v, want canceled", workerContext.Err())
	}
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
		{path: "/v1/admin/sync/fotmob", want: SyncFotMob},
		{path: "/v1/admin/sync/pitchapi", want: SyncPitchAPI},
		{path: "/v1/admin/sync/all", want: SyncAllData},
	}
	for _, test := range tests {
		t.Run(string(test.want), func(t *testing.T) {
			runner := &syncRunnerStub{}
			request := localAdminTestRequest(http.MethodPost, test.path, strings.NewReader(`{"date":"2026-09-30"}`))
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
	request := localAdminTestRequest(
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

func TestOperationalCommandArgsIncludeRangeAndProviderCompetition(t *testing.T) {
	args, err := syncCommandArgs(SyncRequest{
		Type: SyncPitchAPI, Date: "2026-10-09", FromDate: "2026-10-01",
		Competition: "l_0bfbkO",
	})
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(args, " ")
	for _, expected := range []string{
		"pitchapi-sync", "--date 2026-10-09", "--from-date 2026-10-01",
		"--competition l_0bfbkO",
	} {
		if !strings.Contains(joined, expected) {
			t.Fatalf("args = %q; missing %q", joined, expected)
		}
	}
}

func TestContextReportCommandUsesDedicatedCLI(t *testing.T) {
	args, err := syncCommandArgs(SyncRequest{Type: SyncContextReports})
	if err != nil {
		t.Fatal(err)
	}
	if got := strings.Join(args, " "); !strings.Contains(got, "refresh-context-reports") {
		t.Fatalf("context report command = %q", got)
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
		"status":          "COMPLETED_WITH_ERRORS",
		"failure_reasons": map[string]interface{}{"mvp": "API-Football request limit reached"},
	})
	if status != "FAILED" {
		t.Fatalf("status = %q", status)
	}
	if message == nil || *message != "one or more data synchronization operations failed; see the run summary for details" {
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
		context.Background(),
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

func TestRunCommandCancellationStopsProcessGroup(t *testing.T) {
	logFile, err := os.CreateTemp(t.TempDir(), "sync-run-*.log")
	if err != nil {
		t.Fatal(err)
	}
	defer logFile.Close()
	ctx, cancel := context.WithCancel(context.Background())
	runner := &CommandSyncRunner{repoRoot: t.TempDir()}
	done := make(chan error, 1)
	go func() {
		_, runErr := runner.runCommand(
			ctx, "run-id", []string{"/bin/sh", "-c", "sleep 30"}, logFile,
		)
		done <- runErr
	}()
	time.Sleep(50 * time.Millisecond)
	cancel()
	select {
	case runErr := <-done:
		if runErr == nil {
			t.Fatal("expected cancelled command error")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("cancelled command did not stop")
	}
}

func TestAdminSyncStopAndRetryRoutes(t *testing.T) {
	runner := &syncRunnerStub{}
	application := newAdminTestApp(runner)
	for _, test := range []struct {
		path   string
		status int
	}{
		{path: "/v1/admin/sync-runs/run-one/stop", status: http.StatusOK},
		{path: "/v1/admin/sync-runs/run-one/retry", status: http.StatusAccepted},
	} {
		response := httptest.NewRecorder()
		application.Handler().ServeHTTP(response, localAdminTestRequest(http.MethodPost, test.path, nil))
		if response.Code != test.status {
			t.Fatalf("%s response = %d %s", test.path, response.Code, response.Body.String())
		}
	}
	if len(runner.stopped) != 1 || runner.stopped[0] != "run-one" {
		t.Fatalf("stopped = %v", runner.stopped)
	}
	if len(runner.retried) != 1 || runner.retried[0] != "run-one" {
		t.Fatalf("retried = %v", runner.retried)
	}
}

func TestRetryReconstructsRequestAndRecordsLineage(t *testing.T) {
	requestedDate := "2026-10-11"
	run := SyncRun{
		ID: "10000000-0000-4000-8000-000000000001", Type: SyncPitchAPI,
		Status: "FAILED", RequestedDate: &requestedDate,
		Parameters: map[string]interface{}{"from_date": "2026-10-09", "competition": "l_0bfbkO"},
	}
	request := syncRequestFromRun(run)
	parameters := syncParameters(request)
	if parameters["retry_of_run_id"] != run.ID || request.FromDate != "2026-10-09" || request.Competition != "l_0bfbkO" {
		t.Fatalf("request = %+v parameters = %+v", request, parameters)
	}
}

func TestAdminSyncListGetAndErrors(t *testing.T) {
	runner := &syncRunnerStub{runs: []SyncRun{{ID: "one", Type: SyncMVP, Status: "SUCCEEDED"}}}
	application := newAdminTestApp(runner)
	list := httptest.NewRecorder()
	application.Handler().ServeHTTP(list, localAdminTestRequest(http.MethodGet, "/v1/admin/sync-runs", nil))
	if list.Code != http.StatusOK || !strings.Contains(list.Body.String(), `"historical_matches":123`) {
		t.Fatalf("list = %d %s", list.Code, list.Body.String())
	}
	if !strings.Contains(list.Body.String(), `"provider_configuration"`) {
		t.Fatalf("list omits provider configuration: %s", list.Body.String())
	}
	get := httptest.NewRecorder()
	application.Handler().ServeHTTP(get, localAdminTestRequest(http.MethodGet, "/v1/admin/sync-runs/one", nil))
	if get.Code != http.StatusOK || !strings.Contains(get.Body.String(), `"status":"RUNNING"`) {
		t.Fatalf("get = %d %s", get.Code, get.Body.String())
	}

	runner.getErr = errSyncRunNotFound
	missing := httptest.NewRecorder()
	application.Handler().ServeHTTP(missing, localAdminTestRequest(http.MethodGet, "/v1/admin/sync-runs/missing", nil))
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
	application.Handler().ServeHTTP(conflict, localAdminTestRequest(http.MethodPost, "/v1/admin/sync/history", nil))
	if conflict.Code != http.StatusConflict || !strings.Contains(conflict.Body.String(), `"active_run"`) {
		t.Fatalf("conflict = %d %s", conflict.Code, conflict.Body.String())
	}

	runner.startErr = errors.New("database unavailable")
	failure := httptest.NewRecorder()
	application.Handler().ServeHTTP(failure, localAdminTestRequest(http.MethodPost, "/v1/admin/sync/history", nil))
	if failure.Code != http.StatusInternalServerError {
		t.Fatalf("failure = %d %s", failure.Code, failure.Body.String())
	}

	preflightRequest := localAdminTestRequest(http.MethodOptions, "/v1/admin/sync/all", nil)
	preflightRequest.Header.Set("Origin", "http://127.0.0.1:3000")
	preflightRequest.Header.Set("Access-Control-Request-Method", http.MethodPost)
	preflight := httptest.NewRecorder()
	application.Handler().ServeHTTP(preflight, preflightRequest)
	if preflight.Code != http.StatusNoContent || preflight.Header().Get("Access-Control-Allow-Methods") != "GET, POST, OPTIONS" {
		t.Fatalf("preflight = %d headers=%v", preflight.Code, preflight.Header())
	}
}

func localAdminTestRequest(method, path string, body io.Reader) *http.Request {
	request := httptest.NewRequest(method, path, body)
	request.Host = "127.0.0.1:8080"
	request.RemoteAddr = "127.0.0.1:50000"
	request.Header.Set("Origin", "http://127.0.0.1:3000")
	request.Header.Set("Content-Type", "application/json")
	return request
}

func TestAdminAccessRejectsUnauthorizedMutations(t *testing.T) {
	for _, path := range []string{"/v1/admin/sync/mvp", "/v1/admin/sync-runs/run-one/stop", "/v1/admin/sync-runs/run-one/retry"} {
		for _, invalid := range []string{"origin", "host", "peer", "content-type", "origin-less"} {
			t.Run(path+"/"+invalid, func(t *testing.T) {
				runner := &syncRunnerStub{}
				request := localAdminTestRequest(http.MethodPost, path, strings.NewReader(`{}`))
				expected := http.StatusForbidden
				switch invalid {
				case "origin":
					request.Header.Set("Origin", "https://untrusted.example")
				case "host":
					request.Host = "untrusted.example:8080"
				case "peer":
					request.RemoteAddr = "192.0.2.1:50000"
				case "origin-less":
					request.Header.Del("Origin")
				case "content-type":
					request.Header.Set("Content-Type", "text/plain")
					expected = http.StatusUnsupportedMediaType
				}
				response := httptest.NewRecorder()
				newAdminTestApp(runner).Handler().ServeHTTP(response, request)
				if response.Code != expected {
					t.Fatalf("status = %d, want %d", response.Code, expected)
				}
				if len(runner.started)+len(runner.stopped)+len(runner.retried) != 0 {
					t.Fatal("unauthorized mutation invoked runner")
				}
			})
		}
	}
}

func TestOriginlessAdminRequiresConstantTimeValidatedCredential(t *testing.T) {
	for _, authorization := range []string{"", "Bearer wrong", "Basic approved-secret", "Bearer approved-secret"} {
		t.Run(authorization, func(t *testing.T) {
			runner := &syncRunnerStub{}
			application := newAdminTestApp(runner)
			application.config.AdminCLIToken = "approved-secret"
			request := localAdminTestRequest(http.MethodPost, "/v1/admin/sync/mvp", strings.NewReader(`{}`))
			request.Header.Del("Origin")
			request.Header.Set("Authorization", authorization)
			response := httptest.NewRecorder()
			application.Handler().ServeHTTP(response, request)
			if authorization == "Bearer approved-secret" {
				if response.Code != http.StatusAccepted || len(runner.started) != 1 {
					t.Fatalf("authorized response: %d", response.Code)
				}
			} else if response.Code != http.StatusForbidden || len(runner.started) != 0 {
				t.Fatal("invalid credential accepted")
			}
		})
	}
}

func TestNonLoopbackAdminExposureIsAlwaysDenied(t *testing.T) {
	runner := &syncRunnerStub{}
	application := newAdminTestApp(runner)
	application.config.Address = "0.0.0.0:8080"
	request := localAdminTestRequest(http.MethodPost, "/v1/admin/sync/mvp", strings.NewReader(`{}`))
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusForbidden || len(runner.started) != 0 {
		t.Fatal("non-loopback admin exposed")
	}
}

func TestAdministrativeReadsRequireApprovedLocalAccess(t *testing.T) {
	for _, origin := range []string{"", "https://untrusted.example", "http://127.0.0.1:3000"} {
		request := localAdminTestRequest(http.MethodGet, "/v1/admin/sync-runs", nil)
		request.Header.Del("Content-Type")
		request.Header.Set("Origin", origin)
		response := httptest.NewRecorder()
		newAdminTestApp(&syncRunnerStub{}).Handler().ServeHTTP(response, request)
		want := http.StatusForbidden
		if origin == "http://127.0.0.1:3000" {
			want = http.StatusOK
		}
		if response.Code != want {
			t.Fatalf("origin %q: status %d, want %d", origin, response.Code, want)
		}
	}
	application := newAdminTestApp(&syncRunnerStub{})
	application.config.AdminCLIToken = "approved-secret"
	request := localAdminTestRequest(http.MethodGet, "/v1/admin/sync-runs", nil)
	request.Header.Del("Origin")
	request.Header.Del("Content-Type")
	request.Header.Set("Authorization", "Bearer approved-secret")
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("authorized origin-less read: status %d", response.Code)
	}
}
