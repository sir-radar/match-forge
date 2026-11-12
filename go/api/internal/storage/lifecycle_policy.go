package storage

import (
	"errors"
	"slices"
	"time"
)

// MinimumInactivity is the owner's five-hour rule: a completed resource must stay
// unused this long, measured from its last verified activity, before deletion.
const MinimumInactivity = 5 * time.Hour

// Resource classes the five-hour policy may delete. Nothing else is ever selected.
const (
	ClassTestDatabase = "TEST_DATABASE"
	ClassWorktree     = "WORKTREE"
)

// LifecyclePolicy is the owner-approved five-hour cleanup. It covers only
// disposable test databases registered by the integration harness and Git
// worktrees under declared roots whose branch is merged into the target ref.
type LifecyclePolicy struct {
	InactivitySeconds    int                `json:"inactivity_seconds"`
	CheckIntervalSeconds int                `json:"check_interval_seconds"`
	MaxPerRun            int                `json:"max_per_run"`
	TestDatabases        bool               `json:"test_databases"`
	Worktrees            *WorktreeLifecycle `json:"worktrees,omitempty"`
	ApprovedBy           string             `json:"approved_by"`
	ApprovalRecord       string             `json:"approval_record"`
}

// WorktreeLifecycle declares where removable worktrees live and which ref proves
// that their work is merged (for example refs/remotes/origin/main).
type WorktreeLifecycle struct {
	TargetRef string   `json:"target_ref"`
	Roots     []string `json:"roots"`
}

func (l LifecyclePolicy) validate(protected []string) error {
	if l.ApprovedBy == "" || l.ApprovalRecord == "" {
		return errors.New("lifecycle cleanup needs an approval record")
	}
	if err := l.validateBounds(); err != nil {
		return err
	}
	if !l.TestDatabases && l.Worktrees == nil {
		return errors.New("lifecycle cleanup must enable at least one resource class")
	}
	if l.Worktrees != nil {
		return l.Worktrees.validate(protected)
	}
	return nil
}

func (l LifecyclePolicy) validateBounds() error {
	if time.Duration(l.InactivitySeconds)*time.Second < MinimumInactivity {
		return errors.New("lifecycle cleanup needs at least five hours of inactivity")
	}
	if l.CheckIntervalSeconds < 900 || l.CheckIntervalSeconds > 1800 {
		return errors.New("lifecycle cleanup checks every 15 to 30 minutes")
	}
	if l.MaxPerRun < 1 || l.MaxPerRun > 20 {
		return errors.New("lifecycle cleanup deletes between 1 and 20 resources per run")
	}
	return nil
}

func (w WorktreeLifecycle) validate(protected []string) error {
	if len(w.TargetRef) < len("refs/x") || w.TargetRef[:5] != "refs/" {
		return errors.New("worktree cleanup needs a fully qualified target ref")
	}
	if len(w.Roots) == 0 {
		return errors.New("worktree cleanup needs at least one worktree root")
	}
	for _, root := range w.Roots {
		if !cleanAbsolute(root) {
			return errors.New("invalid worktree root")
		}
		if slices.ContainsFunc(protected, func(p string) bool { return within(p, root) || within(root, p) }) {
			return errors.New("a worktree root overlaps a protected path")
		}
	}
	return nil
}

func (l LifecyclePolicy) inactivity() time.Duration {
	return time.Duration(l.InactivitySeconds) * time.Second
}

func (l LifecyclePolicy) checkInterval() time.Duration {
	return time.Duration(l.CheckIntervalSeconds) * time.Second
}

func (l LifecyclePolicy) actor() string {
	return "policy:" + l.ApprovalRecord + ":" + l.ApprovedBy
}
