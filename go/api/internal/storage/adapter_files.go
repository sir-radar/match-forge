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
	"sync"
	"syscall"
	"time"
)

// QuarantineDirectory is created inside each managed root so that quarantine is
// an atomic same-device rename that never leaves the declared root.
const QuarantineDirectory = ".matchforge-quarantine"

// measureCache keeps bounded tree measurements between requests. A refresh drops it.
type measureCache struct {
	mu      sync.Mutex
	entries map[string]treeMeasure
}

type treeMeasure struct {
	logical, allocated int64
	entries            int
	complete           bool
	errors             []string
	at                 time.Time
}

var measurements = measureCache{entries: map[string]treeMeasure{}}

const measureTTL = 15 * time.Minute

// InvalidateMeasurements forces the next listing to re-measure every tree.
func InvalidateMeasurements() {
	measurements.mu.Lock()
	measurements.entries = map[string]treeMeasure{}
	measurements.mu.Unlock()
}

func measureTree(ctx context.Context, path string, maxEntries int, budget time.Duration) treeMeasure {
	key := path
	measurements.mu.Lock()
	cached, ok := measurements.entries[key]
	measurements.mu.Unlock()
	if ok && time.Since(cached.at) < measureTTL {
		return cached
	}
	limited, cancel := context.WithTimeout(ctx, budget)
	defer cancel()
	p := Policy{MaxEntries: maxEntries}
	s := scanCount{Errors: []string{}, seen: map[[2]uint64]bool{}}
	m := treeMeasure{at: time.Now()}
	handle, err := os.OpenRoot(path)
	if err != nil {
		m.errors = []string{err.Error()}
		return m
	}
	defer handle.Close()
	err = fs.WalkDir(handle.FS(), ".", func(name string, entry fs.DirEntry, err error) error {
		return s.visit(limited, p, entry, name, err)
	})
	if err != nil {
		s.recordError(err.Error())
	}
	m.logical, m.allocated, m.entries = s.Logical, s.Allocated, s.Entries
	m.complete = s.ErrorCount == 0
	m.errors = s.Errors
	measurements.mu.Lock()
	measurements.entries[key] = m
	measurements.mu.Unlock()
	return m
}

// processDirectories returns the working directories of the current user's
// processes, so a worktree or directory in active use is never removed.
func processDirectories(ctx context.Context) ([]string, error) {
	output, err := exec.CommandContext(ctx, "lsof", "-a", "-d", "cwd", "-F", "n", "-u", fmt.Sprint(os.Getuid())).Output()
	if err != nil && len(output) == 0 {
		return nil, err
	}
	var result []string
	for _, line := range strings.Split(string(output), "\n") {
		if strings.HasPrefix(line, "n/") {
			result = append(result, filepath.Clean(line[1:]))
		}
	}
	return result, nil
}

func inUse(path string, cwds []string) bool {
	return slices.ContainsFunc(cwds, func(cwd string) bool { return cwd == path || within(path, cwd) })
}

func protectedBy(path string, protected []string) string {
	for _, p := range protected {
		if p == path || within(p, path) || within(path, p) {
			return p
		}
	}
	return ""
}

func fileIdentity(info os.FileInfo) (uint64, uint64, error) {
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return 0, 0, errors.New("filesystem identity unavailable")
	}
	return uint64(stat.Dev), stat.Ino, nil
}

// FilesystemIdentityKey binds protection to the device and inode, which survive a
// rename inside the same filesystem.
func FilesystemIdentityKey(dev, ino uint64) string { return fmt.Sprintf("filesystem:%d:%d", dev, ino) }

// ListFilesystem assesses direct children of the policy's managed roots.
func ListFilesystem(ctx context.Context, p Policy, protections map[string][]string, quarantined map[string]QuarantineInfo, cwds []string, now time.Time) []ManagedResource {
	result := []ManagedResource{}
	budget := time.Duration(max(p.ScanSeconds, 5)) * time.Second
	for _, root := range p.ManagedRoots {
		entries, err := os.ReadDir(root.Path)
		if err != nil {
			continue
		}
		rootInfo, err := os.Lstat(root.Path)
		if err != nil || rootInfo.Mode()&os.ModeSymlink != 0 {
			continue
		}
		rootDev, _, _ := fileIdentity(rootInfo)
		for _, entry := range entries {
			if entry.Name() == QuarantineDirectory {
				continue
			}
			path := filepath.Join(root.Path, entry.Name())
			r := assessFile(ctx, p, root, path, rootDev, protections, cwds, budget, now)
			if q, ok := quarantined[r.IdentityKey]; ok {
				q := q
				r.Quarantine = &q
			}
			r.finish()
			result = append(result, r)
		}
		result = append(result, quarantinedFiles(root, quarantined, now)...)
	}
	return result
}

func assessFile(ctx context.Context, p Policy, root ManagedRoot, path string, rootDev uint64, protections map[string][]string, cwds []string, budget time.Duration, now time.Time) ManagedResource {
	r := ManagedResource{Backend: "filesystem", Kind: "directory", Name: filepath.Base(path), Location: path, ObservedAt: now,
		Purpose: strings.ToUpper(root.Class), Details: map[string]any{"managed_root": root.Path, "root_description": root.Description}}
	info, ok := inspectFile(&r, path)
	if !ok {
		return r
	}
	dev, _, _ := fileIdentity(info)
	if dev != rootDev {
		r.classify(Protected, "different filesystem from its managed root (mount point)")
	}
	protectFile(&r, p, protections, cwds)
	m := measureFile(ctx, info, path, p.MaxEntries, budget)
	r.LogicalBytes, r.AllocatedBytes, r.Complete = &m.logical, &m.allocated, m.complete
	r.Details["entries"] = m.entries
	r.Details["measurement"] = "allocated bytes, hard links once; APFS clones may share extents"
	if !m.complete {
		r.classify(ReviewRequired, "measurement incomplete; size is a lower bound")
		r.Details["measurement_errors"] = m.errors
	}
	r.EvidenceSHA256 = Fingerprint(r.IdentityKey, path, m.allocated, m.entries, info.ModTime().UnixNano())
	if root.Class == "disposable" {
		r.classify(Eligible, "direct child of an owner-declared disposable root ("+root.Path+")")
		return r
	}
	r.review("may hold unique evidence or task output", "Inspect the contents, then record that they are not required, or protect them.")
	return r
}

// inspectFile resolves the identity without following links.
func inspectFile(r *ManagedResource, path string) (os.FileInfo, bool) {
	info, err := os.Lstat(path)
	if err != nil {
		r.IdentityKey = "filesystem:missing:" + path
		r.classify(ReviewRequired, "cannot inspect: "+err.Error())
		return nil, false
	}
	dev, ino, err := fileIdentity(info)
	r.IdentityKey = FilesystemIdentityKey(dev, ino)
	r.Identity = map[string]any{"device": dev, "inode": ino, "path": path}
	switch {
	case err != nil:
		r.classify(ReviewRequired, err.Error())
		return nil, false
	case info.Mode()&os.ModeSymlink != 0:
		r.classify(ReviewRequired, "symbolic link; links are never followed or removed by Storage Management")
		return nil, false
	case info.Mode().IsRegular():
		r.Kind = "file"
	}
	return info, true
}

func protectFile(r *ManagedResource, p Policy, protections map[string][]string, cwds []string) {
	if protected := protectedBy(r.Location, p.ProtectedPaths); protected != "" {
		r.Role = "REQUIRED_EVIDENCE"
		r.classify(Protected, "inside or containing protected path "+protected)
	}
	for _, reason := range protections[r.IdentityKey] {
		r.Role = strings.SplitN(reason, ":", 2)[0]
		r.classify(Protected, reason)
	}
	if inUse(r.Location, cwds) {
		r.classify(Protected, "a running process has its working directory here")
	}
}

func measureFile(ctx context.Context, info os.FileInfo, path string, maxEntries int, budget time.Duration) treeMeasure {
	if info.IsDir() {
		return measureTree(ctx, path, maxEntries, budget)
	}
	blocks := int64(0)
	if stat, ok := info.Sys().(*syscall.Stat_t); ok {
		blocks = stat.Blocks
	}
	return treeMeasure{logical: info.Size(), allocated: blocks * 512, entries: 1, complete: true}
}

func quarantinedFiles(root ManagedRoot, quarantined map[string]QuarantineInfo, now time.Time) []ManagedResource {
	var result []ManagedResource
	for key, q := range quarantined {
		if !strings.HasPrefix(key, "filesystem:") || !strings.HasPrefix(q.QuarantineLocation, filepath.Join(root.Path, QuarantineDirectory)+string(filepath.Separator)) {
			continue
		}
		q := q
		r := ManagedResource{Backend: "filesystem", Kind: "quarantine", Name: filepath.Base(q.OriginalLocation), Location: q.QuarantineLocation,
			IdentityKey: key, ObservedAt: now, Purpose: "QUARANTINED", Quarantine: &q, Complete: true,
			Details: map[string]any{"managed_root": root.Path}}
		if info, err := os.Lstat(q.QuarantineLocation); err == nil {
			m := treeMeasure{}
			if info.IsDir() {
				m = measureTree(context.Background(), q.QuarantineLocation, 5_000_000, 30*time.Second)
			} else {
				m.allocated = info.Sys().(*syscall.Stat_t).Blocks * 512
				m.logical = info.Size()
			}
			r.LogicalBytes, r.AllocatedBytes = &m.logical, &m.allocated
			r.classify(Eligible, "quarantined; restorable until purged")
		} else {
			r.classify(ReviewRequired, "quarantined copy is missing: "+err.Error())
		}
		r.finish()
		result = append(result, r)
	}
	return result
}

// fileExecutor operates only on direct children of a declared managed root,
// through an os.Root handle so traversal and symlink escapes are impossible.
type fileExecutor struct{ policy Policy }

func (x fileExecutor) root(path string) (*ManagedRoot, string, error) {
	for _, root := range x.policy.ManagedRoots {
		rel, err := filepath.Rel(root.Path, path)
		if err == nil && filepath.IsLocal(rel) && !strings.Contains(rel, string(filepath.Separator)) && rel != QuarantineDirectory {
			root := root
			return &root, rel, nil
		}
	}
	return nil, "", errors.New("path is not a direct child of a managed root")
}

func (x fileExecutor) verify(r ManagedResource, handle *os.Root, name string) (os.FileInfo, error) {
	info, err := handle.Lstat(name)
	if err != nil {
		return nil, err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("target became a symbolic link")
	}
	dev, ino, err := fileIdentity(info)
	if err != nil {
		return nil, err
	}
	if FilesystemIdentityKey(dev, ino) != r.IdentityKey {
		return nil, errors.New("target identity changed since approval")
	}
	return info, nil
}

func (x fileExecutor) Delete(ctx context.Context, r ManagedResource) (Measurement, error) {
	m := Measurement{Method: "allocated bytes of the exact tree, then verified absence and host free space"}
	path := r.Location
	if r.Quarantine != nil {
		path = r.Quarantine.QuarantineLocation
	}
	rootPath, name, err := x.locate(path, r.Quarantine != nil)
	if err != nil {
		return m, err
	}
	handle, err := os.OpenRoot(rootPath)
	if err != nil {
		return m, err
	}
	defer handle.Close()
	if _, err = x.verify(r, handle, name); err != nil {
		return m, err
	}
	InvalidateMeasurements()
	before := measureTree(ctx, path, 50_000_000, 10*time.Minute)
	if !before.complete {
		return m, errors.New("pre-deletion measurement incomplete; deletion refused")
	}
	m.BeforeBytes = before.allocated
	m.HostFreeBefore = freeBytes(rootPath)
	if err = handle.RemoveAll(name); err != nil {
		return m, err
	}
	if _, err = handle.Lstat(name); !errors.Is(err, fs.ErrNotExist) {
		return m, errors.New("target still present after removal")
	}
	m.VerifiedAbsent = true
	m.HostFreeAfter = freeBytes(rootPath)
	m.ReclaimedBytes = &before.allocated
	return m, nil
}

// locate returns the directory handle root and the single-component name.
func (x fileExecutor) locate(path string, quarantined bool) (string, string, error) {
	if quarantined {
		for _, root := range x.policy.ManagedRoots {
			base := filepath.Join(root.Path, QuarantineDirectory)
			rel, err := filepath.Rel(base, path)
			if err == nil && filepath.IsLocal(rel) {
				return base, rel, nil
			}
		}
		return "", "", errors.New("quarantine location is outside managed roots")
	}
	root, name, err := x.root(path)
	if err != nil {
		return "", "", err
	}
	return root.Path, name, nil
}

func (x fileExecutor) Quarantine(ctx context.Context, r ManagedResource, operationID string) (Measurement, string, error) {
	m := Measurement{Method: "same-device rename into the root's quarantine directory"}
	root, name, err := x.root(r.Location)
	if err != nil {
		return m, "", err
	}
	handle, err := os.OpenRoot(root.Path)
	if err != nil {
		return m, "", err
	}
	defer handle.Close()
	if _, err = x.verify(r, handle, name); err != nil {
		return m, "", err
	}
	if err = handle.MkdirAll(filepath.Join(QuarantineDirectory, operationID), 0o700); err != nil {
		return m, "", err
	}
	target := filepath.Join(QuarantineDirectory, operationID, name)
	if err = handle.Rename(name, target); err != nil {
		return m, "", err
	}
	zero := int64(0)
	m.ReclaimedBytes = &zero
	return m, filepath.Join(root.Path, target), nil
}

func (x fileExecutor) Restore(_ context.Context, r ManagedResource) (Measurement, error) {
	m := Measurement{Method: "same-device rename back to the original path"}
	if r.Quarantine == nil {
		return m, errors.New("resource is not quarantined")
	}
	root, name, err := x.root(r.Quarantine.OriginalLocation)
	if err != nil {
		return m, err
	}
	handle, err := os.OpenRoot(root.Path)
	if err != nil {
		return m, err
	}
	defer handle.Close()
	rel, err := filepath.Rel(root.Path, r.Quarantine.QuarantineLocation)
	if err != nil || !filepath.IsLocal(rel) {
		return m, errors.New("quarantine location is outside its managed root")
	}
	if _, err = x.verify(r, handle, rel); err != nil {
		return m, err
	}
	if _, err = handle.Lstat(name); err == nil {
		return m, errors.New("original path is occupied; restore refused")
	}
	if err = handle.Rename(rel, name); err != nil {
		return m, err
	}
	_ = handle.Remove(filepath.Dir(rel))
	zero := int64(0)
	m.ReclaimedBytes = &zero
	return m, nil
}

func freeBytes(path string) *int64 {
	c, err := DiskCapacity(path)
	if err != nil {
		return nil
	}
	return &c.FreeBytes
}
