package app

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type storageStub struct{ syncRunnerStub }

func (*storageStub) StorageView(context.Context) (StorageView, error) {
	return StorageView{State: "EMPTY", Message: "No completed reviews", History: []json.RawMessage{}, Approvals: []json.RawMessage{}}, nil
}

func TestStorageAdminRequiresExistingLocalAuthorization(t *testing.T) {
	app := newAdminTestApp(&storageStub{})
	for _, origin := range []string{"http://evil.invalid", "http://127.0.0.1:3000"} {
		r := httptest.NewRequest(http.MethodGet, "http://127.0.0.1:8080/v1/admin/storage", nil)
		r.RemoteAddr = "127.0.0.1:12345"
		r.Header.Set("Origin", origin)
		w := httptest.NewRecorder()
		app.Handler().ServeHTTP(w, r)
		expected := 200
		if origin == "http://evil.invalid" {
			expected = 403
		}
		if w.Code != expected {
			t.Fatalf("%s: %d", origin, w.Code)
		}
	}
}
func TestStorageAdminRejectsDestructiveAndArbitraryRequests(t *testing.T) {
	runner := &storageStub{}
	app := newAdminTestApp(runner)
	for _, body := range []string{`{"dry_run":false}`, `{"dry_run":true,"path":"/etc"}`, `{"dry_run":true} {"delete":true}`} {
		r := httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8080/v1/admin/storage/reviews", strings.NewReader(body))
		r.RemoteAddr = "127.0.0.1:12345"
		r.Header.Set("Origin", "http://127.0.0.1:3000")
		r.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		app.Handler().ServeHTTP(w, r)
		if w.Code != 400 {
			t.Fatalf("destructive request %s: %d", body, w.Code)
		}
	}
	if len(runner.started) != 0 {
		t.Fatal("invalid body started work")
	}
}

func TestStorageManagementDestructiveRoutesRequireOwnerCredential(t *testing.T) {
	app := newAdminTestApp(&storageStub{})
	bodies := map[string]string{
		"/v1/admin/storage/actions":      `{"action":"DELETE","resource_ids":["` + strings.Repeat("a", 64) + `"],"plan_sha256":"` + strings.Repeat("b", 64) + `","confirmation":"DELETE 1","confirmed":true}`,
		"/v1/admin/storage/dispositions": `{"resource_id":"` + strings.Repeat("a", 64) + `","evidence_sha256":"` + strings.Repeat("b", 64) + `","disposition":"UNIQUE_DATA_NOT_REQUIRED","rationale":"not required at all, really"}`,
		"/v1/admin/storage/protections":  `{"resource_id":"` + strings.Repeat("a", 64) + `","reason":"keep"}`,
	}
	for path, body := range bodies {
		for _, token := range []string{"", "Bearer wrong"} {
			r := httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8080"+path, strings.NewReader(body))
			r.RemoteAddr = "127.0.0.1:12345"
			r.Header.Set("Origin", "http://127.0.0.1:3000")
			r.Header.Set("Content-Type", "application/json")
			if token != "" {
				r.Header.Set("Authorization", token)
			}
			w := httptest.NewRecorder()
			app.Handler().ServeHTTP(w, r)
			if w.Code != http.StatusForbidden {
				t.Fatalf("%s without owner credential: %d", path, w.Code)
			}
		}
	}
	// Read-only management routes report an undeployed migration instead of guessing.
	r := httptest.NewRequest(http.MethodGet, "http://127.0.0.1:8080/v1/admin/storage/resources", nil)
	r.RemoteAddr = "127.0.0.1:12345"
	r.Header.Set("Origin", "http://127.0.0.1:3000")
	w := httptest.NewRecorder()
	app.Handler().ServeHTTP(w, r)
	if w.Code != http.StatusConflict {
		t.Fatalf("resources without manager: %d", w.Code)
	}
}
