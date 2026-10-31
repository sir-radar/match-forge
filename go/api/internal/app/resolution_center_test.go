package app

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type resolutionStub struct {
	syncRunnerStub
	calls int
	input resolutionRequest
}

func (runner *resolutionStub) Resolution(_ context.Context, input resolutionRequest) (resolutionResult, error) {
	runner.calls++
	runner.input = input
	return resolutionResult{StatusCode: 200, Data: json.RawMessage(`{"items":[]}`)}, nil
}
func TestResolutionReadProtectionAndStrictInputs(t *testing.T) {
	runner := &resolutionStub{}
	application := newAdminTestApp(runner)
	request := httptest.NewRequest("GET", "/v1/admin/resolution/identity", nil)
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusForbidden || runner.calls != 0 {
		t.Fatal("unprotected read")
	}
	response = httptest.NewRecorder()
	application.Handler().ServeHTTP(response, localAdminTestRequest("GET", "/v1/admin/resolution/identity?q=Brentford", nil))
	if response.Code != http.StatusOK || runner.calls != 1 || runner.input.Query["q"] != "Brentford" {
		t.Fatalf("read failed %d", response.Code)
	}
	if response.Header().Get("Cache-Control") != "no-store" {
		t.Fatal("private response is cacheable")
	}
}
func TestResolutionInputsAndReadOnlyRoutes(t *testing.T) {
	runner := &resolutionStub{}
	application := newAdminTestApp(runner)
	var request *http.Request
	var response *httptest.ResponseRecorder
	for _, path := range []string{"/v1/admin/resolution/not-supported", "/v1/admin/resolution/identity?page_size=101", "/v1/admin/resolution/identity?q=" + strings.Repeat("a", 257)} {
		response = httptest.NewRecorder()
		application.Handler().ServeHTTP(response, localAdminTestRequest("GET", path, nil))
		if response.Code != http.StatusBadRequest || runner.calls != 0 {
			t.Fatalf("input accepted %s", path)
		}
	}
	for _, path := range []string{"/v1/admin/resolution/apply", "/v1/admin/resolution/preview"} {
		request = localAdminTestRequest("POST", path, strings.NewReader(`{}`))
		request.Header.Set("Content-Type", "application/json")
		response = httptest.NewRecorder()
		application.Handler().ServeHTTP(response, request)
		if response.Code != http.StatusMethodNotAllowed || runner.calls != 0 {
			t.Fatalf("read-only route accepted POST: %d", response.Code)
		}
	}
}

func TestResolutionOutputIsBounded(t *testing.T) {
	var output resolutionOutput
	_, err := io.Copy(&output, strings.NewReader(strings.Repeat("x", 2*1024*1024+1)))
	if err == nil || output.buffer.Len() > 2*1024*1024 {
		t.Fatal("response cap bypassed")
	}
}
func TestResolutionDatabaseBridge(t *testing.T) {
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("integration database required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	root, err := filepath.Abs("../../../..")
	if err != nil {
		t.Fatal(err)
	}
	runner := NewCommandSyncRunner(ctx, pool, root, slog.New(slog.NewTextHandler(io.Discard, nil)))
	result, err := runner.Resolution(ctx, resolutionRequest{Operation: "read", View: "identity", Query: map[string]any{"page": 1, "page_size": 20}})
	if err != nil || result.StatusCode != 200 || !json.Valid(result.Data) {
		t.Fatalf("real bridge: %v status=%d", err, result.StatusCode)
	}
}
