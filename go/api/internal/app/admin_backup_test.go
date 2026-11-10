package app

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"reflect"
	"strings"
	"testing"
	"time"
)

type backupRunnerStub struct {
	syncRunnerStub
	availability BackupAvailability
}

func (runner *backupRunnerStub) BackupView(context.Context, bool) (BackupView, error) {
	return BackupView{Availability: runner.availability, Runs: []SyncRun{}, ReminderDue: true}, nil
}
func TestBackupRequiresConfirmationOriginAndSuccessfulPreflight(t *testing.T) {
	const body = `{"request_id":"10000000-0000-4000-8000-000000000001","confirmed":true}`
	for _, item := range []struct {
		origin, body, state string
		status              int
	}{
		{"http://evil.invalid", body, "READY", 403},
		{"http://127.0.0.1:3000", `{"confirmed":false}`, "READY", 400},
		{"http://127.0.0.1:3000", body, "DISCONNECTED", 409},
		{"http://127.0.0.1:3000", body, "READY", 202},
	} {
		runner := &backupRunnerStub{availability: BackupAvailability{State: item.state, Message: "Connect enrolled drive"}}
		runner.getErr = errSyncRunNotFound
		application := newAdminTestApp(runner)
		request := httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8080/v1/admin/backup", strings.NewReader(item.body))
		request.RemoteAddr = "127.0.0.1:12345"
		request.Header.Set("Origin", item.origin)
		request.Header.Set("Content-Type", "application/json")
		response := httptest.NewRecorder()
		application.Handler().ServeHTTP(response, request)
		if response.Code != item.status {
			t.Fatalf("state %s: %d: %s", item.state, response.Code, response.Body.String())
		}
		if item.status != 202 && len(runner.started) != 0 {
			t.Fatal("failed preflight started a backup")
		}
		if item.status == 202 && (len(runner.started) != 1 || runner.started[0].Type != SyncManualBackup) {
			t.Fatal("wrong manual action")
		}
	}
}

func TestBackupSummaryRequiresIndependentVerificationFields(t *testing.T) {
	good := map[string]any{"status": "VERIFIED", "verified": true, "snapshot_id": strings.Repeat("a", 64), "verified_at": "2026-11-10T11:00:00Z", "captured_at": "2026-11-10T10:55:00Z"}
	payload, _ := json.Marshal(good)
	if !validBackupSummary(payload) {
		t.Fatal("valid verified summary rejected")
	}
	for _, field := range []string{"verified", "snapshot_id", "verified_at", "captured_at"} {
		changed := map[string]any{}
		for key, value := range good {
			if key != field {
				changed[key] = value
			}
		}
		payload, _ = json.Marshal(changed)
		if validBackupSummary(payload) {
			t.Fatalf("missing %s accepted", field)
		}
	}
	if validBackupSummary([]byte(`{"status":"CAPTURED","verified":false}`)) {
		t.Fatal("copied bytes were labeled verified")
	}
}

func TestBackupSharedFixtureMatchesGoTransport(t *testing.T) {
	payload, err := os.ReadFile("../../../../web/test-fixtures/backup-status.json")
	if err != nil {
		t.Fatal(err)
	}
	var view BackupView
	if err = json.Unmarshal(payload, &view); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(view)
	if err != nil {
		t.Fatal(err)
	}
	var before, after any
	if err = json.Unmarshal(payload, &before); err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(encoded, &after); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(before, after) {
		t.Fatal("Go backup response drifted from shared transport fixture")
	}
}

func TestBackupReminderUsesVerifiedTimeAndThirtyDays(t *testing.T) {
	verified := time.Date(2026, 10, 1, 12, 0, 0, 0, time.UTC)
	run := SyncRun{Status: "SUCCEEDED", Summary: map[string]interface{}{"verified": true, "verified_at": verified.Format(time.RFC3339), "captured_at": verified.Add(-time.Minute).Format(time.RFC3339)}}
	for _, elapsed := range []time.Duration{30*24*time.Hour - time.Second, 30 * 24 * time.Hour, 31 * 24 * time.Hour} {
		view := BackupView{}
		if err := applyBackupReminder(&view, run, verified.Add(elapsed)); err != nil {
			t.Fatal(err)
		}
		if view.ReminderDue != (elapsed >= 30*24*time.Hour) {
			t.Fatalf("wrong reminder at %v", elapsed)
		}
		if *view.NextDueAt != verified.Add(30*24*time.Hour) {
			t.Fatal("reminder date changed without new verified backup")
		}
		if *view.BackupAgeSeconds != int64(elapsed.Seconds())+60 {
			t.Fatal("data-loss age used verification time instead of the earlier snapshot")
		}
	}
	if applyBackupReminder(&BackupView{}, run, verified.Add(-time.Second)) == nil {
		t.Fatal("future verified timestamp accepted")
	}
}

func TestBackupPrivateDiagnosticsStayInProtectedLog(t *testing.T) {
	logFile, err := os.CreateTemp(t.TempDir(), "backup-log-")
	if err != nil {
		t.Fatal(err)
	}
	defer logFile.Close()
	if _, err = logFile.WriteString(`{"status":"RECOVERY_DIAGNOSTIC","private_dependency_detail":"/private/owner/source.json"}` + "\n"); err != nil {
		t.Fatal(err)
	}
	summary, err := syncCommandSummary(`{"backup":true,"status":"FAILED","message":"Registered file dependencies are incomplete"}`, errors.New("process failed"), logFile)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(summary)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(payload), "/private/") {
		t.Fatal("protected dependency path leaked in API summary")
	}
}
