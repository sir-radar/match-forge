package app

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type scheduleRunner struct {
	requests chan SyncRequest
}

type forecastScheduleRunner struct {
	scheduleRunner
	pending bool
}

type contextReportScheduleRunner struct {
	scheduleRunner
	pending bool
}

func (runner forecastScheduleRunner) PendingForecastRefresh(context.Context) (bool, error) {
	return runner.pending, nil
}

func (runner contextReportScheduleRunner) PendingPublicReports(context.Context) (bool, error) {
	return runner.pending, nil
}

func (runner scheduleRunner) Start(_ context.Context, request SyncRequest) (SyncRun, error) {
	runner.requests <- request
	return SyncRun{}, nil
}
func (scheduleRunner) Stop(context.Context, string) (SyncRun, error)  { return SyncRun{}, nil }
func (scheduleRunner) Retry(context.Context, string) (SyncRun, error) { return SyncRun{}, nil }
func (scheduleRunner) List(context.Context) ([]SyncRun, error)        { return nil, nil }
func (scheduleRunner) Get(context.Context, string) (SyncRun, error)   { return SyncRun{}, nil }
func (scheduleRunner) Coverage(context.Context) (Coverage, error)     { return Coverage{}, nil }

func TestOperationalScheduleStartsEveryEnabledProviderWithoutBrowserTraffic(t *testing.T) {
	requests := make(chan SyncRequest, 2)
	application := NewWithSyncRunner(
		Config{OperationalSyncInterval: time.Hour, FotMobEnabled: true, PitchAPIEnabled: true},
		slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, unavailableProductStore{},
		scheduleRunner{requests: requests},
	)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go application.runOperationalSyncSchedule(ctx)

	seen := map[SyncType]bool{}
	for len(seen) < 2 {
		select {
		case request := <-requests:
			seen[request.Type] = true
			if request.Date == "" {
				t.Fatal("scheduled request date is empty")
			}
			lagos := time.FixedZone("Africa/Lagos", 60*60)
			if request.FromDate != time.Now().In(lagos).AddDate(0, 0, -1).Format("2006-01-02") {
				t.Fatalf("scheduled range starts at %q, want yesterday", request.FromDate)
			}
		case <-time.After(time.Second):
			t.Fatalf("scheduled providers = %v, want FotMob and PitchAPI", seen)
		}
	}
	if !seen[SyncFotMob] || !seen[SyncPitchAPI] {
		t.Fatalf("scheduled providers = %v, want FotMob and PitchAPI", seen)
	}
}

func TestSyncLanesSeparateLiveProvidersFromBulkWork(t *testing.T) {
	tests := map[SyncType]string{
		SyncFotMob:          "LIVE_FOTMOB",
		SyncPitchAPI:        "LIVE_PITCHAPI",
		SyncHistoryBackfill: "BULK",
		SyncAllData:         "BULK",
	}
	for syncType, expected := range tests {
		if actual := syncLane(syncType); actual != expected {
			t.Errorf("syncLane(%q) = %q, want %q", syncType, actual, expected)
		}
	}
}

func TestHistoryScheduleRequiresEnablementAndSubmitsBoundedDurableWork(t *testing.T) {
	requests := make(chan SyncRequest, 2)
	application := NewWithSyncRunner(
		Config{HistorySyncInterval: time.Hour, PitchAPIEnabled: true},
		slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, unavailableProductStore{},
		scheduleRunner{requests: requests},
	)
	application.runHistorySyncSchedule(context.Background())
	select {
	case <-requests:
		t.Fatal("disabled history acquisition submitted work")
	default:
	}
	application.config.HistorySyncEnabled = true
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go application.runHistorySyncSchedule(ctx)
	select {
	case request := <-requests:
		if request.Type != SyncHistoryBackfill || !request.ScheduledHistory {
			t.Fatalf("scheduled history request = %+v", request)
		}
		args, err := syncCommandArgs(request)
		if err != nil || !strings.Contains(strings.Join(args, " "), "--scheduled") {
			t.Fatalf("scheduled command = %v, error = %v", args, err)
		}
		retry := syncRequestFromRun(SyncRun{Type: request.Type, Parameters: syncParameters(request)})
		if !retry.ScheduledHistory {
			t.Fatal("durable retry lost scheduled acquisition limits")
		}
	case <-time.After(time.Second):
		t.Fatal("enabled history acquisition did not progress without browser traffic")
	}
}

func TestPendingForecastScheduleUsesDurableBoundedJob(t *testing.T) {
	requests := make(chan SyncRequest, 1)
	application := NewWithSyncRunner(
		Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)),
		readinessStub{}, unavailableProductStore{},
		forecastScheduleRunner{scheduleRunner: scheduleRunner{requests: requests}, pending: true},
	)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go application.runForecastRefreshSchedule(ctx)
	select {
	case request := <-requests:
		if request.Type != SyncForecastRefresh || !request.PendingOnly {
			t.Fatalf("scheduled forecast request = %+v", request)
		}
		args, err := syncCommandArgs(request)
		if err != nil || !strings.Contains(strings.Join(args, " "), "--pending-only") {
			t.Fatalf("scheduled command = %v, error = %v", args, err)
		}
		retry := syncRequestFromRun(SyncRun{Type: request.Type, Parameters: syncParameters(request)})
		if !retry.PendingOnly {
			t.Fatal("durable retry lost pending-only scope")
		}
	case <-time.After(time.Second):
		t.Fatal("pending forecast work did not progress without browser traffic")
	}
}

func TestPendingContextReportScheduleUsesDurableJob(t *testing.T) {
	requests := make(chan SyncRequest, 1)
	application := NewWithSyncRunner(
		Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)),
		readinessStub{}, unavailableProductStore{},
		contextReportScheduleRunner{scheduleRunner: scheduleRunner{requests: requests}, pending: true},
	)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go application.runPublicReportSchedule(ctx)
	select {
	case request := <-requests:
		if request.Type != SyncPublicReports {
			t.Fatalf("scheduled context report request = %+v", request)
		}
		args, err := syncCommandArgs(request)
		if err != nil || !strings.Contains(strings.Join(args, " "), "refresh-public-reports") {
			t.Fatalf("scheduled command = %v, error = %v", args, err)
		}
	case <-time.After(time.Second):
		t.Fatal("pending public reports did not progress without browser traffic")
	}
}

func TestHistoryThroughputRequiresAnObservedSchedulingInterval(t *testing.T) {
	progress := []ProviderHistoryProgress{
		{Pending: 4, Completions24Hours: 2, ObservedSeconds: 3599},
		{Pending: 4, Completions24Hours: 2, ObservedSeconds: 3600},
		{Pending: 4, ObservedSeconds: 3600},
	}
	calculateHistoryThroughput(progress, time.Hour)
	if progress[0].EstimatedDrainHours != nil || progress[2].CompletionsPerHour != nil {
		t.Fatal("unmeasured throughput was estimated")
	}
	if progress[1].CompletionsPerHour == nil || *progress[1].CompletionsPerHour != 2 ||
		progress[1].EstimatedDrainHours == nil || *progress[1].EstimatedDrainHours != 2 {
		t.Fatalf("measured throughput = %+v", progress[1])
	}
}

type readinessStub struct {
	err error
}

func (stub readinessStub) Ready(context.Context) error {
	return stub.err
}

func TestOperationalEndpoints(t *testing.T) {
	tests := []struct {
		name       string
		path       string
		readiness  error
		statusCode int
		body       string
	}{
		{name: "health", path: "/healthz", statusCode: http.StatusOK, body: `{"status":"ok"}`},
		{name: "ready", path: "/readyz", statusCode: http.StatusOK, body: `{"status":"ready"}`},
		{name: "not ready", path: "/readyz", readiness: errors.New("offline"), statusCode: http.StatusServiceUnavailable, body: `{"status":"unavailable"}`},
		{name: "version", path: "/version", statusCode: http.StatusOK, body: `{"code_commit_sha":"unknown","dependency_lock_sha256":"unknown","version":"test-version","worktree_state":"unknown"}`},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			application := New(
				Config{Version: "test-version"},
				slog.New(slog.NewTextHandler(io.Discard, nil)),
				readinessStub{err: test.readiness},
			)
			request := httptest.NewRequest(http.MethodGet, test.path, nil)
			response := httptest.NewRecorder()

			application.Handler().ServeHTTP(response, request)

			if response.Code != test.statusCode {
				t.Fatalf("status = %d, want %d", response.Code, test.statusCode)
			}
			if strings.TrimSpace(response.Body.String()) != test.body {
				t.Fatalf("body = %q, want %q", response.Body.String(), test.body)
			}
			if contentType := response.Header().Get("Content-Type"); contentType != "application/json" {
				t.Fatalf("Content-Type = %q, want application/json", contentType)
			}
		})
	}
}

func TestConfigFromEnvRejectsInvalidAddress(t *testing.T) {
	t.Setenv("DATABASE_URL", "test-database-url")
	t.Setenv("POSTGRES_ADDR", "127.0.0.1:1")
	t.Setenv("REDIS_ADDR", "127.0.0.1:2")
	t.Setenv("API_ADDR", "missing-port")

	_, err := ConfigFromEnv("test")

	if err == nil || !strings.Contains(err.Error(), "API_ADDR must be host:port") {
		t.Fatalf("error = %v, want API_ADDR validation error", err)
	}
}

func TestConfigFromEnvRejectsNonPositiveDuration(t *testing.T) {
	t.Setenv("DATABASE_URL", "test-database-url")
	t.Setenv("POSTGRES_ADDR", "127.0.0.1:1")
	t.Setenv("REDIS_ADDR", "127.0.0.1:2")
	t.Setenv("DEPENDENCY_TIMEOUT", "0s")

	_, err := ConfigFromEnv("test")

	if err == nil || err.Error() != "DEPENDENCY_TIMEOUT must be a positive duration" {
		t.Fatalf("error = %v, want positive duration validation error", err)
	}
}

func TestHistorySyncIntervalCannotExceedApprovedCadence(t *testing.T) {
	for _, value := range []string{"30m", "invalid"} {
		t.Setenv("MATCHFORGE_HISTORY_SYNC_INTERVAL", value)
		if _, err := historySyncIntervalFromEnv(); err == nil {
			t.Fatalf("interval %q was accepted", value)
		}
	}
	t.Setenv("MATCHFORGE_HISTORY_SYNC_INTERVAL", "1h")
	interval, err := historySyncIntervalFromEnv()
	if err != nil || interval != time.Hour {
		t.Fatalf("approved interval = %s, error = %v", interval, err)
	}
}

func TestConfigFromEnvRequiresDatabaseURL(t *testing.T) {
	t.Setenv("DATABASE_URL", "")

	_, err := ConfigFromEnv("test")

	if err == nil || err.Error() != "DATABASE_URL is required" {
		t.Fatalf("error = %v, want required DATABASE_URL error", err)
	}
}
