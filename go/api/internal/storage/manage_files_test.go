package storage

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func managedPolicy(t *testing.T, class string) (Policy, string) {
	t.Helper()
	base := t.TempDir()
	base, _ = filepath.EvalSymlinks(base)
	root := filepath.Join(base, "managed")
	must(t, os.MkdirAll(root, 0o700))
	p := Policy{MaxEntries: 10_000, ScanSeconds: 5, ManagedRoots: []ManagedRoot{{Path: root, Class: class}},
		ProtectedPaths: []string{filepath.Join(root, "evidence")}}
	return p, root
}

func write(t *testing.T, path string, size int) {
	t.Helper()
	must(t, os.MkdirAll(filepath.Dir(path), 0o700))
	must(t, os.WriteFile(path, []byte(strings.Repeat("x", size)), 0o600))
}

func byName(resources []ManagedResource, name string) ManagedResource {
	for _, r := range resources {
		if r.Name == name {
			return r
		}
	}
	return ManagedResource{}
}

func TestFilesystemClassificationProtectsEvidenceLinksAndActiveUse(t *testing.T) {
	InvalidateMeasurements()
	p, root := managedPolicy(t, "disposable")
	write(t, filepath.Join(root, "cache", "a.bin"), 10_000)
	write(t, filepath.Join(root, "evidence", "receipt.json"), 100)
	write(t, filepath.Join(root, "busy", "x"), 10)
	outside := t.TempDir()
	must(t, os.Symlink(outside, filepath.Join(root, "link")))
	resources := ListFilesystem(context.Background(), p, map[string][]string{}, nil, []string{filepath.Join(root, "busy")}, time.Now())
	{
		r := byName(resources, "cache")
		expect(t, !(r.Classification != Eligible || !r.Allows(ActionDelete) || *r.AllocatedBytes < 10_000), "disposable cache: %+v", r)
	}
	{
		r := byName(resources, "evidence")
		expect(t, !(r.Classification != Protected || r.Allows(ActionDelete)), "protected evidence: %+v", r)
	}
	{
		r := byName(resources, "busy")
		expect(t, !(r.Classification != Protected), "directory in use: %+v", r)
	}
	{
		r := byName(resources, "link")
		expect(t, !(r.Classification == Eligible || r.Allows(ActionDelete)), "symlink offered for deletion: %+v", r)
	}
	// Owner protection by device+inode survives a rename.
	cache := byName(resources, "cache")
	must(t, os.Rename(filepath.Join(root, "cache"), filepath.Join(root, "cache-renamed")))
	InvalidateMeasurements()
	resources = ListFilesystem(context.Background(), p, map[string][]string{cache.IdentityKey: {"OWNER_PROTECTED: keep"}}, nil, nil, time.Now())
	{
		r := byName(resources, "cache-renamed")
		expect(t, !(r.Classification != Protected), "rename bypassed protection: %+v", r)
	}
}

func TestFilesystemReviewRootNeedsDisposition(t *testing.T) {
	InvalidateMeasurements()
	p, root := managedPolicy(t, "review")
	write(t, filepath.Join(root, "task-output", "report.json"), 100)
	r := byName(ListFilesystem(context.Background(), p, map[string][]string{}, nil, nil, time.Now()), "task-output")
	expect(t, !(r.Classification != ReviewRequired || r.Allows(ActionDelete) || r.EvidenceSHA256 == ""), "review root child: %+v", r)
	applyDisposition(&r, &Disposition{Disposition: "UNIQUE_DATA_NOT_REQUIRED"})
	r.finish()
	expect(t, !(r.Classification != Eligible || !r.Allows(ActionDelete)), "disposition did not resolve review: %+v", r)
}

func TestFilesystemExecutorRefusesTraversalNestedAndSwappedTargets(t *testing.T) {
	p, root := managedPolicy(t, "disposable")
	x := fileExecutor{policy: p}
	for _, path := range []string{filepath.Join(root, "..", "escape"), filepath.Join(root, "a", "b"), "/etc", filepath.Join(root, QuarantineDirectory)} {
		if _, _, err := x.root(path); err == nil {
			t.Fatalf("accepted unmanaged path %s", path)
		}
	}
	write(t, filepath.Join(root, "cache", "a"), 10)
	InvalidateMeasurements()
	r := byName(ListFilesystem(context.Background(), p, map[string][]string{}, nil, nil, time.Now()), "cache")
	// Replace the directory with a different inode between approval and execution.
	must(t, os.RemoveAll(filepath.Join(root, "cache")))
	write(t, filepath.Join(root, "cache", "b"), 10)
	if _, err := x.Delete(context.Background(), r); err == nil || !strings.Contains(err.Error(), "identity changed") {
		t.Fatalf("swapped target deleted: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, "cache", "b")); err != nil {
		t.Fatal("swapped target was touched")
	}
}

func TestFilesystemQuarantineRestoreAndDeleteMeasureSpace(t *testing.T) {
	p, root := managedPolicy(t, "disposable")
	write(t, filepath.Join(root, "build", "out.bin"), 50_000)
	InvalidateMeasurements()
	r := byName(ListFilesystem(context.Background(), p, map[string][]string{}, nil, nil, time.Now()), "build")
	x := fileExecutor{policy: p}
	_, target, err := x.Quarantine(context.Background(), r, "11111111-1111-4111-8111-111111111111")
	must(t, err)
	if _, err = os.Stat(filepath.Join(root, "build")); !os.IsNotExist(err) {
		t.Fatal("original still present after quarantine")
	}
	r.Quarantine = &QuarantineInfo{OriginalLocation: filepath.Join(root, "build"), QuarantineLocation: target}
	if _, err = x.Restore(context.Background(), r); err != nil {
		t.Fatal(err)
	}
	if _, err = os.Stat(filepath.Join(root, "build", "out.bin")); err != nil {
		t.Fatal("restore lost data")
	}
	r.Quarantine = nil
	m, err := x.Delete(context.Background(), r)
	must(t, err)
	expect(t, !(!m.VerifiedAbsent || m.ReclaimedBytes == nil || *m.ReclaimedBytes < 50_000), "deletion not measured: %+v", m)
}

func TestUniqueBytesCountsNestedAndDuplicateResourcesOnce(t *testing.T) {
	ten, five := int64(10), int64(5)
	resources := []ManagedResource{
		{IdentityKey: "a", Backend: "git", Location: "/w/one", AllocatedBytes: &ten},
		{IdentityKey: "b", Backend: "filesystem", Location: "/w/one/.local/cache", AllocatedBytes: &five},
		{IdentityKey: "a", Backend: "git", Location: "/w/one", AllocatedBytes: &ten},
		{IdentityKey: "c", Backend: "postgres", Location: "1/db", AllocatedBytes: &five},
	}
	if got := uniqueBytes(resources); got != 15 {
		t.Fatalf("unique bytes %d", got)
	}
}

func git(t *testing.T, dir string, args ...string) string {
	t.Helper()
	output, err := exec.Command("git", append([]string{"-C", dir}, args...)...).CombinedOutput()
	expect(t, !(err != nil), "git %v: %v %s", args, err, output)
	return strings.TrimSpace(string(output))
}

func TestWorktreeClassificationAndRemoval(t *testing.T) {
	InvalidateMeasurements()
	base, _ := filepath.EvalSymlinks(t.TempDir())
	remote, repo := filepath.Join(base, "remote.git"), filepath.Join(base, "repo")
	git(t, base, "init", "-q", "--bare", remote)
	git(t, base, "init", "-q", "-b", "main", repo)
	git(t, repo, "config", "user.email", "test@example.invalid")
	git(t, repo, "config", "user.name", "test")
	write(t, filepath.Join(repo, ".gitignore"), 0)
	must(t, os.WriteFile(filepath.Join(repo, ".gitignore"), []byte("node_modules/\n.local/\n"), 0o600))
	git(t, repo, "add", ".")
	git(t, repo, "commit", "-q", "-m", "init")
	git(t, repo, "remote", "add", "origin", remote)
	git(t, repo, "push", "-q", "origin", "main")
	git(t, repo, "fetch", "-q", "origin")
	clean, evidence, dirty := filepath.Join(base, "clean"), filepath.Join(base, "evidence"), filepath.Join(base, "dirty")
	for _, w := range []string{clean, evidence, dirty} {
		git(t, repo, "worktree", "add", "-q", "--detach", w, "main")
	}
	write(t, filepath.Join(clean, "node_modules", "x.js"), 10)
	write(t, filepath.Join(evidence, ".local", "receipt.json"), 10)
	write(t, filepath.Join(dirty, "new.txt"), 10)
	resources, err := ListWorktrees(context.Background(), repo, map[string][]string{}, nil, 10_000, time.Now())
	must(t, err)
	{
		r := byName(resources, "repo")
		expect(t, !(r.Classification != Protected), "primary checkout: %+v", r)
	}
	{
		r := byName(resources, "evidence")
		expect(t, !(r.Classification != ReviewRequired || r.Allows(ActionDelete)), "ignored evidence: %+v", r)
	}
	{
		r := byName(resources, "dirty")
		expect(t, !(r.Classification != ReviewRequired || r.Allows(ActionDelete)), "dirty worktree: %+v", r)
	}
	r := byName(resources, "clean")
	expect(t, !(r.Classification != Eligible || !r.Allows(ActionDelete) || r.Allows(ActionQuarantine)), "clean worktree: %+v", r)
	m, err := worktreeExecutor{repository: repo}.Delete(context.Background(), r)
	expect(t, !(err != nil || !m.VerifiedAbsent), "worktree removal: %+v %v", m, err)
	if _, err = os.Stat(dirty); err != nil {
		t.Fatal("unrelated worktree touched")
	}
}

func must(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func expect(t *testing.T, ok bool, message string, args ...any) {
	t.Helper()
	if !ok {
		t.Fatalf(message, args...)
	}
}

func TestAutomaticCleanupSelectsOnlyAgedDisposableFilesWithinBounds(t *testing.T) {
	now := time.Now()
	old, recent := now.Add(-72*time.Hour), now.Add(-time.Hour)
	rule := AutomaticPolicy{Action: "DELETE_DISPOSABLE", Root: "/m/cache", MinAgeSeconds: 86400, MaxPerRun: 2, ApprovedBy: "owner", ApprovalRecord: "rec"}
	file := func(name string, modified time.Time, backend string, class Classification) ManagedResource {
		r := ManagedResource{Backend: backend, Name: name, Location: "/m/cache/" + name, IdentityKey: "k" + name, Classification: class, Details: map[string]any{"modified_at": modified}}
		r.finish()
		r.ResourceID = name
		return r
	}
	resources := []ManagedResource{
		file("a", old, "filesystem", Eligible), file("b", recent, "filesystem", Eligible), file("c", old, "filesystem", Protected),
		file("d", old, "postgres", Eligible), file("e", old, "git", Eligible), file("f", old, "filesystem", Eligible), file("g", old, "filesystem", Eligible),
	}
	ids, action := automaticCandidates(resources, rule, now)
	expect(t, action == ActionDelete && len(ids) == 2 && ids[0] == "a" && ids[1] == "f", "unexpected automatic selection %v", ids)
	elsewhere := rule
	elsewhere.Root = "/m/other"
	ids, _ = automaticCandidates(resources, elsewhere, now)
	expect(t, len(ids) == 0, "selected outside the approved root: %v", ids)
	p := Policy{ManagedRoots: []ManagedRoot{{Path: "/m/cache", Class: "review"}}}
	expect(t, p.validateAutomatic(rule) != nil, "automatic cleanup accepted a review root")
	p.ManagedRoots[0].Class = "disposable"
	expect(t, p.validateAutomatic(rule) == nil, "valid automatic rule rejected")
	rule.MinAgeSeconds = 60
	expect(t, p.validateAutomatic(rule) != nil, "automatic cleanup accepted an age under one day")
}
