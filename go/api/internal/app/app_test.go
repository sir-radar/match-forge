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
)

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
	t.Setenv("API_ADDR", "missing-port")

	_, err := ConfigFromEnv("test")

	if err == nil || !strings.Contains(err.Error(), "API_ADDR must be host:port") {
		t.Fatalf("error = %v, want API_ADDR validation error", err)
	}
}

func TestConfigFromEnvRejectsNonPositiveDuration(t *testing.T) {
	t.Setenv("DEPENDENCY_TIMEOUT", "0s")

	_, err := ConfigFromEnv("test")

	if err == nil || err.Error() != "DEPENDENCY_TIMEOUT must be a positive duration" {
		t.Fatalf("error = %v, want positive duration validation error", err)
	}
}
