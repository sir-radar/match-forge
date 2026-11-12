package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Publish fences all inventory writes with the existing shared work lease.
func Publish(ctx context.Context, pool *pgxpool.Pool, lease Lease, review Review) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	err = lockPublication(ctx, tx, lease)
	if err != nil {
		return err
	}
	for _, resource := range review.Resources {
		if resource.Kind == "archive" {
			continue // A capacity scan cannot change a publication receipt.
		}
		if err = observe(ctx, tx, resource); err != nil {
			return err
		}
	}
	payload, err := json.Marshal(review)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(payload)
	if err = insertReview(ctx, tx, lease.WorkID, review.PolicySHA256, hex.EncodeToString(sum[:]), payload); err != nil {
		return err
	}
	if err = lockPublication(ctx, tx, lease); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func observe(ctx context.Context, tx pgx.Tx, r Resource) error {
	blockers, _ := json.Marshal(r.Blockers)
	// Discovery may refresh accounting, never downgrade owner-declared protection/retention.
	_, err := tx.Exec(ctx, `INSERT INTO football.storage_resources(resource_id,backend,location,kind,subsystem,
 logical_bytes,allocated_bytes,sha256,protected,reference_count,complete,blockers,details,owner_name,lease_until,state)
 VALUES($1,$2,$3,$4,$5,$6,$7,$8,true,$9,$10,$11,$12,$13,$14,$15)
 ON CONFLICT(resource_id) DO UPDATE SET logical_bytes=EXCLUDED.logical_bytes,
 allocated_bytes=EXCLUDED.allocated_bytes,reference_count=EXCLUDED.reference_count,
 complete=EXCLUDED.complete,blockers=EXCLUDED.blockers,details=EXCLUDED.details,owner_name=EXCLUDED.owner_name,lease_until=EXCLUDED.lease_until,state=EXCLUDED.state,observed_at=clock_timestamp()
 WHERE (storage_resources.logical_bytes,storage_resources.allocated_bytes,storage_resources.reference_count,
 storage_resources.complete,storage_resources.blockers,storage_resources.details,storage_resources.owner_name,storage_resources.lease_until,storage_resources.state) IS DISTINCT FROM
 (EXCLUDED.logical_bytes,EXCLUDED.allocated_bytes,EXCLUDED.reference_count,EXCLUDED.complete,EXCLUDED.blockers,EXCLUDED.details,EXCLUDED.owner_name,EXCLUDED.lease_until,EXCLUDED.state)`,
		r.ID, r.Backend, r.Location, r.Kind, r.Subsystem, r.LogicalBytes, r.AllocatedBytes, r.SHA256, r.References, r.Complete, blockers, r.Details, r.Owner, r.LeaseUntil, r.State)
	return err
}

// Reserve serializes capacity admission on the backing device across all task owners.
// Expired reservations remain charged until their resources are explicitly released.
func Reserve(ctx context.Context, pool *pgxpool.Pool, id string, lease Lease, device string, bytes, reserve int64, until time.Time, freeCapacity func(context.Context) (int64, error)) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, "storage-capacity:"+device); err != nil {
		return err
	}
	free, err := freeCapacity(ctx)
	if err != nil {
		return err
	}
	if err = lockPublication(ctx, tx, lease); err != nil {
		return err
	}
	var charged int64
	if err = tx.QueryRow(ctx, `SELECT coalesce(sum(reserved_bytes),0) FROM football.storage_reservations WHERE backend_identity=$1 AND released_at IS NULL`, device).Scan(&charged); err != nil {
		return err
	}
	if err = (Reservation{bytes, free, charged, reserve}).Admit(); err != nil {
		return err
	}
	if !until.After(time.Now()) {
		return errors.New("reservation requires a future ownership lease")
	}
	_, err = tx.Exec(ctx, `INSERT INTO football.storage_reservations(resource_id,work_id,owner_name,backend_identity,reserved_bytes,lease_until,work_generation) VALUES($1,$2,$3,$4,$5,$6,$7)`, id, lease.WorkID, lease.Owner, device, bytes, until, lease.Generation)
	if err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func Release(ctx context.Context, pool *pgxpool.Pool, id, owner string) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	var device string
	if err = tx.QueryRow(ctx, `SELECT backend_identity FROM football.storage_reservations WHERE resource_id=$1 AND owner_name=$2 AND released_at IS NULL`, id, owner).Scan(&device); err != nil {
		return err
	}
	if _, err = tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, "storage-capacity:"+device); err != nil {
		return err
	}
	result, err := tx.Exec(ctx, `UPDATE football.storage_reservations SET released_at=clock_timestamp() WHERE resource_id=$1 AND owner_name=$2 AND released_at IS NULL`, id, owner)
	if err != nil {
		return err
	}
	if result.RowsAffected() != 1 {
		return errors.New("resource ownership absent or already released")
	}
	return tx.Commit(ctx)
}

func lockPublication(ctx context.Context, tx pgx.Tx, lease Lease) error {
	if err := lease.Validate(); err != nil {
		return err
	}
	_, err := tx.Exec(ctx, `SELECT football.lock_work($1,$2,$3,$4)`, lease.WorkID, lease.Owner, lease.Token, lease.Generation)
	return err
}

func insertReview(ctx context.Context, tx pgx.Tx, workID, policy, digest string, payload []byte) error {
	_, err := tx.Exec(ctx, `INSERT INTO football.storage_reviews(work_id,policy_sha256,manifest_sha256,manifest) VALUES($1,$2,$3,$4) ON CONFLICT(work_id) DO NOTHING`, workID, policy, digest, payload)
	if err != nil {
		return err
	}
	var stored string
	if err = tx.QueryRow(ctx, `SELECT manifest_sha256 FROM football.storage_reviews WHERE work_id=$1`, workID).Scan(&stored); err != nil {
		return err
	}
	if stored != digest {
		return errors.New("work identity already binds a different immutable storage review")
	}
	return nil
}
