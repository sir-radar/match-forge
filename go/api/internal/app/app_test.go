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
		{name: "version", path: "/version", statusCode: http.StatusOK, body: `{"version":"test-version"}`},
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

func TestConfigFromEnvRequiresDatabaseURL(t *testing.T) {
	t.Setenv("DATABASE_URL", "")

	_, err := ConfigFromEnv("test")

	if err == nil || err.Error() != "DATABASE_URL is required" {
		t.Fatalf("error = %v, want required DATABASE_URL error", err)
	}
}
