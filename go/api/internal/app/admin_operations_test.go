package app

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/jackc/pgx/v5"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type operationsRunnerStub struct {
	syncRunnerStub
	calls int
	fail  error
}

func (runner *operationsRunnerStub) Operations(context.Context, string, OperationPage) (OperationView, error) {
	runner.calls++
	return OperationView{Domain: "providers", Items: []json.RawMessage{json.RawMessage(`{"provider":"fotmob"}`)}}, runner.fail
}
func (runner *operationsRunnerStub) WorkItems(context.Context, WorkFilters) (WorkPage, error) {
	runner.calls++
	return WorkPage{Items: []WorkItem{}}, runner.fail
}
func (runner *operationsRunnerStub) WorkItem(context.Context, string) (WorkItem, error) {
	runner.calls++
	return WorkItem{ID: "00000000-0000-4000-8000-000000000001", State: "BLOCKED"}, runner.fail
}
func (runner *operationsRunnerStub) ControlWork(context.Context, string, string) (WorkItem, error) {
	runner.calls++
	return WorkItem{ID: "00000000-0000-4000-8000-000000000001", State: "PENDING"}, runner.fail
}

func TestOperationsRoutesRetainAdminAccess(t *testing.T) {
	for _, path := range []string{"/v1/admin/operations/providers", "/v1/admin/work", "/v1/admin/work/00000000-0000-4000-8000-000000000001"} {
		runner := &operationsRunnerStub{}
		request := httptest.NewRequest(http.MethodGet, path, nil)
		response := httptest.NewRecorder()
		newAdminTestApp(runner).Handler().ServeHTTP(response, request)
		if response.Code != http.StatusForbidden || runner.calls != 0 {
			t.Fatalf("unprotected route: %d calls=%d", response.Code, runner.calls)
		}
		request = localAdminTestRequest(http.MethodGet, path, nil)
		response = httptest.NewRecorder()
		newAdminTestApp(runner).Handler().ServeHTTP(response, request)
		if response.Code != http.StatusOK || runner.calls != 1 {
			t.Fatalf("protected read: %d %s", response.Code, response.Body)
		}
	}
}

func TestOperationsInputsAreValidatedBeforeStorage(t *testing.T) {
	paths := []string{"/v1/admin/operations/unknown", "/v1/admin/work?state=ANY_SQL", "/v1/admin/work?page_size=101", "/v1/admin/work?page=9223372036854775807&page_size=100", "/v1/admin/work/not-a-uuid"}
	for _, path := range paths {
		runner := &operationsRunnerStub{}
		response := httptest.NewRecorder()
		newAdminTestApp(runner).Handler().ServeHTTP(response, localAdminTestRequest(http.MethodGet, path, nil))
		if response.Code != http.StatusBadRequest || runner.calls != 0 {
			t.Fatalf("invalid input %s: %d calls=%d", path, response.Code, runner.calls)
		}
	}
}

func TestWorkActionsRetainSecurityAndStrictEmptyBody(t *testing.T) {
	for _, action := range []string{"cancel", "retry"} {
		path := "/v1/admin/work/00000000-0000-4000-8000-000000000001/" + action
		runner := &operationsRunnerStub{}
		for _, body := range []string{`{"force":true}`, `{} {}`, `null`, `[]`} {
			request := localAdminTestRequest(http.MethodPost, path, strings.NewReader(body))
			request.Header.Set("Content-Type", "application/json")
			response := httptest.NewRecorder()
			newAdminTestApp(runner).Handler().ServeHTTP(response, request)
			if response.Code != http.StatusBadRequest || runner.calls != 0 {
				t.Fatalf("invalid mutation body: %d %s", response.Code, response.Body)
			}
		}
		request := localAdminTestRequest(http.MethodPost, path, strings.NewReader(`{}`))
		request.Header.Set("Content-Type", "application/json")
		response := httptest.NewRecorder()
		newAdminTestApp(runner).Handler().ServeHTTP(response, request)
		if response.Code != http.StatusAccepted || runner.calls != 1 {
			t.Fatalf("mutation response: %d %s", response.Code, response.Body)
		}
	}
}

func TestOperationsErrorsDoNotExposeStorageDetails(t *testing.T) {
	runner := &operationsRunnerStub{fail: errors.New("password=secret internal SQL")}
	response := httptest.NewRecorder()
	newAdminTestApp(runner).Handler().ServeHTTP(response, localAdminTestRequest(http.MethodGet, "/v1/admin/work", nil))
	if response.Code != http.StatusInternalServerError || strings.Contains(response.Body.String(), "secret") {
		t.Fatalf("unsafe error: %d %s", response.Code, response.Body)
	}
}

func TestOperationsWorkDiagnosticsOmitLeaseTokenAndRedactSecrets(t *testing.T) {
	item, err := decodeWork([]byte(`{"work_id":"id","lease_token":"publication-right","last_error_message":"Bearer secret-one api_key=secret-two&ok=1 password=secret-three postgres://user:secret-four@db/name"}`))
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(item)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{"publication-right", "secret-one", "secret-two", "secret-three", "secret-four", "lease_token"} {
		if strings.Contains(string(raw), secret) {
			t.Fatalf("diagnostic secret exposed: %s", raw)
		}
	}
	if !strings.Contains(string(raw), "[REDACTED]") || !strings.Contains(string(raw), "ok=1") {
		t.Fatalf("diagnostic lost context: %s", raw)
	}
}

func TestOperationsR3UsesTrackedOwnerState(t *testing.T) {
	payload := `{"contract":"ProjectStatusV2","mvp_product":{"audit_remediation":{"current_phase":"R3_DEFERRED_ARCHITECTURE_MIGRATION","blocked_findings":["MF-AUD-0009"],"research_execution_authorized":false,"status":"IN_PROGRESS"}}}`
	root := t.TempDir()
	path := filepath.Join(root, "docs", "project-status.json")
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(payload), 0600); err != nil {
		t.Fatal(err)
	}
	application := newAdminTestApp(&syncRunnerStub{})
	application.config.RepoRoot = root
	response := httptest.NewRecorder()
	application.Handler().ServeHTTP(response, localAdminTestRequest(http.MethodGet, "/v1/admin/operations/r3-audit", nil))
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), "MF-AUD-0009") || !strings.Contains(response.Body.String(), "R3_DEFERRED_ARCHITECTURE_MIGRATION") {
		t.Fatalf("R3 owner state: %d %s", response.Code, response.Body)
	}
	t.Logf("OPENAPI OperationView %s", strings.TrimSpace(response.Body.String()))
	after, err := os.ReadFile(path)
	if err != nil || string(after) != payload {
		t.Fatal("audit view changed owner state")
	}
	for _, bad := range []string{`{}`, `{"contract":"ProjectStatusV2","mvp_product":{"audit_remediation":null}}`, `{"contract":"Other"}`} {
		if _, err := decodeProjectAudit([]byte(bad)); err == nil {
			t.Fatalf("invalid project state accepted: %s", bad)
		}
	}
}

func TestOperationsUnavailableAndControlConflictResponses(t *testing.T) {
	for _, check := range []struct {
		err  error
		want int
	}{
		{errProductUnavailable, http.StatusServiceUnavailable}, {pgx.ErrNoRows, http.StatusNotFound},
		{errWorkControlConflict, http.StatusConflict}, {context.DeadlineExceeded, http.StatusGatewayTimeout},
		{errSyncRunNotRetryable, http.StatusConflict}, {errSyncAlreadyRunning, http.StatusConflict},
	} {
		runner := &operationsRunnerStub{fail: check.err}
		response := httptest.NewRecorder()
		newAdminTestApp(runner).Handler().ServeHTTP(response, localAdminTestRequest(http.MethodGet, "/v1/admin/work", nil))
		if response.Code != check.want {
			t.Fatalf("error %v status %d", check.err, response.Code)
		}
	}
}
