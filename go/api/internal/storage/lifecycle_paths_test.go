package storage

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type fakeProcesses struct {
	mu  sync.Mutex
	use ProcessUse
	err error
}

func (f *fakeProcesses) scan(context.Context) (ProcessUse, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.use, f.err
}

func (f *fakeProcesses) set(use ProcessUse, err error) {
	f.mu.Lock()
	f.use, f.err = use, err
	f.mu.Unlock()
}

func writeFile(t *testing.T, path string, size int) {
	t.Helper()
	must(t, os.MkdirAll(filepath.Dir(path), 0o755))
	must(t, os.WriteFile(path, make([]byte, size), 0o644))
}

// pathHarness builds a repository with a Rust target, a shared dependency cache
// with a one-day exemption, a temporary directory and the operating data root.
func pathHarness(t *testing.T) (*lifecycleHarness, *fakeProcesses, map[string]string) {
	t.Helper()
	h := newLifecycleHarness(t, databasePool(t))
	repo, err := filepath.EvalSymlinks(t.TempDir())
	must(t, err)
	paths := map[string]string{"target": filepath.Join(repo, "target"), "cache": filepath.Join(repo, ".local", "go-cache"),
		"tmp": filepath.Join(repo, ".local", "tmp"), "data": filepath.Join(repo, ".local", "football-data")}
	for name, p := range paths {
		writeFile(t, filepath.Join(p, "a", name+".bin"), 64<<10)
	}
	t.Setenv("FOOTBALL_DATA_ROOT", ".local/football-data")
	processes := &fakeProcesses{}
	h.m.Repository = repo
	h.m.ProcessScan = processes.scan
	h.m.Policy.LifecycleCleanup.TestDatabases = false
	h.m.Policy.LifecycleCleanup.Paths = []DisposablePath{
		{Path: paths["target"], Kind: "BUILD_OUTPUT", Consumers: []string{"cargo", "rustc"}},
		{Path: paths["cache"], Kind: "DEPENDENCY_CACHE", Consumers: []string{"go"}, MinIdleSeconds: 86400},
		{Path: paths["tmp"], Kind: "TEMPORARY"},
		{Path: paths["data"], Kind: "TEMPORARY"}, // misconfigured: the data root must never be deleted
	}
	return h, processes, paths
}

func pathKey(t *testing.T, path string) string {
	t.Helper()
	key, _, err := pathIdentity(path)
	must(t, err)
	return key
}

func TestDatabaseLifecyclePathsFiveHourDeletionAndActivity(t *testing.T) {
	h, processes, paths := pathHarness(t)
	target, tmp := pathKey(t, paths["target"]), pathKey(t, paths["tmp"])
	processes.set(ProcessUse{Names: []string{"cargo"}, Open: []string{paths["tmp"] + "/a/tmp.bin"}}, nil)
	h.advance(time.Minute)
	expect(t, h.record(target).State == LifecycleActive && contains(h.record(target).Blockers, "consumer process running: cargo"), "a running build must keep its output active: %+v", h.record(target))
	expect(t, h.record(tmp).State == LifecycleActive, "an open file must keep a directory active")

	processes.set(ProcessUse{Names: []string{"zsh"}}, nil)
	h.advance(time.Hour)
	r := h.record(target)
	expect(t, r.State == LifecycleWaiting && *r.Completion == "CONSUMERS_IDLE", "an idle build output should wait: %+v", r)

	// A write inside the build output restarts the window.
	h.advance(3 * time.Hour)
	writeFile(t, filepath.Join(paths["target"], "a", "new.o"), 1024)
	h.advance(time.Hour)
	r = h.record(target)
	expect(t, r.State == LifecycleWaiting && r.LastActivityAt.Equal(h.now), "a write did not reset the window: %+v", r)

	h.advance(5*time.Hour - time.Second)
	_, err := os.Stat(paths["target"])
	expect(t, err == nil, "deleted before five hours")
	run := h.advance(time.Second)
	_, err = os.Lstat(paths["target"])
	r = h.record(target)
	expect(t, run.Deleted >= 1 && errors.Is(err, os.ErrNotExist) && r.State == LifecycleDeleted && *r.ReclaimedBytes > 0, "not deleted at five hours: %+v %+v", run, r)
	staging, _ := filepath.Glob(paths["target"] + stagingMarker + "*")
	expect(t, len(staging) == 0, "staging left behind: %v", staging)
	var actor, state string
	must(t, h.pool.QueryRow(context.Background(), `SELECT approved_by,state FROM football.storage_operations WHERE operation_id=$1`, *r.OperationID).Scan(&actor, &state))
	expect(t, actor == "policy:test-approval:owner" && state == "SUCCEEDED", "operation %s %s", actor, state)

	// A rebuilt directory is a new resource with its own window.
	writeFile(t, filepath.Join(paths["target"], "a", "rebuilt.o"), 1024)
	h.advance(time.Minute)
	rebuilt := h.record(pathKey(t, paths["target"]))
	expect(t, rebuilt.IdentityKey != target && rebuilt.State == LifecycleWaiting, "rebuilt output not tracked anew: %+v", rebuilt)
}

func TestDatabaseLifecyclePathsExemptionsProtectionAndScanFailure(t *testing.T) {
	h, processes, paths := pathHarness(t)
	cache, data := pathKey(t, paths["cache"]), pathKey(t, paths["data"])
	processes.set(ProcessUse{}, errors.New("lsof unavailable"))
	h.advance(time.Minute)
	expect(t, h.record(cache).State == LifecycleActive, "unknown process activity must count as use")
	processes.set(ProcessUse{}, nil)
	h.advance(time.Minute)
	h.advance(6 * time.Hour)
	_, err := os.Stat(paths["cache"])
	expect(t, err == nil && h.record(cache).State == LifecycleWaiting, "an exempt cache was deleted after five hours: %+v", h.record(cache))
	h.advance(18 * time.Hour)
	_, err = os.Lstat(paths["cache"])
	expect(t, errors.Is(err, os.ErrNotExist), "an exempt cache was kept after its own window")

	r := h.record(data)
	_, err = os.Stat(filepath.Join(paths["data"], "a", "data.bin"))
	expect(t, r.State == LifecycleBlocked && contains(r.Blockers, "path overlaps the operating data root") && err == nil, "the data root was not protected: %+v", r)
}

func TestDatabaseLifecyclePathsInterruptedDeletion(t *testing.T) {
	h, processes, paths := pathHarness(t)
	ctx := context.Background()
	processes.set(ProcessUse{}, nil)
	h.advance(time.Minute)
	key := pathKey(t, paths["tmp"])
	rec := h.record(key)
	// Interrupted before the directory was detached: recovery must not claim success.
	operation := newUUID()
	identity := map[string]any{"path": paths["tmp"], "device": rec.Identity["device"], "inode": rec.Identity["inode"],
		"quarantine_location": paths["tmp"] + stagingMarker + operation}
	_, err := h.pool.Exec(ctx, `INSERT INTO football.storage_operations(operation_id,batch_id,action,resource_id,backend,location,identity_key,identity,plan_sha256,approved_by,confirmation)
 VALUES($1,$2,'DELETE',$3,'filesystem',$4,$5,$6,$7,'policy:test-approval:owner','policy')`, operation, newUUID(), Identity("filesystem", key), paths["tmp"], key, identity, strings.Repeat("d", 64))
	must(t, err)
	_, err = h.pool.Exec(ctx, `UPDATE football.storage_operations SET state='RUNNING' WHERE operation_id=$1`, operation)
	must(t, err)
	must(t, h.m.Recover(ctx))
	var state string
	must(t, h.pool.QueryRow(ctx, `SELECT state FROM football.storage_operations WHERE operation_id=$1`, operation).Scan(&state))
	expect(t, state == "FAILED", "an undetached path was recorded as deleted: %s", state)

	// A staging directory left by this policy is removed; a foreign one is not.
	ours := paths["tmp"] + stagingMarker + operation
	foreign := paths["tmp"] + stagingMarker + newUUID()
	writeFile(t, filepath.Join(ours, "x"), 10)
	writeFile(t, filepath.Join(foreign, "x"), 10)
	h.advance(time.Minute)
	_, errOurs := os.Lstat(ours)
	_, errForeign := os.Lstat(foreign)
	expect(t, errors.Is(errOurs, os.ErrNotExist) && errForeign == nil, "staging cleanup: ours=%v foreign=%v", errOurs, errForeign)
}

func TestDisposablePathValidation(t *testing.T) {
	base := LifecyclePolicy{InactivitySeconds: 18000, CheckIntervalSeconds: 900, MaxPerRun: 5, ApprovedBy: "o", ApprovalRecord: "r"}
	for name, paths := range map[string][]DisposablePath{
		"relative":     {{Path: "target", Kind: "BUILD_OUTPUT", Consumers: []string{"cargo"}}},
		"no consumers": {{Path: "/r/target", Kind: "BUILD_OUTPUT"}},
		"short idle":   {{Path: "/r/target", Kind: "BUILD_OUTPUT", Consumers: []string{"cargo"}, MinIdleSeconds: 3600}},
		"unknown kind": {{Path: "/r/target", Kind: "DATA", Consumers: []string{"x"}}},
		"overlap":      {{Path: "/r/.local", Kind: "TEMPORARY"}, {Path: "/r/.local/tmp", Kind: "TEMPORARY"}},
		"protected":    {{Path: "/r/keep/cache", Kind: "TEMPORARY"}},
	} {
		p := base
		p.Paths = paths
		expect(t, p.validate([]string{"/r/keep"}) != nil, "%s accepted", name)
	}
	p := base
	p.Paths = []DisposablePath{{Path: "/r/target", Kind: "BUILD_OUTPUT", Consumers: []string{"cargo"}}, {Path: "/r/.local/tmp", Kind: "TEMPORARY"}}
	expect(t, p.validate(nil) == nil, "valid paths rejected")
}
