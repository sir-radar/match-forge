package storage

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// Regenerable ignored output that a worktree removal may discard. Anything else
// that Git ignores (for example `.local` task evidence) needs owner review.
var regenerableIgnored = []string{
	"node_modules/", "web/node_modules/", ".venv/", "target/", ".next/", "web/.next/",
	".pytest_cache/", ".mypy_cache/", ".ruff_cache/", "__pycache__/", ".tools/", ".hypothesis/",
	".local/bin/", ".local/dist/", "web/test-results/", "web/playwright-report/",
	"web/tsconfig.tsbuildinfo", "web/next-env.d.ts", ".coverage",
}

func regenerable(path string) bool {
	for _, prefix := range regenerableIgnored {
		if path == prefix || strings.HasPrefix(path, prefix) || strings.Contains(path, "/__pycache__/") || strings.HasSuffix(path, "/__pycache__/") {
			return true
		}
	}
	return false
}

type worktreeEntry struct {
	path, head, branch string
	locked, prunable   bool
}

func parseWorktrees(output string) []worktreeEntry {
	var result []worktreeEntry
	var current *worktreeEntry
	for _, field := range strings.Split(output, "\n") {
		switch {
		case strings.HasPrefix(field, "worktree "):
			result = append(result, worktreeEntry{path: strings.TrimPrefix(field, "worktree ")})
			current = &result[len(result)-1]
		case current == nil:
		case strings.HasPrefix(field, "HEAD "):
			current.head = strings.TrimPrefix(field, "HEAD ")
		case strings.HasPrefix(field, "branch "):
			current.branch = strings.TrimPrefix(field, "branch ")
		case strings.HasPrefix(field, "locked"):
			current.locked = true
		case strings.HasPrefix(field, "prunable"):
			current.prunable = true
		}
	}
	return result
}

// ListWorktrees assesses every Git worktree of the repository.
func ListWorktrees(ctx context.Context, repository string, protections map[string][]string, cwds []string, maxEntries int, now time.Time) ([]ManagedResource, error) {
	output, err := gitRead(ctx, repository, "worktree", "list", "--porcelain")
	if err != nil {
		return nil, err
	}
	common, err := gitRead(ctx, repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
	if err != nil {
		return nil, err
	}
	common = strings.TrimSpace(common)
	result := []ManagedResource{}
	for i, w := range parseWorktrees(output) {
		r := assessWorktree(ctx, w, i == 0, common, repository, protections, cwds, maxEntries, now)
		r.finish()
		result = append(result, r)
	}
	return result, nil
}

func assessWorktree(ctx context.Context, w worktreeEntry, primary bool, common, repository string, protections map[string][]string, cwds []string, maxEntries int, now time.Time) ManagedResource {
	r := ManagedResource{Backend: "git", Kind: "worktree", Name: filepath.Base(w.path), Location: w.path, ObservedAt: now,
		Purpose: "WORKTREE", Details: map[string]any{"head": w.head, "branch": strings.TrimPrefix(w.branch, "refs/heads/")}}
	gitDir := worktreeGitDir(ctx, w.path, primary, common)
	r.IdentityKey = "git:" + gitDir
	if gitDir == "" {
		r.IdentityKey = "git:unresolved:" + w.path
	}
	r.Identity = map[string]any{"git_dir": gitDir, "path": w.path, "head": w.head}
	if primary {
		r.Role = "PRIMARY_CHECKOUT"
		r.classify(Protected, "primary repository checkout")
		return r
	}
	protectWorktree(&r, w, repository, protections, cwds)
	if w.prunable || gitDir == "" {
		r.classify(ReviewRequired, "worktree directory is missing or unreadable")
		return r
	}
	status := worktreeStatus(ctx, &r)
	unique := worktreeIgnored(ctx, &r)
	m := measureTree(ctx, w.path, maxEntries, 30*time.Second)
	r.LogicalBytes, r.AllocatedBytes, r.Complete = &m.logical, &m.allocated, m.complete
	if !m.complete {
		r.classify(ReviewRequired, "measurement incomplete; size is a lower bound")
	}
	r.EvidenceSHA256 = Fingerprint(r.IdentityKey, w.head, status, unique)
	if len(unique) > 0 {
		r.review("ignored files that may be unique task evidence: "+strings.Join(firstN(unique, 5), ", "),
			"Preserve or archive the ignored files, or record that they are not required.")
		return r
	}
	r.classify(Eligible, "clean, pushed and holds only regenerable ignored output")
	return r
}

func worktreeGitDir(ctx context.Context, path string, primary bool, common string) string {
	if primary {
		return common
	}
	value, err := gitRead(ctx, path, "rev-parse", "--path-format=absolute", "--git-dir")
	if err != nil {
		return ""
	}
	return strings.TrimSpace(value)
}

func protectWorktree(r *ManagedResource, w worktreeEntry, repository string, protections map[string][]string, cwds []string) {
	for _, reason := range protections[r.IdentityKey] {
		r.Role = strings.SplitN(reason, ":", 2)[0]
		r.classify(Protected, reason)
	}
	if w.locked {
		r.classify(Protected, "worktree is locked by its owner")
	}
	if filepath.Clean(w.path) == filepath.Clean(repository) {
		r.classify(Protected, "the API runs from this worktree")
	}
	if inUse(w.path, cwds) {
		r.classify(Protected, "a running process has its working directory in this worktree")
	}
}

// worktreeStatus blocks uncommitted, untracked and unpushed work.
func worktreeStatus(ctx context.Context, r *ManagedResource) string {
	status, err := gitRead(ctx, r.Location, "status", "--porcelain", "--untracked-files=all")
	switch {
	case err != nil:
		r.classify(ReviewRequired, "cannot read worktree status")
	case strings.TrimSpace(status) != "":
		r.classify(ReviewRequired, "uncommitted or untracked changes")
		r.Details["status"] = firstLines(status, 10)
		r.Remediation = append(r.Remediation, "Commit, push or discard the changes in the worktree first.")
	}
	remote, err := gitRead(ctx, r.Location, "branch", "-r", "--contains", "HEAD")
	if err != nil || strings.TrimSpace(remote) == "" {
		r.classify(ReviewRequired, "HEAD is not contained in any remote branch")
		r.Remediation = append(r.Remediation, "Push the branch or merge it before removing the worktree.")
	}
	return status
}

// worktreeIgnored lists ignored entries that are not known regenerable output.
func worktreeIgnored(ctx context.Context, r *ManagedResource) []string {
	ignored, err := gitRead(ctx, r.Location, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory")
	if err != nil {
		r.classify(ReviewRequired, "cannot list ignored files")
		return nil
	}
	var unique []string
	for _, line := range strings.Split(strings.TrimSpace(ignored), "\n") {
		if line != "" && !regenerable(line) {
			unique = append(unique, line)
		}
	}
	r.Details["ignored_unique"] = firstN(unique, 20)
	return unique
}

func firstLines(s string, n int) []string {
	return firstN(strings.Split(strings.TrimSpace(s), "\n"), n)
}

func firstN(values []string, n int) []string {
	if len(values) > n {
		return values[:n]
	}
	if values == nil {
		return []string{}
	}
	return values
}

func (worktreeExecutor) Quarantine(context.Context, ManagedResource, string) (Measurement, string, error) {
	return Measurement{}, "", errors.New("worktrees are removed with Git, not quarantined")
}

func (worktreeExecutor) Restore(context.Context, ManagedResource) (Measurement, error) {
	return Measurement{}, errors.New("worktrees are not quarantined")
}

// worktreeExecutor removes a worktree with Git itself (never --force), keeping
// the branch. Git refuses dirty or untracked worktrees independently.
type worktreeExecutor struct{ repository string }

func (x worktreeExecutor) Delete(ctx context.Context, r ManagedResource) (Measurement, error) {
	m := Measurement{Method: "git worktree remove without --force, then verified absence and host free space"}
	gitDir, _ := r.Identity["git_dir"].(string)
	value, err := gitRead(ctx, r.Location, "rev-parse", "--path-format=absolute", "--git-dir")
	if err != nil || strings.TrimSpace(value) != gitDir || gitDir == "" {
		return m, errors.New("worktree identity changed since approval")
	}
	InvalidateMeasurements()
	before := measureTree(ctx, r.Location, 50_000_000, 10*time.Minute)
	m.BeforeBytes = before.allocated
	m.HostFreeBefore = freeBytes(filepath.Dir(r.Location))
	command := exec.CommandContext(ctx, "git", "-C", x.repository, "worktree", "remove", r.Location)
	if output, err := command.CombinedOutput(); err != nil {
		return m, errors.New("git worktree remove refused: " + strings.TrimSpace(string(output)))
	}
	if _, err = os.Lstat(r.Location); !errors.Is(err, fs.ErrNotExist) {
		return m, errors.New("worktree directory still present")
	}
	m.VerifiedAbsent = true
	m.HostFreeAfter = freeBytes(filepath.Dir(r.Location))
	if before.complete {
		m.ReclaimedBytes = &before.allocated
	}
	return m, nil
}
