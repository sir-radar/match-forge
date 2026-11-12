package storage

import (
	"context"
	"encoding/json"
	"os/exec"
	"strings"
)

func ScanWorktrees(ctx context.Context, repository string) ([]Resource, error) {
	// Newline porcelain: "-z" needs Git 2.36, older supported Git rejects it.
	output, err := gitRead(ctx, repository, "worktree", "list", "--porcelain")
	if err != nil {
		return nil, err
	}
	result := []Resource{}
	for _, field := range strings.Split(output, "\n") {
		if !strings.HasPrefix(field, "worktree ") {
			continue
		}
		path := strings.TrimPrefix(field, "worktree ")
		result = append(result, inspectWorktree(ctx, path))
	}
	return result, nil
}
func gitRead(ctx context.Context, path string, args ...string) (string, error) {
	output, err := exec.CommandContext(ctx, "git", append([]string{"-C", path}, args...)...).Output()
	return string(output), err
}
func inspectWorktree(ctx context.Context, path string) Resource {
	r := Resource{ID: Identity("git", path), Backend: "git", Location: path, Kind: "worktree", Subsystem: "worktrees", Protected: true, State: "PROTECTED", Blockers: []string{"active process ownership is unverified", "unique ignored evidence and branch dependencies require review", "explicit owner approval required"}}
	observations := map[string]string{}
	queries := map[string][]string{"status": {"status", "--porcelain", "--untracked-files=normal"}, "ignored": {"ls-files", "--others", "--ignored", "--exclude-standard", "--directory"}, "unmerged_commits": {"rev-list", "--count", "origin/main..HEAD"}, "head": {"rev-parse", "HEAD"}}
	for key, args := range queries {
		value, err := gitRead(ctx, path, args...)
		if err != nil {
			r.Blockers = append(r.Blockers, "cannot verify "+key)
			continue
		}
		observations[key] = value
	}
	r.Details, _ = json.Marshal(observations)
	return r
}
