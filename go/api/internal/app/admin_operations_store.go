package app

import (
	"context"
	"encoding/json"
	"errors"
	"regexp"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

func (runner *CommandSyncRunner) Operations(ctx context.Context, domain string, page OperationPage) (OperationView, error) {
	query, ok := operationQueries[domain]
	view := OperationView{Domain: domain, Source: query.source, OperationPage: page, Items: []json.RawMessage{}}
	if !ok {
		return view, errProductUnavailable
	}
	tx, err := runner.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return view, err
	}
	defer tx.Rollback(ctx) // Read transactions publish nothing.
	if err = tx.QueryRow(ctx, "SELECT transaction_timestamp()").Scan(&view.ObservedAt); err != nil {
		return view, err
	}
	rows, err := tx.Query(ctx, query.query+" LIMIT $1 OFFSET $2", page.PageSize+1, (page.Page-1)*page.PageSize)
	if err != nil {
		return view, err
	}
	defer rows.Close()
	for rows.Next() {
		var payload []byte
		if err = rows.Scan(&payload); err != nil {
			return view, err
		}
		view.Items = append(view.Items, json.RawMessage(payload))
	}
	view.HasMore = len(view.Items) > page.PageSize
	if view.HasMore {
		view.Items = view.Items[:page.PageSize]
	}
	return view, rows.Err()
}
func (runner *CommandSyncRunner) WorkItems(ctx context.Context, filter WorkFilters) (WorkPage, error) {
	page := WorkPage{OperationPage: filter.OperationPage, Items: []WorkItem{}}
	tx, err := runner.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return page, err
	}
	defer tx.Rollback(ctx)
	if err = tx.QueryRow(ctx, "SELECT transaction_timestamp()").Scan(&page.ObservedAt); err != nil {
		return page, err
	}
	rows, err := tx.Query(ctx, operationWorkSelect+`WHERE ($3::text='' OR w.state=$3)
        ORDER BY w.requested_at DESC,w.work_id LIMIT $1 OFFSET $2`, filter.PageSize+1, (filter.Page-1)*filter.PageSize, filter.State)
	if err != nil {
		return page, err
	}
	defer rows.Close()
	for rows.Next() {
		var payload []byte
		if err = rows.Scan(&payload); err != nil {
			return page, err
		}
		item, decodeErr := decodeWork(payload)
		if decodeErr != nil {
			return page, decodeErr
		}
		page.Items = append(page.Items, item)
	}
	page.HasMore = len(page.Items) > filter.PageSize
	if page.HasMore {
		page.Items = page.Items[:filter.PageSize]
	}
	return page, rows.Err()
}
func (runner *CommandSyncRunner) WorkItem(ctx context.Context, id string) (WorkItem, error) {
	var payload []byte
	err := runner.pool.QueryRow(ctx, operationWorkSelect+"WHERE w.work_id=$1::uuid", id).Scan(&payload)
	if err != nil {
		return WorkItem{}, err
	}
	return decodeWork(payload)
}

var operationBearer = regexp.MustCompile(`(?i)\bbearer\s+[^\s,;]+`)
var operationSecret = regexp.MustCompile(`(?i)(password|api[_-]?key|token|authorization)(\s*[:=]\s*)[^\s,;&]+`)
var operationCredentialURL = regexp.MustCompile(`(?i)\b(postgres(?:ql)?|https?)://[^/\s@]+@`)

func decodeWork(payload []byte) (WorkItem, error) {
	var item WorkItem
	err := json.Unmarshal(payload, &item)
	if item.LastErrorMessage != nil {
		message := operationBearer.ReplaceAllString(*item.LastErrorMessage, "Bearer [REDACTED]")
		message = operationSecret.ReplaceAllString(message, "${1}${2}[REDACTED]")
		message = operationCredentialURL.ReplaceAllString(message, "${1}://[REDACTED]@")
		item.LastErrorMessage = &message
	}
	return item, err
}
func (runner *CommandSyncRunner) ControlWork(ctx context.Context, id, action string) (WorkItem, error) {
	item, err := runner.WorkItem(ctx, id)
	if err != nil {
		return item, err
	}
	var syncStatus string
	syncErr := runner.pool.QueryRow(ctx, "SELECT status FROM football.product_sync_runs WHERE run_id=$1::uuid", id).Scan(&syncStatus)
	if syncErr != nil && !errors.Is(syncErr, pgx.ErrNoRows) {
		return item, syncErr
	}
	if syncErr == nil {
		return runner.controlSyncWork(ctx, id, action, syncStatus)
	}
	return runner.controlSharedWork(ctx, item, action)
}
func (runner *CommandSyncRunner) controlSyncWork(ctx context.Context, id, action, status string) (WorkItem, error) {
	if action == "retry" {
		run, err := runner.Retry(ctx, id)
		if err != nil {
			return WorkItem{}, err
		}
		return runner.WorkItem(ctx, run.ID)
	}
	if action != "cancel" {
		return WorkItem{}, errWorkControlConflict
	}
	if status == "QUEUED" || status == "RUNNING" {
		if _, err := runner.Stop(ctx, id); err != nil {
			return WorkItem{}, err
		}
	}
	return runner.WorkItem(ctx, id)
}
func (runner *CommandSyncRunner) controlSharedWork(ctx context.Context, item WorkItem, action string) (WorkItem, error) {
	var err error
	switch action {
	case "cancel":
		_, err = runner.pool.Exec(ctx, "SELECT football.cancel_work($1::uuid)", item.ID)
	case "retry":
		switch item.State {
		case "RETRY_WAIT":
			return item, nil // Existing retry policy and deferral remain authoritative.
		case "BLOCKED":
			_, err = runner.pool.Exec(ctx, `SELECT football.release_blocked_work(work_id,
                greatest(available_at,clock_timestamp())) FROM football.work_items WHERE work_id=$1::uuid`, item.ID)
		default:
			return item, errWorkControlConflict
		}
	default:
		return item, errWorkControlConflict
	}
	var postgresError *pgconn.PgError
	if errors.As(err, &postgresError) && postgresError.Code == "55000" {
		return item, errWorkControlConflict
	}
	if err != nil {
		return item, err
	}
	return runner.WorkItem(ctx, item.ID)
}

// Keep compile-time ownership explicit without adding another administration service.
var _ operationsReader = (*CommandSyncRunner)(nil)
