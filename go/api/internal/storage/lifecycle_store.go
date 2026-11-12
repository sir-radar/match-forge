package storage

import (
	"context"
	"encoding/json"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const lifecycleColumns = `identity_key,resource_class,backend,location,owner_kind,identity,owner_ref,created_at,
 last_activity_at,activity_fingerprint,completed_at,completion,state,eligible_at,blockers,checked_at,operation_id::text,reclaimed_bytes`

// lifecycleRecords reads lifecycle rows matching a fixed filter. Before the
// lifecycle migration is deployed it returns no rows, so nothing is eligible.
func lifecycleRecords(ctx context.Context, pool *pgxpool.Pool, filter string) (map[string]LifecycleRecord, error) {
	result := map[string]LifecycleRecord{}
	var ready bool
	if err := pool.QueryRow(ctx, `SELECT to_regclass('football.storage_lifecycle_resources') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		return result, err
	}
	rows, err := pool.Query(ctx, `SELECT `+lifecycleColumns+` FROM football.storage_lifecycle_resources WHERE `+filter+` ORDER BY registered_at, identity_key`)
	if err != nil {
		return nil, err
	}
	records, err := pgx.CollectRows(rows, scanLifecycle)
	for _, r := range records {
		result[r.IdentityKey] = r
	}
	return result, err
}

func scanLifecycle(row pgx.CollectableRow) (LifecycleRecord, error) {
	var r LifecycleRecord
	var blockers []byte
	err := row.Scan(&r.IdentityKey, &r.Class, &r.Backend, &r.Location, &r.OwnerKind, &r.Identity, &r.OwnerRef, &r.CreatedAt,
		&r.LastActivityAt, &r.Fingerprint, &r.CompletedAt, &r.Completion, &r.State, &r.EligibleAt, &blockers, &r.CheckedAt,
		&r.OperationID, &r.ReclaimedBytes)
	if err == nil {
		err = json.Unmarshal(blockers, &r.Blockers)
	}
	return r, err
}

// registerLifecycle inserts a newly discovered resource once. The SQL guard
// refuses protected identities.
func registerLifecycle(ctx context.Context, pool *pgxpool.Pool, r LifecycleRecord, now time.Time) error {
	tag, err := pool.Exec(ctx, `INSERT INTO football.storage_lifecycle_resources(identity_key,resource_class,backend,identity,location,
 owner_kind,owner_ref,created_at,last_activity_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$8) ON CONFLICT (identity_key) DO NOTHING`,
		r.IdentityKey, r.Class, r.Backend, r.Identity, r.Location, r.OwnerKind, r.OwnerRef, now)
	if err != nil || tag.RowsAffected() == 0 {
		return err
	}
	return lifecycleEvent(ctx, pool, r.IdentityKey, "REGISTERED", map[string]any{"owner_kind": r.OwnerKind, "location": r.Location})
}

func lifecycleEvent(ctx context.Context, pool *pgxpool.Pool, key, event string, detail map[string]any) error {
	_, err := pool.Exec(ctx, `INSERT INTO football.storage_lifecycle_events(identity_key,event,detail) VALUES($1,$2,$3)`, key, event, detail)
	return err
}

// saveDecision persists the decision and its audit events in one transaction,
// unless a claim or deletion started meanwhile.
func saveDecision(ctx context.Context, pool *pgxpool.Pool, rec LifecycleRecord, d LifecycleDecision, now time.Time) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	blockers, _ := json.Marshal(d.Blockers)
	tag, err := tx.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET state=$2,last_activity_at=$3,activity_fingerprint=$4,
 completed_at=$5,completion=$6,eligible_at=$7,blockers=$8,checked_at=$9
 WHERE identity_key=$1 AND state=$10 AND (claimed_until IS NULL OR claimed_until<$9)`,
		rec.IdentityKey, d.State, d.LastActivityAt, d.Fingerprint, d.CompletedAt, d.Completion, d.EligibleAt, blockers, now, rec.State)
	if err != nil || tag.RowsAffected() == 0 {
		return err
	}
	detail := map[string]any{"state": d.State, "eligible_at": d.EligibleAt, "last_activity_at": d.LastActivityAt}
	if len(d.Blockers) > 0 {
		detail["blockers"] = d.Blockers
	}
	for _, event := range dedupe(d.Events) {
		if _, err = tx.Exec(ctx, `INSERT INTO football.storage_lifecycle_events(identity_key,event,detail) VALUES($1,$2,$3)`,
			rec.IdentityKey, event, detail); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

// claimLifecycle takes an exclusive, expiring claim on one ELIGIBLE resource so
// two cleanup workers can never submit the same deletion.
func claimLifecycle(ctx context.Context, pool *pgxpool.Pool, key string, now time.Time, hold time.Duration) (string, bool, error) {
	token := newUUID()
	tag, err := pool.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET claim_token=$2,claimed_until=$3
 WHERE identity_key=$1 AND state='ELIGIBLE' AND (claimed_until IS NULL OR claimed_until<$4)`, key, token, now.Add(hold), now)
	if err != nil || tag.RowsAffected() != 1 {
		return "", false, err
	}
	return token, true, lifecycleEvent(ctx, pool, key, "CLAIMED", map[string]any{"claimed_until": now.Add(hold)})
}

func releaseClaim(ctx context.Context, pool *pgxpool.Pool, key, token string) {
	_, _ = pool.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET claim_token=NULL,claimed_until=NULL
 WHERE identity_key=$1 AND claim_token=$2`, key, token)
}

func markDeleting(ctx context.Context, pool *pgxpool.Pool, key, token, operation string) error {
	_, err := pool.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET state='DELETING',operation_id=$3
 WHERE identity_key=$1 AND claim_token=$2 AND state='ELIGIBLE'`, key, token, operation)
	if err == nil {
		err = lifecycleEvent(ctx, pool, key, "SUBMITTED", map[string]any{"operation_id": operation})
	}
	return err
}

// settleDeletion records the outcome of a submitted deletion from its durable
// storage operation. A failed or blocked deletion returns the resource to
// BLOCKED; the next check re-derives its state from fresh observations.
func settleDeletion(ctx context.Context, pool *pgxpool.Pool, rec LifecycleRecord, now time.Time) (string, *int64, error) {
	if rec.OperationID == nil {
		return "", nil, nil
	}
	var state string
	var reclaimed *int64
	var message *string
	if err := pool.QueryRow(ctx, `SELECT state,reclaimed_bytes,error FROM football.storage_operations WHERE operation_id=$1`,
		*rec.OperationID).Scan(&state, &reclaimed, &message); err != nil {
		return "", nil, err
	}
	switch state {
	case "PENDING", "RUNNING":
		return state, nil, nil
	case "SUCCEEDED":
		_, err := pool.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET state='DELETED',reclaimed_bytes=$2,checked_at=$3,
 claim_token=NULL,claimed_until=NULL WHERE identity_key=$1 AND state='DELETING'`, rec.IdentityKey, reclaimed, now)
		if err == nil {
			err = lifecycleEvent(ctx, pool, rec.IdentityKey, "DELETED", map[string]any{"operation_id": *rec.OperationID, "reclaimed_bytes": reclaimed})
		}
		return state, reclaimed, err
	}
	reason := "deletion " + strings.ToLower(state)
	if message != nil {
		reason += ": " + *message
	}
	blockers, _ := json.Marshal([]string{reason})
	_, err := pool.Exec(ctx, `UPDATE football.storage_lifecycle_resources SET state='BLOCKED',blockers=$2,checked_at=$3,
 claim_token=NULL,claimed_until=NULL,operation_id=NULL WHERE identity_key=$1 AND state='DELETING'`, rec.IdentityKey, blockers, now)
	if err == nil {
		err = lifecycleEvent(ctx, pool, rec.IdentityKey, "DELETE_FAILED", map[string]any{"operation_id": *rec.OperationID, "reason": reason})
	}
	return state, nil, err
}
