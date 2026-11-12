package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"

	"github.com/jackc/pgx/v5/pgxpool"
)

// RecordArchive binds a verified publication to the work that produced it.
// An identical retry preserves the original owner and publication receipt.
func RecordArchive(ctx context.Context, pool *pgxpool.Pool, lease Lease, path string, m ArchiveManifest) error {
	location, err := filepath.Abs(path)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(m)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(payload)
	digest := hex.EncodeToString(sum[:])
	return recordArchive(ctx, pool, lease, location, digest, m)
}

func recordArchive(ctx context.Context, pool *pgxpool.Pool, lease Lease, location, digest string, m ArchiveManifest) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if err = lockPublication(ctx, tx, lease); err != nil {
		return err
	}
	id := Identity("filesystem", location)
	_, err = tx.Exec(ctx, `INSERT INTO football.storage_resources
 (resource_id,backend,location,kind,subsystem,owner_name,logical_bytes,sha256,retain_until,protected,complete,details)
 VALUES($1,'filesystem',$2,'archive','evidence_archives',$3,$4,$5,$6,true,true,
 jsonb_build_object('work_id',$7::text,'packed_bytes',$8::bigint,'unique_bytes',$9::bigint,'manifest_sha256',$10::text))
 ON CONFLICT(resource_id) DO NOTHING`,
		id, location, lease.Owner, m.LogicalBytes, m.PayloadSHA256, m.RetainUntil, lease.WorkID, m.PackedBytes, m.UniqueBytes, digest)
	if err != nil {
		return err
	}
	var matches bool
	err = tx.QueryRow(ctx, `SELECT coalesce(kind='archive' AND details->>'manifest_sha256'=$2,false)
 FROM football.storage_resources WHERE resource_id=$1`, id, digest).Scan(&matches)
	if err != nil {
		return err
	}
	if !matches {
		return errors.New("archive location already binds different published evidence")
	}
	return tx.Commit(ctx)
}

func archiveReceipts(ctx context.Context, pool *pgxpool.Pool) ([]Resource, error) {
	rows, err := pool.Query(ctx, `SELECT resource_id,location,owner_name,logical_bytes,sha256,retain_until,
 details || jsonb_build_object('verified_at',observed_at)
 FROM football.storage_resources WHERE kind='archive' ORDER BY resource_id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Resource{}
	for rows.Next() {
		r := Resource{Backend: "filesystem", Kind: "archive", Subsystem: "evidence_archives", Protected: true,
			Complete: true, State: "PROTECTED", Blockers: []string{"archive receipt is historical; independent recovery is required"}}
		if err = rows.Scan(&r.ID, &r.Location, &r.Owner, &r.LogicalBytes, &r.SHA256, &r.RetainUntil, &r.Details); err != nil {
			return nil, err
		}
		archiveAvailability(&r)
		result = append(result, r)
	}
	return result, rows.Err()
}

func archiveAvailability(r *Resource) {
	var receipt struct {
		PackedBytes int64 `json:"packed_bytes"`
	}
	info, err := os.Lstat(filepath.Join(r.Location, "payload.tar.gz"))
	if json.Unmarshal(r.Details, &receipt) != nil || err != nil || !info.Mode().IsRegular() || info.Size() != receipt.PackedBytes {
		r.Complete = false
		r.Blockers = append(r.Blockers, "recorded archive payload unavailable or size changed")
	}
}
