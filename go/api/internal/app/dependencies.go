package app

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// ReadinessChecker reports whether required runtime dependencies are usable.
type ReadinessChecker interface{ Ready(context.Context) error }

// DependencyReadiness probes the same PostgreSQL pool used by serving, its
// migrated schema, and the Redis protocol required by the local service contract.
type DependencyReadiness struct {
	pool         *pgxpool.Pool
	redisAddress string
	timeout      time.Duration
}

func NewDependencyReadiness(config Config, pool *pgxpool.Pool) DependencyReadiness {
	return DependencyReadiness{pool: pool, redisAddress: config.RedisAddress, timeout: config.DependencyTimeout}
}

func (readiness DependencyReadiness) Ready(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, readiness.timeout)
	defer cancel()
	if err := readiness.pool.Ping(ctx); err != nil {
		return fmt.Errorf("PostgreSQL serving pool unavailable: %w", err)
	}
	var ready bool
	err := readiness.pool.QueryRow(ctx, `SELECT
   to_regclass('football.product_forecasts') IS NOT NULL
   AND to_regclass('football.product_sync_runs') IS NOT NULL
   AND to_regprocedure('football.product_performance_forecasts(uuid[],integer)') IS NOT NULL
   AND to_regprocedure('football.product_eligible_team_history_at(timestamptz,uuid[])') IS NOT NULL
   AND EXISTS (SELECT 1 FROM (SELECT DISTINCT ON (version_id) version_id,is_applied
               FROM public.goose_db_version ORDER BY version_id,id DESC) migration
               WHERE version_id=202610130600 AND is_applied)`).Scan(&ready)
	if err != nil {
		return fmt.Errorf("serving schema unavailable: %w", err)
	}
	if !ready {
		return errors.New("serving schema migration 202610130600 required")
	}
	return redisReady(ctx, readiness.redisAddress)
}

func redisReady(ctx context.Context, address string) error {
	connection, err := (&net.Dialer{}).DialContext(ctx, "tcp", address)
	if err != nil {
		return fmt.Errorf("Redis unavailable: %w", err)
	}
	defer connection.Close()
	stop := context.AfterFunc(ctx, func() { _ = connection.Close() })
	defer stop()
	deadline, _ := ctx.Deadline()
	if err := connection.SetDeadline(deadline); err != nil {
		return err
	}
	if _, err := io.WriteString(connection, "*1\r\n$4\r\nPING\r\n"); err != nil {
		return fmt.Errorf("Redis PING failed: %w", err)
	}
	response := make([]byte, 7)
	if _, err := io.ReadFull(connection, response); err != nil {
		return fmt.Errorf("Redis PING failed: %w", err)
	}
	if string(response) != "+PONG\r\n" {
		return errors.New("Redis did not return protocol PONG")
	}
	return nil
}
