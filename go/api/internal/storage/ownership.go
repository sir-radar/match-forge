package storage

import (
	"context"
	"encoding/json"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func attachManagedOwnership(ctx context.Context, pool *pgxpool.Pool, resources []Resource) error {
	rows, err := pool.Query(ctx, `SELECT r.owner_name,r.resource_identity->>'cluster',
 r.resource_identity->>'database',r.resource_identity->>'oid',
 coalesce(w.lease_until,r.lease_until),CASE WHEN w.generation=r.work_generation THEN w.state ELSE 'STALE_GENERATION' END,r.work_id::text
 FROM football.storage_reservations r JOIN football.work_items w USING(work_id)
 WHERE r.released_at IS NULL AND r.resource_identity ? 'database'`)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var owner, cluster, database, oid, state, workID string
		var until time.Time
		if err = rows.Scan(&owner, &cluster, &database, &oid, &until, &state, &workID); err != nil {
			return err
		}
		for i := range resources {
			if resources[i].Location == cluster+"/"+database {
				attachOwner(&resources[i], owner, oid, workID, state, until)
			}
		}
	}
	return rows.Err()
}
func attachOwner(r *Resource, owner, oid, workID, state string, until time.Time) {
	var details struct {
		OID int64 `json:"oid"`
	}
	if json.Unmarshal(r.Details, &details) != nil {
		return
	}
	// OID is included in the declaration; name reuse never transfers ownership.
	var registered int64
	if json.Unmarshal([]byte(oid), &registered) != nil || registered != details.OID {
		return
	}
	r.Owner = owner
	r.LeaseUntil = &until
	r.Subsystem = "managed_rehearsals"
	metadata := map[string]any{}
	if json.Unmarshal(r.Details, &metadata) != nil {
		return
	}
	metadata["work_id"] = workID
	metadata["work_state"] = state
	r.Details, _ = json.Marshal(metadata)
	if state == "RUNNING" && until.After(time.Now()) {
		r.State = "ACTIVE"
	} else {
		r.Blockers = append(r.Blockers, "managed rehearsal has no active job lease; preserve for owner review")
	}
}
