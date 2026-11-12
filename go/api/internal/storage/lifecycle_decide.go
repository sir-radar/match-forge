package storage

import (
	"slices"
	"time"
)

// Lifecycle states. ACTIVE: in use or not yet complete. WAITING: complete, inside
// the inactivity window. ELIGIBLE: every condition held at the last check.
// BLOCKED: complete but a safety condition prevents deletion. DELETING: a
// storage operation was submitted. DELETED and ABSENT are terminal.
const (
	LifecycleActive   = "ACTIVE"
	LifecycleWaiting  = "WAITING"
	LifecycleEligible = "ELIGIBLE"
	LifecycleBlocked  = "BLOCKED"
	LifecycleDeleting = "DELETING"
	LifecycleDeleted  = "DELETED"
	LifecycleAbsent   = "ABSENT"
)

// LifecycleRecord is the durable state of one tracked resource.
type LifecycleRecord struct {
	IdentityKey    string         `json:"identity_key"`
	Class          string         `json:"resource_class"`
	Backend        string         `json:"backend"`
	Location       string         `json:"location"`
	OwnerKind      string         `json:"owner_kind"`
	Identity       map[string]any `json:"identity"`
	OwnerRef       map[string]any `json:"owner_ref"`
	CreatedAt      time.Time      `json:"created_at"`
	LastActivityAt time.Time      `json:"last_activity_at"`
	Fingerprint    string         `json:"-"`
	CompletedAt    *time.Time     `json:"completed_at"`
	Completion     *string        `json:"completion"`
	State          string         `json:"state"`
	EligibleAt     *time.Time     `json:"eligible_at"`
	Blockers       []string       `json:"blockers"`
	CheckedAt      *time.Time     `json:"checked_at"`
	OperationID    *string        `json:"operation_id"`
	ReclaimedBytes *int64         `json:"reclaimed_bytes"`
}

// LifecycleObservation is what one check verified about a resource right now.
type LifecycleObservation struct {
	Present bool
	// Fingerprint changes whenever the resource is used: database activity
	// counters, or a worktree's HEAD, index and status.
	Fingerprint string
	// InUse lists live signals (connections, processes, Git locks). Each one
	// counts as activity and prevents deletion.
	InUse []string
	// Blockers are conditions that must be resolved before deletion.
	Blockers []string
	// Completion is OWNER_EXITED or PR_MERGED once the lifecycle is conclusively
	// complete, and empty otherwise.
	Completion string
	// Deletable reports that the resource inventory offers DELETE right now.
	Deletable bool
}

// LifecycleDecision is the next durable state plus the audit events it implies.
type LifecycleDecision struct {
	State          string
	LastActivityAt time.Time
	Fingerprint    string
	CompletedAt    *time.Time
	Completion     *string
	EligibleAt     *time.Time
	Blockers       []string
	Events         []string
}

// DecideLifecycle applies the five-hour rule. It is pure so the full window can be
// tested with a deterministic clock. Eligibility needs, at the same check: a
// conclusively completed lifecycle, no live use, no blockers, the inactivity
// window elapsed since the later of last activity and completion, and an
// inventory that offers deletion. Any new activity restarts the window.
func DecideLifecycle(rec LifecycleRecord, obs LifecycleObservation, now time.Time, inactivity time.Duration) LifecycleDecision {
	d := LifecycleDecision{LastActivityAt: rec.LastActivityAt, Fingerprint: rec.Fingerprint, CompletedAt: rec.CompletedAt,
		Completion: rec.Completion, Blockers: []string{}}
	if !obs.Present {
		d.State = LifecycleAbsent
		d.Events = []string{"ABSENT"}
		return d
	}
	if obs.Fingerprint != rec.Fingerprint || len(obs.InUse) > 0 {
		d.LastActivityAt, d.Fingerprint = now, obs.Fingerprint
		d.Events = append(d.Events, "ACTIVITY")
	}
	d.applyCompletion(obs.Completion, now)
	d.Blockers = append(append(d.Blockers, obs.InUse...), obs.Blockers...)
	d.State = d.state(obs, now, inactivity)
	if d.State != rec.State {
		d.Events = append(d.Events, stateEvent[d.State])
	}
	return d
}

var stateEvent = map[string]string{LifecycleActive: "ACTIVITY", LifecycleWaiting: "WAITING", LifecycleEligible: "ELIGIBLE", LifecycleBlocked: "BLOCKED"}

// applyCompletion records completion once; it is withdrawn when the evidence no
// longer holds (for example new commits on a merged branch).
func (d *LifecycleDecision) applyCompletion(completion string, now time.Time) {
	switch {
	case completion == "":
		d.CompletedAt, d.Completion = nil, nil
	case d.CompletedAt == nil || d.Completion == nil || *d.Completion != completion:
		at, kind := now, completion
		d.CompletedAt, d.Completion = &at, &kind
		d.Events = append(d.Events, "COMPLETED")
	}
}

func (d *LifecycleDecision) state(obs LifecycleObservation, now time.Time, inactivity time.Duration) string {
	if d.CompletedAt == nil {
		return LifecycleActive
	}
	start := d.LastActivityAt
	if d.CompletedAt.After(start) {
		start = *d.CompletedAt
	}
	eligibleAt := start.Add(inactivity)
	d.EligibleAt = &eligibleAt
	switch {
	case len(obs.InUse) > 0:
		return LifecycleActive
	case len(obs.Blockers) > 0:
		return LifecycleBlocked
	case now.Before(eligibleAt):
		return LifecycleWaiting
	case !obs.Deletable:
		d.Blockers = append(d.Blockers, "the resource inventory does not offer deletion")
		return LifecycleBlocked
	}
	return LifecycleEligible
}

// Changed reports whether the decision differs from the stored record.
func (d LifecycleDecision) Changed(rec LifecycleRecord) bool {
	return d.State != rec.State || !d.LastActivityAt.Equal(rec.LastActivityAt) || d.Fingerprint != rec.Fingerprint ||
		!sameTime(d.CompletedAt, rec.CompletedAt) || !sameTime(d.EligibleAt, rec.EligibleAt) || !slices.Equal(d.Blockers, rec.Blockers)
}

func sameTime(a, b *time.Time) bool {
	if a == nil || b == nil {
		return a == b
	}
	return a.Equal(*b)
}
