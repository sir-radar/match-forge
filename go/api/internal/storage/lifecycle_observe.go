package storage

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

// Test-database markers written by tests/integration/database_isolation.py.
const (
	disposableMarkerPrefix = "matchforge-disposable-test-database:v1:"
	ownedMarkerPrefix      = "matchforge-test-owned-database:v1:"
)

// testMarkerMatches requires the database comment to equal the exact marker the
// harness recorded for this run: the run's own database carries the disposable
// marker, databases its tests created carry the owned marker.
func testMarkerMatches(comment string, lc LifecycleRecord) bool {
	key := "marker"
	if lc.OwnerKind == "HARNESS_CHILD" {
		key = "owned_marker"
	}
	want, _ := lc.OwnerRef[key].(string)
	return want != "" && comment == want &&
		(strings.HasPrefix(want, disposableMarkerPrefix) || strings.HasPrefix(want, ownedMarkerPrefix))
}

// OwnerProcess verifies whether the process that owns a test run is still alive.
// It returns running=false only when the exact process (PID plus start time) is
// verifiably gone on this host.
type OwnerProcess func(ctx context.Context, owner map[string]any) (running bool, err error)

// LocalOwnerProcess checks the recorded PID and start time with ps on this host.
func LocalOwnerProcess(ctx context.Context, owner map[string]any) (bool, error) {
	pid, started, err := localOwner(owner)
	if err != nil {
		return true, err
	}
	output, err := exec.CommandContext(ctx, "ps", "-o", "lstart=", "-p", strconv.FormatInt(pid, 10)).Output()
	current := strings.Join(strings.Fields(string(output)), " ")
	var exit *exec.ExitError
	switch {
	case err == nil && current == strings.Join(strings.Fields(started), " "):
		return true, nil
	case err == nil && current != "":
		return false, nil // the PID now belongs to a different process
	case errors.As(err, &exit) && current == "":
		return false, nil
	}
	return true, fmt.Errorf("cannot verify owner process %d: %v", pid, err)
}

// localOwner reads the recorded owner and refuses one on another host.
func localOwner(owner map[string]any) (int64, string, error) {
	host, _ := owner["host"].(string)
	started, _ := owner["process_started"].(string)
	pid, err := ownerPID(owner["pid"])
	if err != nil || host == "" || started == "" {
		return 0, "", errors.New("owner process record is incomplete")
	}
	if local, err := os.Hostname(); err != nil || local != host {
		return 0, "", fmt.Errorf("owner process runs on host %q; completion cannot be verified here", host)
	}
	return pid, started, nil
}

func ownerPID(value any) (int64, error) {
	switch v := value.(type) {
	case float64:
		return int64(v), nil
	case int64:
		return v, nil
	case string:
		return strconv.ParseInt(v, 10, 64)
	}
	return 0, errors.New("owner PID missing")
}

// observeDatabase verifies a tracked test database against the live inventory.
func (m *Manager) observeDatabase(ctx context.Context, rec LifecycleRecord, byKey map[string]ManagedResource, rows map[string]databaseRow) LifecycleObservation {
	r, ok := byKey[rec.IdentityKey]
	d, live := rows[rec.IdentityKey]
	if !ok || !live {
		return LifecycleObservation{}
	}
	obs := LifecycleObservation{Present: true, Fingerprint: d.activity, Deletable: r.Classification != Protected}
	if d.connections > 0 {
		obs.InUse = append(obs.InUse, fmt.Sprintf("%d active PostgreSQL session(s)", d.connections))
	}
	if !testMarkerMatches(d.comment, rec) {
		obs.Blockers = append(obs.Blockers, "database comment does not match the marker recorded at creation")
	}
	if name, _ := rec.Identity["database"].(string); name != d.name {
		obs.Blockers = append(obs.Blockers, "database was renamed since registration")
	}
	if r.Classification == Protected && d.connections == 0 {
		obs.Blockers = append(obs.Blockers, r.Reasons...)
	}
	running, err := m.ownerProcess()(ctx, rec.OwnerRef)
	switch {
	case err != nil:
		obs.Blockers = append(obs.Blockers, err.Error())
	case !running:
		obs.Completion = "OWNER_EXITED"
	}
	return obs
}

func (m *Manager) ownerProcess() OwnerProcess {
	if m.OwnerProcess != nil {
		return m.OwnerProcess
	}
	return LocalOwnerProcess
}

// PRVerifier confirms that a pull request for branch at exactly head was merged
// into base. It is injected so tests do not depend on GitHub.
type PRVerifier func(ctx context.Context, repository, branch, head, base string) (bool, error)

// GitHubPRVerifier asks the GitHub CLI for merged pull requests of the branch.
func GitHubPRVerifier(ctx context.Context, repository, branch, head, base string) (bool, error) {
	command := exec.CommandContext(ctx, "gh", "pr", "list", "--state", "merged", "--head", branch, "--base", base,
		"--json", "headRefOid", "--jq", ".[].headRefOid")
	command.Dir = repository
	output, err := command.Output()
	if err != nil {
		return false, fmt.Errorf("cannot confirm the pull request merge with GitHub: %v", err)
	}
	for _, oid := range strings.Fields(string(output)) {
		if oid == head {
			return true, nil
		}
	}
	return false, nil
}

func (m *Manager) prVerifier() PRVerifier {
	if m.PRVerifier != nil {
		return m.PRVerifier
	}
	return GitHubPRVerifier
}

// observeWorktree verifies a tracked worktree. Activity covers HEAD, branch,
// status (including staged changes) and the reflog; Git lock files and process working
// directories count as live use.
func (m *Manager) observeWorktree(ctx context.Context, rec LifecycleRecord, byKey map[string]ManagedResource, cwds []string, wt WorktreeLifecycle) LifecycleObservation {
	r, ok := byKey[rec.IdentityKey]
	if !ok {
		if _, err := os.Lstat(rec.Location); errors.Is(err, os.ErrNotExist) {
			return LifecycleObservation{}
		}
		return LifecycleObservation{Present: true, Fingerprint: rec.Fingerprint, Blockers: []string{"worktree is no longer listed by Git but its directory remains"}}
	}
	gitDir, _ := r.Identity["git_dir"].(string)
	head, _ := r.Details["head"].(string)
	branch, _ := r.Details["branch"].(string)
	// --no-optional-locks: observing must not refresh the index and look like use.
	status, _ := gitRead(ctx, r.Location, "--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all")
	obs := LifecycleObservation{Present: true, Deletable: r.Allows(ActionDelete),
		Fingerprint: Fingerprint(head, branch, status, fileStamp(filepath.Join(gitDir, "logs", "HEAD")))}
	if recorded, _ := rec.Identity["git_dir"].(string); recorded != gitDir || r.Location != rec.Location {
		obs.Blockers = append(obs.Blockers, "worktree identity differs from the recorded cleanup candidate")
	}
	if inUse(r.Location, cwds) {
		obs.InUse = append(obs.InUse, "a running process has its working directory in this worktree")
	}
	if lock := gitLock(gitDir); lock != "" {
		obs.InUse = append(obs.InUse, "Git operation in progress ("+lock+")")
	}
	if !obs.Deletable {
		obs.Blockers = append(obs.Blockers, r.Reasons...)
	}
	obs.Completion, obs.Blockers = m.mergeCompletion(ctx, r.Location, branch, head, wt, obs.Blockers)
	return obs
}

// mergeCompletion is PR_MERGED only when HEAD is contained in the target ref and
// a merged pull request for this branch has exactly this HEAD.
func (m *Manager) mergeCompletion(ctx context.Context, location, branch, head string, wt WorktreeLifecycle, blockers []string) (string, []string) {
	if branch == "" || head == "" {
		return "", append(blockers, "detached HEAD: no branch or pull request to verify")
	}
	if exec.CommandContext(ctx, "git", "-C", location, "merge-base", "--is-ancestor", head, wt.TargetRef).Run() != nil {
		return "", append(blockers, "HEAD is not merged into "+wt.TargetRef)
	}
	merged, err := m.prVerifier()(ctx, m.Repository, branch, head, baseBranch(wt.TargetRef))
	switch {
	case err != nil:
		return "", append(blockers, err.Error())
	case !merged:
		return "", append(blockers, "no merged pull request for this branch at its current HEAD")
	}
	return "PR_MERGED", blockers
}

func baseBranch(ref string) string {
	parts := strings.Split(strings.TrimPrefix(ref, "refs/"), "/")
	if len(parts) >= 3 && parts[0] == "remotes" {
		return strings.Join(parts[2:], "/")
	}
	return strings.Join(parts[1:], "/")
}

func fileStamp(path string) string {
	info, err := os.Stat(path)
	if err != nil {
		return "absent"
	}
	return fmt.Sprintf("%d:%d", info.Size(), info.ModTime().UnixNano())
}

// gitLock names a lock file that shows a Git command is running in the worktree.
func gitLock(gitDir string) string {
	for _, name := range []string{"index.lock", "HEAD.lock", "MERGE_HEAD", "REBASE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "BISECT_LOG"} {
		if _, err := os.Lstat(filepath.Join(gitDir, name)); err == nil {
			return name
		}
	}
	return ""
}
