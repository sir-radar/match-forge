package app

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func servingDatabasePool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("requires disposable integration database")
	}
	pool, err := pgxpool.New(context.Background(), url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestServingDatabaseReadinessAndWrongCredentials(t *testing.T) {
	pool := servingDatabasePool(t)
	redis := protocolListener(t, "+PONG\r\n")
	config := Config{RedisAddress: redis, DependencyTimeout: time.Second}
	if err := NewDependencyReadiness(config, pool).Ready(context.Background()); err != nil {
		t.Fatal(err)
	}
	invalid := pool.Config()
	invalid.ConnConfig.Password = "not-valid-for-disposable-database"
	badPool, err := pgxpool.NewWithConfig(context.Background(), invalid)
	if err != nil {
		t.Fatal(err)
	}
	defer badPool.Close()
	if NewDependencyReadiness(config, badPool).Ready(context.Background()) == nil {
		t.Fatal("wrong credentials accepted")
	}
	pool.Close()
	if NewDependencyReadiness(config, pool).Ready(context.Background()) == nil {
		t.Fatal("closed serving pool accepted")
	}
}

func TestServingDatabaseRejectsInvalidProtocol(t *testing.T) {
	if os.Getenv("TEST_DATABASE_URL") == "" {
		t.Skip("requires disposable integration database")
	}
	address := protocolListener(t, "NOTPOSTGRES")
	pool, err := pgxpool.New(context.Background(), "postgres://test:test@"+address+"/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	started := time.Now()
	if NewDependencyReadiness(Config{DependencyTimeout: 50 * time.Millisecond}, pool).Ready(context.Background()) == nil {
		t.Fatal("TCP-only listener accepted")
	}
	if time.Since(started) > time.Second {
		t.Fatal("protocol check unbounded")
	}
}

type blockedPerformanceStore struct {
	unavailableProductStore
	pool    *pgxpool.Pool
	started chan uint32
}

func (store blockedPerformanceStore) Performances(ctx context.Context, _ PerformanceFilters) (PerformancePage, error) {
	connection, err := store.pool.Acquire(ctx)
	if err != nil {
		return PerformancePage{}, err
	}
	defer connection.Release()
	store.started <- connection.Conn().PgConn().PID()
	_, err = connection.Exec(ctx, "SELECT pg_sleep(10)")
	return PerformancePage{}, err
}

func TestServingDatabaseRequestDeadlineCancelsPostgresWork(t *testing.T) {
	pool := servingDatabasePool(t)
	started := make(chan uint32, 1)
	application := New(Config{HandlerTimeout: 200 * time.Millisecond}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, blockedPerformanceStore{pool: pool, started: started})
	response := httptest.NewRecorder()
	done := make(chan struct{})
	go func() {
		application.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/v1/performance", nil))
		close(done)
	}()
	var pid uint32
	select {
	case pid = <-started:
	case <-time.After(time.Second):
		t.Fatal("query never started")
	}
	assertBackendActivity(t, pool, pid, true)
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("request ignored execution deadline")
	}
	if response.Code != http.StatusGatewayTimeout {
		t.Fatalf("query timeout status %d: %s", response.Code, response.Body)
	}
	assertBackendActivity(t, pool, pid, false)
}

func assertBackendActivity(t *testing.T, pool *pgxpool.Pool, pid uint32, want bool) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for {
		var active bool
		err := pool.QueryRow(context.Background(), "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=$1 AND state='active' AND query LIKE '%pg_sleep%')", pid).Scan(&active)
		if err != nil {
			t.Fatal(err)
		}
		if active == want {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("backend activity = %v, want %v", active, want)
		}
		time.Sleep(5 * time.Millisecond)
	}
}

func TestServingDatabaseDurableJobOutlivesRequestAndThirtySeconds(t *testing.T) {
	pool := servingDatabasePool(t)
	root := delayedSyncRepository(t, "31")
	parent, cancel := context.WithCancel(context.Background())
	defer cancel()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	runner := NewCommandSyncRunner(parent, pool, root, logger)
	application := NewWithSyncRunner(Config{Address: "127.0.0.1:8080", AllowedOrigin: "http://127.0.0.1:3000", HandlerTimeout: 100 * time.Millisecond}, logger, readinessStub{}, unavailableProductStore{}, runner)
	request := httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8080/v1/admin/sync/openfootball", strings.NewReader("{}"))
	request.RemoteAddr = "127.0.0.1:1234"
	request.Header.Set("Origin", "http://127.0.0.1:3000")
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	started := time.Now()
	application.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf("submission failed: %d %s", response.Code, response.Body)
	}
	var run SyncRun
	if err := json.Unmarshal(response.Body.Bytes(), &run); err != nil {
		t.Fatal(err)
	}
	ctx, stop := context.WithTimeout(context.Background(), 40*time.Second)
	defer stop()
	if err := waitSuccessfulJob(ctx, runner, run.ID); err != nil {
		t.Fatal(err)
	}
	if time.Since(started) < 30*time.Second {
		t.Fatal("long durable job was not exercised")
	}
}

func delayedSyncRepository(t *testing.T, delay string) string {
	t.Helper()
	root := t.TempDir()
	binary := filepath.Join(root, ".tools", "bin", "uv")
	if err := os.MkdirAll(filepath.Dir(binary), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(binary, []byte(fmt.Sprintf("#!/bin/sh\nsleep %s\nprintf '%%s\\n' '{\"matches_inserted\":0}'\n", delay)), 0700); err != nil {
		t.Fatal(err)
	}
	return root
}

func waitSuccessfulJob(ctx context.Context, runner *CommandSyncRunner, id string) error {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			run, err := runner.Get(ctx, id)
			if err != nil {
				return err
			}
			if run.Status == "SUCCEEDED" {
				return nil
			}
			if run.Status == "FAILED" || run.Status == "CANCELLED" {
				return context.Canceled
			}
		}
	}
}

type responseLookupKey struct{}
type responseLookupCancellation struct {
	cancel    context.CancelFunc
	triggered atomic.Bool
}

func (tracer *responseLookupCancellation) TraceQueryStart(ctx context.Context, _ *pgx.Conn, data pgx.TraceQueryStartData) context.Context {
	if ctx.Value(responseLookupKey{}) != nil && strings.Contains(data.SQL, "FROM football.product_sync_runs") && strings.Contains(data.SQL, "SELECT") && tracer.triggered.CompareAndSwap(false, true) {
		tracer.cancel()
	}
	return ctx
}
func (*responseLookupCancellation) TraceQueryEnd(context.Context, *pgx.Conn, pgx.TraceQueryEndData) {}

func TestServingDatabaseCommittedJobSurvivesResponseLookupCancellation(t *testing.T) {
	base := servingDatabasePool(t)
	request, cancel := context.WithCancel(context.WithValue(context.Background(), responseLookupKey{}, true))
	defer cancel()
	tracer := &responseLookupCancellation{cancel: cancel}
	config := base.Config()
	config.ConnConfig.Tracer = tracer
	pool, err := pgxpool.NewWithConfig(context.Background(), config)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	runner := NewCommandSyncRunner(context.Background(), pool, delayedSyncRepository(t, "0.1"), slog.New(slog.NewTextHandler(io.Discard, nil)))
	_, err = runner.Start(request, SyncRequest{Type: SyncOpenFootball})
	if err == nil || !tracer.triggered.Load() {
		t.Fatal("response lookup cancellation not exercised")
	}
	var id string
	if err := pool.QueryRow(context.Background(), "SELECT run_id::text FROM football.product_sync_runs ORDER BY requested_at DESC LIMIT 1").Scan(&id); err != nil {
		t.Fatal(err)
	}
	ctx, stop := context.WithTimeout(context.Background(), 2*time.Second)
	defer stop()
	if err := waitSuccessfulJob(ctx, runner, id); err != nil {
		t.Fatal("committed job lost after HTTP cancellation", err)
	}
}

// Run last in the isolated serving test database; the harness drops it afterward.
func TestServingDatabaseMissingSchemaFailsReadiness(t *testing.T) {
	pool := servingDatabasePool(t)
	_, err := pool.Exec(context.Background(), "DROP FUNCTION football.product_performance_forecasts(uuid[],integer)")
	if err != nil {
		t.Fatal(err)
	}
	if NewDependencyReadiness(Config{RedisAddress: protocolListener(t, "+PONG\r\n"), DependencyTimeout: time.Second}, pool).Ready(context.Background()) == nil {
		t.Fatal("missing serving schema accepted")
	}
}
