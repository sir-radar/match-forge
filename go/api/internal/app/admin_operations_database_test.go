package app

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

func operationDatabaseWork(t *testing.T, pool *pgxpool.Pool, dependencies []string) string {
	t.Helper()
	id, err := newUUID()
	if err != nil {
		t.Fatal(err)
	}
	_, err = pool.Exec(context.Background(), `SELECT football.enqueue_work($1::uuid,'NORMALIZATION',$1::text,
        $2::football.sha256_hex,0,clock_timestamp(),3,60::double precision,600::double precision,
        2::double precision,$3::uuid[],NULL::uuid,0::double precision)`, id, strings.Repeat("a", 64), dependencies)
	if err != nil {
		t.Fatal(err)
	}
	return id
}
func operationDatabaseFail(t *testing.T, pool *pgxpool.Pool, id, classification string) {
	t.Helper()
	_, err := pool.Exec(context.Background(), `WITH claimed AS (
        SELECT * FROM football.claim_work('operations-test',interval '1 minute',
            ARRAY['NORMALIZATION'],ARRAY[$1::uuid]))
        SELECT football.fail_work(work_id,'operations-test',lease_token,generation,$2,
            'TEST_FAILURE','api_key=private-token',clock_timestamp()+interval '1 hour',NULL)
        FROM claimed`, id, classification)
	if err != nil {
		t.Fatal(err)
	}
}
func operationDatabaseResponse(t *testing.T, runner *CommandSyncRunner, path, schema string) []byte {
	t.Helper()
	response := httptest.NewRecorder()
	newAdminTestApp(runner).Handler().ServeHTTP(response, localAdminTestRequest(http.MethodGet, path, nil))
	if response.Code != http.StatusOK {
		t.Fatalf("operational response %s: %d %s", path, response.Code, response.Body)
	}
	t.Logf("OPENAPI %s %s", schema, strings.TrimSpace(response.Body.String()))
	return response.Body.Bytes()
}
func TestOperationsDatabaseViews(t *testing.T) {
	pool := servingDatabasePool(t)
	runner := &CommandSyncRunner{pool: pool}
	for domain, query := range operationQueries {
		payload := operationDatabaseResponse(t, runner, "/v1/admin/operations/"+domain, "OperationView")
		var view OperationView
		if err := json.Unmarshal(payload, &view); err != nil {
			t.Fatal(err)
		}
		if view.Source != query.source || view.Items == nil || view.ObservedAt.IsZero() {
			t.Fatalf("invalid view %s: %+v", domain, view)
		}
	}
}
func readOperationWork(t *testing.T, runner *CommandSyncRunner, id string) WorkItem {
	t.Helper()
	item, err := runner.WorkItem(context.Background(), id)
	if err != nil {
		t.Fatal(err)
	}
	return item
}
func TestOperationsDatabaseWorkDependencies(t *testing.T) {
	pool := servingDatabasePool(t)
	runner := &CommandSyncRunner{pool: pool}
	parent := operationDatabaseWork(t, pool, []string{})
	child := operationDatabaseWork(t, pool, []string{parent})
	item := readOperationWork(t, runner, child)
	if item.DependencyCount != 1 || len(item.Dependencies) != 1 || item.Dependencies[0] != parent {
		t.Fatalf("dependencies: %+v", item)
	}
}
func TestOperationsDatabaseCancellationFencesExistingLease(t *testing.T) {
	pool := servingDatabasePool(t)
	runner := &CommandSyncRunner{pool: pool}
	id := operationDatabaseWork(t, pool, []string{})
	var token string
	var generation int64
	err := pool.QueryRow(context.Background(), `SELECT lease_token::text,generation FROM football.claim_work(
        'operations-test',interval '1 minute',ARRAY['NORMALIZATION'],ARRAY[$1::uuid])`, id).Scan(&token, &generation)
	if err != nil {
		t.Fatal(err)
	}
	cancelled, err := runner.ControlWork(context.Background(), id, "cancel")
	if err != nil || cancelled.State != "CANCELLED" || cancelled.Generation <= generation || cancelled.LeaseUntil != nil {
		t.Fatalf("cancel: %+v %v", cancelled, err)
	}
	operationDatabaseResponse(t, runner, "/v1/admin/work/"+id, "WorkItem")
	_, err = pool.Exec(context.Background(), `SELECT football.finish_work($1::uuid,'operations-test',
        $2::uuid,$3,$4::football.sha256_hex)`, id, token, generation, strings.Repeat("b", 64))
	var postgresError *pgconn.PgError
	if !errors.As(err, &postgresError) || postgresError.Code != "55000" {
		t.Fatalf("old lease published after cancellation: %v", err)
	}
}
func TestOperationsDatabaseWorkStateFilter(t *testing.T) {
	pool := servingDatabasePool(t)
	runner := &CommandSyncRunner{pool: pool}
	id := operationDatabaseWork(t, pool, []string{})
	if _, err := runner.ControlWork(context.Background(), id, "cancel"); err != nil {
		t.Fatal(err)
	}
	payload := operationDatabaseResponse(t, runner, "/v1/admin/work?state=CANCELLED", "WorkPage")
	var page WorkPage
	if err := json.Unmarshal(payload, &page); err != nil {
		t.Fatal(err)
	}
	if len(page.Items) == 0 {
		t.Fatal("cancelled work list is empty")
	}
	for _, work := range page.Items {
		if work.State != "CANCELLED" {
			t.Fatal("state filter ignored")
		}
	}
}
func TestOperationsDatabaseBlockedWorkRelease(t *testing.T) {
	pool := servingDatabasePool(t)
	runner := &CommandSyncRunner{pool: pool}
	id := operationDatabaseWork(t, pool, []string{})
	operationDatabaseFail(t, pool, id, "BLOCKED_EXTERNAL")
	before := readOperationWork(t, runner, id)
	result, err := runner.ControlWork(context.Background(), id, "retry")
	if err != nil || result.State != "PENDING" || result.Attempts != before.Attempts || result.Generation <= before.Generation {
		t.Fatalf("blocked release: %+v %v", result, err)
	}
}
func TestOperationsDatabaseRetryDeadlinePreserved(t *testing.T) {
	pool := servingDatabasePool(t)
	runner := &CommandSyncRunner{pool: pool}
	id := operationDatabaseWork(t, pool, []string{})
	operationDatabaseFail(t, pool, id, "RETRYABLE")
	before := readOperationWork(t, runner, id)
	result, err := runner.ControlWork(context.Background(), id, "retry")
	if err != nil || result.State != "RETRY_WAIT" || result.Generation != before.Generation || !result.AvailableAt.Equal(before.AvailableAt) {
		t.Fatalf("retry deadline changed: %+v %v", result, err)
	}
	if before.LastErrorMessage == nil || strings.Contains(*before.LastErrorMessage, "private-token") {
		t.Fatalf("unredacted work error: %+v", before)
	}
}
func TestOperationsDatabaseTerminalWorkIdentityPreserved(t *testing.T) {
	pool := servingDatabasePool(t)
	runner := &CommandSyncRunner{pool: pool}
	id := operationDatabaseWork(t, pool, []string{})
	operationDatabaseFail(t, pool, id, "NON_RETRYABLE")
	before := readOperationWork(t, runner, id)
	if _, err := runner.ControlWork(context.Background(), id, "retry"); !errors.Is(err, errWorkControlConflict) {
		t.Fatalf("terminal retry accepted: %v", err)
	}
	after := readOperationWork(t, runner, id)
	if after.State != "FAILED" || after.Generation != before.Generation {
		t.Fatalf("terminal identity changed: %+v", after)
	}
}
func TestOperationsDatabaseParentSyncRetryUsesExistingRunner(t *testing.T) {
	pool := servingDatabasePool(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	runner := NewCommandSyncRunner(ctx, pool, delayedSyncRepository(t, "0.05"), slog.New(slog.NewTextHandler(io.Discard, nil)))
	defer runner.Shutdown(context.Background())
	id, err := newUUID()
	if err != nil {
		t.Fatal(err)
	}
	request := SyncRequest{Type: SyncMVP, Date: "2026-10-20"}
	date, err := validateSyncDateRange(request.Date, "")
	if err != nil {
		t.Fatal(err)
	}
	if err = runner.enqueue(ctx, request, id, ".local/sync-runs/old.log", date, []byte(`{}`)); err != nil {
		t.Fatal(err)
	}
	runner.cancelled(id)
	result, err := runner.ControlWork(ctx, id, "retry")
	if err != nil || result.ID == id || result.ParentSyncRunID == nil || *result.ParentSyncRunID != result.ID {
		t.Fatalf("parent retry: %+v %v", result, err)
	}
	old, err := runner.WorkItem(ctx, id)
	if err != nil || old.State != "CANCELLED" {
		t.Fatalf("old parent changed: %+v %v", old, err)
	}
	stop, cancelStop := context.WithTimeout(context.Background(), time.Second)
	defer cancelStop()
	runner.Shutdown(stop)
}

func TestOperationsDatabaseModelRegistrationContract(t *testing.T) {
	runner := &CommandSyncRunner{pool: servingDatabasePool(t)}
	view, err := runner.Operations(context.Background(), "models", OperationPage{Page: 1, PageSize: 20})
	if err != nil {
		t.Fatal(err)
	}
	if len(view.Items) != 1 {
		t.Fatalf("expected the fixture's exact champion registration: %+v", view)
	}
	var record struct {
		Registration map[string]json.RawMessage `json:"registration"`
		SHA256       string                     `json:"registration_sha256"`
		RegisteredAt time.Time                  `json:"registered_at"`
	}
	if err = json.Unmarshal(view.Items[0], &record); err != nil {
		t.Fatal(err)
	}
	if len(record.SHA256) != 64 || record.RegisteredAt.IsZero() {
		t.Fatalf("registration metadata: %+v", record)
	}
	if string(record.Registration["contract"]) != `"ModelRegistration"` {
		t.Fatal("registered contract missing")
	}
	if _, changed := record.Registration["registered_at"]; changed {
		t.Fatal("runtime metadata changed the immutable contract")
	}
}
