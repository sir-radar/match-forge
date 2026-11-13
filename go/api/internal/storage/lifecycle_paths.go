package storage

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
	"time"
)

// stagingMarker names a directory detached for deletion next to its original.
const stagingMarker = ".matchforge-deleting-"

// ProcessUse is one scan of what the user's processes are doing: command names,
// open files and working directories.
type ProcessUse struct {
	Names []string
	Open  []string
	Cwds  []string
}

// ProcessScan is injected so tests control process activity.
type ProcessScan func(ctx context.Context) (ProcessUse, error)

// LocalProcessScan lists the current user's processes and their open files with
// one ps and one lsof call per check, never by walking the managed trees.
func LocalProcessScan(ctx context.Context) (ProcessUse, error) {
	var use ProcessUse
	names, err := exec.CommandContext(ctx, "ps", "-x", "-o", "comm=").Output()
	if err != nil {
		return use, err
	}
	for _, line := range strings.Split(string(names), "\n") {
		if line = strings.TrimSpace(line); line != "" {
			use.Names = append(use.Names, filepath.Base(line))
		}
	}
	output, err := exec.CommandContext(ctx, "lsof", "-n", "-P", "-w", "-u", fmt.Sprint(os.Getuid()), "-F", "fn").Output()
	if err != nil && len(output) == 0 {
		return use, err
	}
	cwd := false
	for _, line := range strings.Split(string(output), "\n") {
		switch {
		case strings.HasPrefix(line, "f"):
			cwd = line == "fcwd"
		case strings.HasPrefix(line, "n/"):
			if cwd {
				use.Cwds = append(use.Cwds, line[1:])
			} else {
				use.Open = append(use.Open, line[1:])
			}
		}
	}
	return use, nil
}

func (m *Manager) processScan() ProcessScan {
	if m.ProcessScan != nil {
		return m.ProcessScan
	}
	return LocalProcessScan
}

// pathIdentity returns the identity base of a directory: device, inode and a
// digest of its path. Some filesystems reuse a deleted directory's inode at
// once, so a record key adds a generation after the base (see discoverPaths).
func pathIdentity(path string) (string, map[string]any, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return "", nil, err
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || !info.IsDir() {
		return "", nil, errors.New("not a directory")
	}
	identity := map[string]any{"path": path, "device": uint64(stat.Dev), "inode": stat.Ino}
	return fmt.Sprintf("fs:%d:%d:%s", uint64(stat.Dev), stat.Ino, Fingerprint(path)[:16]), identity, nil
}

// currentPath reports whether the record still describes the directory now at
// its location: same device, inode and path.
func currentPath(key, location string) bool {
	base, _, err := pathIdentity(location)
	return err == nil && strings.HasPrefix(key, base+":")
}

// discoverPaths registers each configured path that exists. A directory whose
// identity base already has an open record is tracked by it; otherwise a new
// generation is registered, so a rebuilt directory never inherits a deleted
// directory's terminal record even when its inode was reused.
func (m *Manager) discoverPaths(ctx context.Context, policy LifecyclePolicy, now time.Time) error {
	for _, d := range policy.Paths {
		base, identity, err := pathIdentity(d.Path)
		if errors.Is(err, fs.ErrNotExist) {
			continue
		}
		if err != nil {
			return err
		}
		var open, generations int
		if err = m.Pool.QueryRow(ctx, `SELECT count(*) FILTER (WHERE state NOT IN ('DELETED','ABSENT')),count(*)
 FROM football.storage_lifecycle_resources WHERE starts_with(identity_key,$1)`, base+":").Scan(&open, &generations); err != nil {
			return err
		}
		if open > 0 {
			continue
		}
		rec := LifecycleRecord{IdentityKey: fmt.Sprintf("%s:%d", base, generations), Class: ClassDisposablePath, Backend: "filesystem",
			Location: d.Path, OwnerKind: "POLICY_PATH", Identity: identity, OwnerRef: map[string]any{"kind": d.Kind, "consumers": d.Consumers}}
		if err = registerLifecycle(ctx, m.Pool, rec, now); err != nil {
			return err
		}
	}
	return nil
}

// pathAllowed refuses anything that is not strictly inside the repository, or
// that overlaps Git metadata, Git-tracked files, the operating data root or a
// protected path.
func (m *Manager) pathAllowed(path string) string {
	if m.Repository == "" || !within(m.Repository, path) || path == m.Repository {
		return "path is not inside the repository"
	}
	for p, reason := range m.reservedPaths() {
		if overlaps(p, path) {
			return reason
		}
	}
	return trackedFilesInside(m.Repository, path)
}

// reservedPaths maps each path the policy must never touch to the reason.
func (m *Manager) reservedPaths() map[string]string {
	reserved := map[string]string{filepath.Join(m.Repository, ".git"): "path is Git metadata"}
	if root := os.Getenv("FOOTBALL_DATA_ROOT"); root != "" {
		if !filepath.IsAbs(root) {
			root = filepath.Join(m.Repository, root)
		}
		reserved[root] = "path overlaps the operating data root"
	}
	if m.Policy != nil {
		for _, p := range m.Policy.ProtectedPaths {
			reserved[p] = "path overlaps a protected path"
		}
	}
	return reserved
}

// trackedFilesInside refuses a directory that holds files Git tracks: tracked
// documentation and source are retired by pull request, never by this policy.
// It fails closed when Git cannot answer.
func trackedFilesInside(repository, path string) string {
	relative, err := filepath.Rel(repository, path)
	if err != nil {
		return "could not check Git-tracked files"
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	output, err := exec.CommandContext(ctx, "git", "-C", repository, "ls-files", "-z", "--", relative).Output()
	if err != nil {
		return "could not check Git-tracked files"
	}
	if len(output) > 0 {
		return "path contains Git-tracked files"
	}
	return ""
}

func overlaps(a, b string) bool { return a == b || within(a, b) || within(b, a) }

// observePath reports live use (consumer processes, open files, working
// directories), completion once none remains, and a bounded fingerprint of the
// top two directory levels that changes when the build or cache writes.
func (m *Manager) observePath(rec LifecycleRecord, use ProcessUse, scanErr error, policy LifecyclePolicy) LifecycleObservation {
	if !currentPath(rec.IdentityKey, rec.Location) {
		return LifecycleObservation{}
	}
	obs := LifecycleObservation{Present: true, Fingerprint: shallowFingerprint(rec.Location, 20_000), Deletable: true}
	if reason := m.pathAllowed(rec.Location); reason != "" {
		obs.Blockers, obs.Deletable = []string{reason}, false
	}
	if scanErr != nil {
		obs.InUse = []string{"process activity unavailable: " + scanErr.Error()}
		return obs
	}
	obs.InUse = use.users(rec.Location, consumersOf(policy, rec.Location))
	if len(obs.InUse) == 0 {
		obs.Completion = "CONSUMERS_IDLE"
	}
	return obs
}

// users lists what uses path: running consumer processes, open files inside it
// and processes working inside it.
func (use ProcessUse) users(path string, consumers []string) []string {
	var result []string
	for _, name := range consumers {
		if slices.Contains(use.Names, name) {
			result = append(result, "consumer process running: "+name)
		}
	}
	if slices.ContainsFunc(use.Open, func(p string) bool { return p == path || within(path, p) }) {
		result = append(result, "a process has files open inside this directory")
	}
	if inUse(path, use.Cwds) {
		result = append(result, "a running process has its working directory here")
	}
	return result
}

func consumersOf(policy LifecyclePolicy, path string) []string {
	for _, d := range policy.Paths {
		if d.Path == path {
			return d.Consumers
		}
	}
	return nil
}

// shallowFingerprint digests names, sizes and modification times of at most
// limit entries in the first two levels. Writes inside a build or cache add or
// replace entries there, so it changes without walking millions of files.
func shallowFingerprint(root string, limit int) string {
	var parts []string
	var walk func(dir string, depth int)
	walk = func(dir string, depth int) {
		entries, err := os.ReadDir(dir)
		if err != nil {
			parts = append(parts, dir+":unreadable")
			return
		}
		for _, e := range entries {
			if len(parts) >= limit {
				return
			}
			info, err := e.Info()
			if err != nil {
				continue
			}
			full := filepath.Join(dir, e.Name())
			parts = append(parts, fmt.Sprintf("%s|%d|%d", full, info.Size(), info.ModTime().UnixNano()))
			if e.IsDir() && depth < 2 {
				walk(full, depth+1)
			}
		}
	}
	if info, err := os.Stat(root); err == nil {
		parts = append(parts, fmt.Sprintf("root|%d", info.ModTime().UnixNano()))
	}
	walk(root, 1)
	return Fingerprint(parts)
}

// deletePath claims an eligible path, re-observes it, records a storage
// operation (the SQL guard rechecks protection), detaches the directory by
// renaming it on the same device, measures and removes it, and verifies it is
// gone. A restart leaves at most a detached staging directory, removed later.
func (m *Manager) deletePath(ctx context.Context, rec LifecycleRecord, policy LifecyclePolicy, run *LifecycleRun, now time.Time) {
	token, ok, err := claimLifecycle(ctx, m.Pool, rec.IdentityKey, now, 15*time.Minute)
	if err != nil || !ok {
		return
	}
	use, scanErr := m.processScan()(ctx)
	obs := m.observePath(rec, use, scanErr, policy)
	if !obs.Present || len(obs.InUse) > 0 || len(obs.Blockers) > 0 || obs.Fingerprint != rec.Fingerprint {
		m.reject(ctx, rec, token, Plan{}, errors.New("path changed or is in use since the eligibility decision"))
		return
	}
	operation := newUUID()
	staging := fmt.Sprintf("%s%s%s", rec.Location, stagingMarker, operation)
	identity := map[string]any{"quarantine_location": staging, "evidence_sha256": rec.Fingerprint}
	for k, v := range rec.Identity {
		identity[k] = v
	}
	_, err = m.Pool.Exec(ctx, `INSERT INTO football.storage_operations(operation_id,batch_id,action,resource_id,backend,location,
 identity_key,identity,plan_sha256,approved_by,confirmation) VALUES($1,$2,'DELETE',$3,'filesystem',$4,$5,$6,$7,$8,'policy')`,
		operation, newUUID(), Identity("filesystem", rec.IdentityKey), rec.Location, rec.IdentityKey, identity,
		Fingerprint(rec.IdentityKey, rec.Fingerprint), policy.actor())
	if err == nil {
		err = markDeleting(ctx, m.Pool, rec.IdentityKey, token, operation)
	}
	if err != nil {
		m.reject(ctx, rec, token, Plan{}, err)
		return
	}
	run.Submitted++
	m.removePath(ctx, operation, rec.Location, staging)
	rec.OperationID, rec.State = &operation, LifecycleDeleting
	m.settle(ctx, rec, run, m.now())
}

func (m *Manager) removePath(ctx context.Context, operation, location, staging string) {
	if _, err := m.Pool.Exec(ctx, `UPDATE football.storage_operations SET state='RUNNING',started_at=clock_timestamp()
 WHERE operation_id=$1 AND state='PENDING'`, operation); err != nil {
		m.finish(ctx, operation, "BLOCKED", nil, nil, "protection check rejected execution: "+err.Error())
		return
	}
	measurement := Measurement{Method: "rename on the same device, logical bytes walked, remove, verified absence and host free space",
		HostFreeBefore: freeBytes(filepath.Dir(location))}
	if err := os.Rename(location, staging); err != nil {
		m.finish(ctx, operation, "FAILED", &measurement, nil, "detach failed: "+err.Error())
		return
	}
	measurement.BeforeBytes = treeBytes(staging)
	if err := os.RemoveAll(staging); err != nil {
		m.finish(ctx, operation, "FAILED", &measurement, nil, "removal incomplete: "+err.Error())
		return
	}
	_, err := os.Lstat(staging)
	measurement.VerifiedAbsent = errors.Is(err, fs.ErrNotExist)
	measurement.HostFreeAfter = freeBytes(filepath.Dir(location))
	measurement.ReclaimedBytes = &measurement.BeforeBytes
	m.finish(ctx, operation, "SUCCEEDED", &measurement, &staging, "")
}

// treeBytes sums allocated bytes of a detached tree; it is walked only once,
// at deletion.
func treeBytes(root string) int64 {
	var total int64
	_ = filepath.WalkDir(root, func(_ string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if info, err := d.Info(); err == nil {
			if stat, ok := info.Sys().(*syscall.Stat_t); ok {
				total += stat.Blocks * 512
			}
		}
		return nil
	})
	return total
}

// removeStaging deletes staging directories left by an interrupted deletion of a
// configured path, but only when the operation that detached it is recorded as
// this policy's own.
func (m *Manager) removeStaging(ctx context.Context, policy LifecyclePolicy) {
	for _, d := range policy.Paths {
		matches, _ := filepath.Glob(d.Path + stagingMarker + "*")
		for _, staging := range matches {
			operation := strings.TrimPrefix(staging, d.Path+stagingMarker)
			var ours bool
			if m.Pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM football.storage_operations WHERE operation_id::text=$1
 AND approved_by=$2 AND location=$3)`, operation, policy.actor(), d.Path).Scan(&ours) == nil && ours {
				_ = os.RemoveAll(staging)
			}
		}
	}
}
