package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type Capacity struct {
	TotalBytes int64  `json:"total_bytes"`
	FreeBytes  int64  `json:"free_bytes"`
	Device     uint64 `json:"device"`
}

func DiskCapacity(path string) (Capacity, error) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return Capacity{}, err
	}
	var identity syscall.Stat_t
	if err := syscall.Stat(path, &identity); err != nil {
		return Capacity{}, err
	}
	return Capacity{int64(stat.Blocks) * int64(stat.Bsize), int64(stat.Bavail) * int64(stat.Bsize), uint64(identity.Dev)}, nil
}
func Identity(backend, location string) string {
	s := sha256.Sum256([]byte(backend + "\x00" + location))
	return hex.EncodeToString(s[:])
}

type scanCount struct {
	Logical    int64
	Allocated  int64
	Entries    int
	Errors     []string
	ErrorCount int
	seen       map[[2]uint64]bool
}

func (s *scanCount) visit(ctx context.Context, p Policy, entry fs.DirEntry, path string, err error) error {
	if ctx.Err() != nil {
		return ctx.Err()
	}
	if err != nil {
		s.recordError(path + ": " + err.Error())
		return fs.SkipDir
	}
	s.Entries++
	if s.Entries > p.MaxEntries {
		return errors.New("scan entry limit reached")
	}
	if entry.Type()&os.ModeSymlink != 0 {
		s.recordError(path + ": symlink excluded")
		return nil
	}
	info, err := entry.Info()
	if err != nil {
		s.recordError(path + ": " + err.Error())
		return nil
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return errors.New("filesystem allocation metadata unavailable")
	}
	key := [2]uint64{uint64(stat.Dev), stat.Ino}
	if s.seen[key] {
		return nil
	}
	s.seen[key] = true
	if info.Mode().IsRegular() {
		s.Logical += info.Size()
	}
	s.Allocated += stat.Blocks * 512
	return nil
}
func ScanRoot(ctx context.Context, p Policy, root RootPolicy) Resource {
	r := Resource{ID: Identity("filesystem", root.Path), Backend: "filesystem", Location: root.Path, Kind: "directory", Subsystem: root.Subsystem, Protected: true, State: "PROTECTED", Blockers: []string{}, Details: json.RawMessage(`{}`)}
	s := scanCount{Errors: []string{}, seen: map[[2]uint64]bool{}}
	// Root pins pathname resolution. Symlinks are excluded, never followed by WalkDir.
	handle, err := os.OpenRoot(root.Path)
	if err != nil {
		r.Blockers = []string{err.Error()}
		return r
	}
	defer handle.Close()
	err = fs.WalkDir(handle.FS(), ".", func(path string, entry fs.DirEntry, err error) error { return s.visit(ctx, p, entry, path, err) })
	if err != nil {
		s.recordError(err.Error())
	}
	r.LogicalBytes = s.Logical
	r.AllocatedBytes = &s.Allocated
	r.Complete = s.ErrorCount == 0
	r.Blockers = s.Errors
	r.Details, _ = json.Marshal(map[string]any{"entries": s.Entries, "measurement": "allocated file bytes; APFS shared extents unknown", "errors": s.Errors, "error_count": s.ErrorCount})
	return r
}

func ScanDatabases(ctx context.Context, pool *pgxpool.Pool) ([]Resource, error) {
	rows, err := pool.Query(ctx, `SELECT d.datname,d.oid::bigint,pg_database_size(d.oid),
 (SELECT count(*) FROM pg_stat_activity a WHERE a.datid=d.oid),
 (SELECT system_identifier::text FROM pg_control_system()) FROM pg_database d WHERE NOT datistemplate ORDER BY datname`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Resource{}
	for rows.Next() {
		var name, cluster string
		var oid, size int64
		var active int
		if err = rows.Scan(&name, &oid, &size, &active, &cluster); err != nil {
			return nil, err
		}
		location := cluster + "/" + name
		details, _ := json.Marshal(map[string]any{"oid": oid, "active_connections": active, "physical_reclaim_estimate": nil, "backup_coverage": "post-rehearsal state not verified"})
		result = append(result, Resource{ID: Identity("postgres", location), Backend: "postgres", Location: location, Kind: "database", Subsystem: "postgres", LogicalBytes: size, Protected: true, Complete: true, References: active, State: "PROTECTED", Blockers: []string{"source dump does not prove recovery of post-rehearsal changes"}, Details: details})
	}
	return result, rows.Err()
}

type Review struct {
	Policy         *Policy           `json:"policy"`
	Actions        []LifecycleAction `json:"actions"`
	ObservedAt     time.Time         `json:"observed_at"`
	Capacity       Capacity          `json:"capacity"`
	Resources      []Resource        `json:"resources"`
	Alerts         []string          `json:"alerts"`
	DryRun         bool              `json:"dry_run"`
	ReclaimedBytes int64             `json:"reclaimed_bytes"`
	PolicySHA256   string            `json:"policy_sha256"`
}

func Collect(ctx context.Context, p Policy, pool *pgxpool.Pool, repository string) (Review, error) {
	r := Review{ObservedAt: time.Now().UTC(), DryRun: true, Resources: []Resource{}, Alerts: []string{}}
	var err error
	r.Capacity, err = DiskCapacity(p.Roots[0].Path)
	if err != nil {
		return r, err
	}
	if r.Capacity.FreeBytes < p.ReserveBytes {
		r.Alerts = append(r.Alerts, "CRITICAL: recovery capacity reserve breached")
	} else if r.Capacity.FreeBytes < p.WarningFreeBytes {
		r.Alerts = append(r.Alerts, "WARNING: free capacity below audited baseline")
	}
	databases, err := ScanDatabases(ctx, pool)
	if err != nil {
		return r, err
	}
	if err = attachManagedOwnership(ctx, pool, databases); err != nil {
		return r, err
	}
	r.Resources = append(r.Resources, databases...)
	r.Alerts = append(r.Alerts, databaseAlerts(databases, p)...)
	limited, cancel := context.WithTimeout(ctx, time.Duration(p.ScanSeconds)*time.Second)
	defer cancel()
	for _, root := range p.Roots {
		resource := ScanRoot(limited, p, root)
		r.Resources = append(r.Resources, resource)
		r.Alerts = append(r.Alerts, rootAlerts(resource, root)...)
	}
	worktrees, err := ScanWorktrees(limited, repository)
	if err != nil {
		r.Alerts = append(r.Alerts, "BLOCKED: incomplete worktree inventory")
	} else {
		r.Resources = append(r.Resources, worktrees...)
	}
	archives, err := archiveReceipts(ctx, pool)
	if err != nil {
		return r, err
	}
	r.Resources = append(r.Resources, archives...)
	payload, _ := json.Marshal(p)
	sum := sha256.Sum256(payload)
	r.PolicySHA256 = hex.EncodeToString(sum[:])
	r.Policy = &p
	r.Actions = PlanLifecycle(r.Resources, r.ObservedAt, time.Duration(p.QuarantineSeconds)*time.Second)
	return r, nil
}
func rootAlerts(r Resource, p RootPolicy) []string {
	alerts := []string{}
	if r.AllocatedBytes != nil {
		if *r.AllocatedBytes >= p.CriticalBytes {
			alerts = append(alerts, "CRITICAL: "+p.Subsystem+" exceeds capacity budget")
		} else if *r.AllocatedBytes >= p.WarningBytes {
			alerts = append(alerts, "WARNING: "+p.Subsystem+" exceeds audited baseline")
		}
	}
	if !r.Complete {
		alerts = append(alerts, "BLOCKED: incomplete "+p.Subsystem+" scan; partial bytes are a lower bound")
	}
	return alerts
}

func SafeRelative(name string) error {
	if !filepath.IsLocal(name) || name == "." || filepath.Clean(name) != name {
		return errors.New("path must be a clean relative resource name")
	}
	return nil
}

func (s *scanCount) recordError(message string) {
	s.ErrorCount++
	if len(s.Errors) < 100 {
		s.Errors = append(s.Errors, message)
	}
}

func databaseAlerts(resources []Resource, p Policy) []string {
	var total int64
	for _, r := range resources {
		if r.Backend == "postgres" {
			total += r.LogicalBytes
		}
	}
	if total >= p.DatabaseCriticalBytes {
		return []string{"CRITICAL: PostgreSQL exceeds the audited footprint plus one measured rehearsal budget; no protected data may be deleted automatically"}
	}
	if total >= p.DatabaseWarningBytes {
		return []string{"WARNING: PostgreSQL exceeds audited baseline capacity"}
	}
	return nil
}
