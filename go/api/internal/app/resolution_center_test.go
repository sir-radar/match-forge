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
func TestResolutionStrictReadInputs(t *testing.T) {
	runner := &resolutionStub{}
	application := newAdminTestApp(runner)
	var response *httptest.ResponseRecorder
	for _, path := range []string{"/v1/admin/resolution/not-supported", "/v1/admin/resolution/identity?page_size=101", "/v1/admin/resolution/identity?q=" + strings.Repeat("a", 257)} {
		response = httptest.NewRecorder()
		application.Handler().ServeHTTP(response, localAdminTestRequest("GET", path, nil))
		if response.Code != http.StatusBadRequest || runner.calls != 0 {
			t.Fatalf("input accepted %s", path)
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

func TestResolutionWritesRequireOwnerCredentialBeyondOrigin(t *testing.T) {
	runner := &resolutionStub{}
	application := newAdminTestApp(runner)
	body := `{"case_key":"team:00000000-0000-4000-8000-000000000001","action":"REJECT","reason":"reviewed","approved":true,"request_id":"00000000-0000-4000-8000-000000000002","evidence_version":"` + strings.Repeat("a", 64) + `"}`
	request := localAdminTestRequest("POST", "/v1/admin/resolution/apply", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusForbidden || runner.calls != 0 {
		t.Fatalf("origin authorized sensitive write: %d", response.Code)
	}
	application.config.AdminCLIToken = "owner-secret"
	request = localAdminTestRequest("POST", "/v1/admin/resolution/apply", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer owner-secret")
	response = httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != 200 || runner.calls != 1 || !strings.HasPrefix(runner.input.Actor, "owner:") {
		t.Fatalf("owner request: %d %s", response.Code, response.Body)
	}
	if strings.Contains(runner.input.Actor, "secret") {
		t.Fatal("credential exposed")
	}
}

func TestResolutionBatchRequiresOwnerAndBoundedRequests(t *testing.T) {
	runner := &resolutionStub{}
	application := newAdminTestApp(runner)
	decision := `{"case_key":"team:00000000-0000-4000-8000-000000000001","action":"BLOCK","reason":"review","approved":true,"request_id":"00000000-0000-4000-8000-000000000002","evidence_version":"` + strings.Repeat("a", 64) + `"}`
	request := localAdminTestRequest("POST", "/v1/admin/resolution/batch-apply", strings.NewReader(`{"requests":[`+decision+`]}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusForbidden || runner.calls != 0 {
		t.Fatal("Origin authorized a batch")
	}
	application.config.AdminCLIToken = "owner-secret"
	request = localAdminTestRequest("POST", "/v1/admin/resolution/batch-apply", strings.NewReader(`{"requests":[`+decision+`]}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer owner-secret")
	response = httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK || runner.input.Operation != "batch_apply" || len(runner.input.Requests) != 1 {
		t.Fatal("owner batch failed")
	}
}
func TestResolutionBatchRejectsOverflow(t *testing.T) {
	runner := &resolutionStub{}
	application := newAdminTestApp(runner)
	request := localAdminTestRequest("POST", "/v1/admin/resolution/batch-preview", strings.NewReader(`{"requests":[`+strings.Repeat(`{},`, 20)+`{}]}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest || runner.calls != 0 {
		t.Fatal("unbounded batch accepted")
	}
}
