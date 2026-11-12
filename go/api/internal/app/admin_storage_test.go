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
