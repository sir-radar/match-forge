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
	ClassTestDatabase   = "TEST_DATABASE"
	ClassWorktree       = "WORKTREE"
	ClassDisposablePath = "DISPOSABLE_PATH"
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
	// Paths are regenerable build outputs, dependency caches and temporary
	// directories inside the repository, each deleted as a whole.
	Paths          []DisposablePath `json:"paths,omitempty"`
	ApprovedBy     string           `json:"approved_by"`
	ApprovalRecord string           `json:"approval_record"`
}

// DisposablePath declares one regenerable directory. Consumers are process names
// (for example cargo, go, node) whose running instance counts as use. A cache
// that is expensive to rebuild can require more idle time than five hours.
type DisposablePath struct {
	Path           string   `json:"path"`
	Kind           string   `json:"kind"`
	Consumers      []string `json:"consumers"`
	MinIdleSeconds int      `json:"min_idle_seconds,omitempty"`
}

var pathKinds = []string{"BUILD_OUTPUT", "DEPENDENCY_CACHE", "TEMPORARY"}

func (d DisposablePath) validate(protected []string) error {
	if !cleanAbsolute(d.Path) || !slices.Contains(pathKinds, d.Kind) {
		return errors.New("invalid disposable path")
	}
	if d.Kind != "TEMPORARY" && len(d.Consumers) == 0 {
		return errors.New("build outputs and caches must name their consumer processes")
	}
	if d.MinIdleSeconds != 0 && time.Duration(d.MinIdleSeconds)*time.Second < MinimumInactivity {
		return errors.New("a disposable path cannot be idle for less than five hours")
	}
	if slices.ContainsFunc(protected, func(p string) bool { return p == d.Path || within(p, d.Path) || within(d.Path, p) }) {
		return errors.New("a disposable path overlaps a protected path")
	}
	return nil
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
	if !l.TestDatabases && l.Worktrees == nil && len(l.Paths) == 0 {
		return errors.New("lifecycle cleanup must enable at least one resource class")
	}
	if err := validatePaths(l.Paths, protected); err != nil {
		return err
	}
	if l.Worktrees != nil {
		return l.Worktrees.validate(protected)
	}
	return nil
}

func validatePaths(paths []DisposablePath, protected []string) error {
	for i, d := range paths {
		if err := d.validate(protected); err != nil {
			return err
		}
		if slices.ContainsFunc(paths[:i], func(o DisposablePath) bool {
			return o.Path == d.Path || within(o.Path, d.Path) || within(d.Path, o.Path)
		}) {
			return errors.New("disposable paths must not overlap")
		}
	}
	return nil
}

// idleFor is the inactivity a resource needs: five hours, or more for a path
// with a retention exemption.
func (l LifecyclePolicy) idleFor(rec LifecycleRecord) time.Duration {
	for _, d := range l.Paths {
		if rec.Class == ClassDisposablePath && d.Path == rec.Location && time.Duration(d.MinIdleSeconds)*time.Second > l.inactivity() {
			return time.Duration(d.MinIdleSeconds) * time.Second
		}
	}
	return l.inactivity()
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
