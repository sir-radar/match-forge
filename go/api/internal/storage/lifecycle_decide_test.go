package storage

import (
	"context"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"testing"
	"time"
)

var lifecycleT0 = time.Date(2026, 11, 13, 9, 0, 0, 0, time.UTC)

// step applies one check and stores the decision the way the runner does.
func step(rec *LifecycleRecord, obs LifecycleObservation, at time.Time) LifecycleDecision {
	d := DecideLifecycle(*rec, obs, at, MinimumInactivity)
	rec.State, rec.LastActivityAt, rec.Fingerprint = d.State, d.LastActivityAt, d.Fingerprint
	rec.CompletedAt, rec.Completion, rec.EligibleAt, rec.Blockers = d.CompletedAt, d.Completion, d.EligibleAt, d.Blockers
	return d
}

func idle(fingerprint string) LifecycleObservation {
	return LifecycleObservation{Present: true, Fingerprint: fingerprint, Completion: "OWNER_EXITED", Deletable: true}
}

func TestLifecycleFiveHourWindowWithDeterministicClock(t *testing.T) {
	rec := LifecycleRecord{State: LifecycleActive, LastActivityAt: lifecycleT0}
	running := LifecycleObservation{Present: true, Fingerprint: "a", Deletable: true}
	d := step(&rec, running, lifecycleT0)
	expect(t, d.State == LifecycleActive && d.EligibleAt == nil, "incomplete run must stay active: %+v", d)

	completed := lifecycleT0.Add(time.Hour)
	d = step(&rec, idle("a"), completed)
	expect(t, d.State == LifecycleWaiting && d.EligibleAt.Equal(completed.Add(5*time.Hour)), "completion starts the window: %+v", d)
	expect(t, contains(d.Events, "COMPLETED") && contains(d.Events, "WAITING"), "events: %v", d.Events)

	d = step(&rec, idle("a"), completed.Add(5*time.Hour-time.Second))
	expect(t, d.State == LifecycleWaiting, "one second early must still wait: %+v", d)
	d = step(&rec, idle("a"), completed.Add(5*time.Hour))
	expect(t, d.State == LifecycleEligible && contains(d.Events, "ELIGIBLE"), "exactly five hours is eligible: %+v", d)
}

func TestLifecycleActivityResetsTheWindow(t *testing.T) {
	rec := LifecycleRecord{State: LifecycleActive, LastActivityAt: lifecycleT0, Fingerprint: "a"}
	step(&rec, idle("a"), lifecycleT0)
	used := lifecycleT0.Add(3 * time.Hour)
	d := step(&rec, idle("b"), used)
	expect(t, d.State == LifecycleWaiting && d.LastActivityAt.Equal(used) && contains(d.Events, "ACTIVITY"), "changed counters are activity: %+v", d)
	expect(t, d.EligibleAt.Equal(used.Add(5*time.Hour)), "window restarts from the new activity: %v", d.EligibleAt)
	d = step(&rec, idle("b"), lifecycleT0.Add(5*time.Hour))
	expect(t, d.State == LifecycleWaiting, "original deadline no longer applies: %+v", d)
	d = step(&rec, idle("b"), used.Add(5*time.Hour))
	expect(t, d.State == LifecycleEligible, "eligible five hours after the last activity: %+v", d)

	// A live session is activity even when counters do not move, and blocks deletion.
	inUse := idle("b")
	inUse.InUse = []string{"1 active PostgreSQL session(s)"}
	later := used.Add(6 * time.Hour)
	d = step(&rec, inUse, later)
	expect(t, d.State == LifecycleActive && d.LastActivityAt.Equal(later), "a live session must reset and block: %+v", d)
}

func TestLifecycleBlockersAndInventoryGate(t *testing.T) {
	rec := LifecycleRecord{State: LifecycleActive, LastActivityAt: lifecycleT0, Fingerprint: "a"}
	blocked := idle("a")
	blocked.Blockers = []string{"uncommitted or untracked changes"}
	d := step(&rec, blocked, lifecycleT0.Add(10*time.Hour))
	expect(t, d.State == LifecycleBlocked && contains(d.Blockers, "uncommitted or untracked changes"), "blocker must hold: %+v", d)

	rec = LifecycleRecord{State: LifecycleActive, LastActivityAt: lifecycleT0, Fingerprint: "a"}
	step(&rec, idle("a"), lifecycleT0)
	notOffered := idle("a")
	notOffered.Deletable = false
	d = step(&rec, notOffered, lifecycleT0.Add(6*time.Hour))
	expect(t, d.State == LifecycleBlocked, "an inventory without DELETE must not be eligible: %+v", d)
}

func TestLifecycleCompletionIsWithdrawnAndAbsenceIsTerminal(t *testing.T) {
	rec := LifecycleRecord{State: LifecycleActive, LastActivityAt: lifecycleT0, Fingerprint: "a"}
	step(&rec, LifecycleObservation{Present: true, Fingerprint: "a", Completion: "PR_MERGED", Deletable: true}, lifecycleT0)
	// New commits after the merge: no longer merged, back to active.
	d := step(&rec, LifecycleObservation{Present: true, Fingerprint: "b", Deletable: true}, lifecycleT0.Add(6*time.Hour))
	expect(t, d.State == LifecycleActive && d.CompletedAt == nil, "withdrawn completion must reset: %+v", d)
	d = step(&rec, LifecycleObservation{}, lifecycleT0.Add(7*time.Hour))
	expect(t, d.State == LifecycleAbsent, "missing resource is absent: %+v", d)
}

// The decision depends only on the durable record and a fresh observation, so a
// restart in the middle of the window reproduces the same deadline.
func TestLifecycleSurvivesRestart(t *testing.T) {
	rec := LifecycleRecord{State: LifecycleActive, LastActivityAt: lifecycleT0, Fingerprint: "a"}
	step(&rec, idle("a"), lifecycleT0)
	stored := rec
	after := DecideLifecycle(stored, idle("a"), lifecycleT0.Add(5*time.Hour), MinimumInactivity)
	expect(t, after.State == LifecycleEligible && !after.Changed(LifecycleRecord{State: LifecycleEligible, LastActivityAt: rec.LastActivityAt,
		Fingerprint: "a", CompletedAt: rec.CompletedAt, EligibleAt: rec.EligibleAt, Blockers: []string{}}), "restart must not move the deadline: %+v", after)
}

func TestLifecyclePolicyValidation(t *testing.T) {
	valid := LifecyclePolicy{InactivitySeconds: 18000, CheckIntervalSeconds: 900, MaxPerRun: 5, TestDatabases: true,
		ApprovedBy: "owner", ApprovalRecord: "docs/governance/decision-events/x.json"}
	expect(t, valid.validate(nil) == nil, "valid policy rejected")
	for name, mutate := range map[string]func(*LifecyclePolicy){
		"under five hours": func(p *LifecyclePolicy) { p.InactivitySeconds = 17999 },
		"interval short":   func(p *LifecyclePolicy) { p.CheckIntervalSeconds = 899 },
		"interval long":    func(p *LifecyclePolicy) { p.CheckIntervalSeconds = 1801 },
		"no approval":      func(p *LifecyclePolicy) { p.ApprovalRecord = "" },
		"unbounded":        func(p *LifecyclePolicy) { p.MaxPerRun = 21 },
		"no class":         func(p *LifecyclePolicy) { p.TestDatabases = false },
		"relative ref":     func(p *LifecyclePolicy) { p.Worktrees = &WorktreeLifecycle{TargetRef: "main", Roots: []string{"/r/w"}} },
		"relative root": func(p *LifecyclePolicy) {
			p.Worktrees = &WorktreeLifecycle{TargetRef: "refs/remotes/origin/main", Roots: []string{"w"}}
		},
	} {
		p := valid
		mutate(&p)
		expect(t, p.validate(nil) != nil, "%s accepted", name)
	}
	p := valid
	p.Worktrees = &WorktreeLifecycle{TargetRef: "refs/remotes/origin/main", Roots: []string{"/r/w"}}
	expect(t, p.validate([]string{"/r"}) != nil, "worktree root inside a protected path accepted")
	expect(t, baseBranch("refs/remotes/origin/main") == "main" && baseBranch("refs/heads/release/1") == "release/1", "base branch")
}

func TestLocalOwnerProcessVerifiesExactProcess(t *testing.T) {
	host, err := os.Hostname()
	must(t, err)
	ctx := context.Background()
	start, err := exec.Command("ps", "-o", "lstart=", "-p", strconv.Itoa(os.Getpid())).Output()
	must(t, err)
	running, err := LocalOwnerProcess(ctx, map[string]any{"host": host, "pid": float64(os.Getpid()), "process_started": string(start)})
	expect(t, err == nil && running, "own process must be running: %v", err)

	child := exec.Command("true")
	must(t, child.Run())
	running, err = LocalOwnerProcess(ctx, map[string]any{"host": host, "pid": float64(child.Process.Pid), "process_started": string(start)})
	expect(t, err == nil && !running, "finished process must be verified gone: %v", err)

	// Same PID with a different start time is a reused PID: the owner is gone.
	running, err = LocalOwnerProcess(ctx, map[string]any{"host": host, "pid": float64(os.Getpid()), "process_started": "Thu Jan  1 00:00:00 1970"})
	expect(t, err == nil && !running, "reused PID must count as exited: %v", err)

	_, err = LocalOwnerProcess(ctx, map[string]any{"host": host + "-elsewhere", "pid": float64(os.Getpid()), "process_started": string(start)})
	expect(t, err != nil && strings.Contains(err.Error(), "cannot be verified"), "another host must not be verifiable: %v", err)
}

func contains(values []string, want string) bool {
	for _, v := range values {
		if v == want {
			return true
		}
	}
	return false
}
