package storage

import (
	"context"
	"path/filepath"
	"strings"
	"time"
)

// RunAutomaticCleanup executes only the owner-approved, narrowly scoped policies:
// purging expired quarantine and deleting aged children of declared disposable
// filesystem roots. Databases and worktrees are never selected. Every candidate
// goes through the same preview, revalidation, protection trigger and
// measurement as a manual action.
func (m *Manager) RunAutomaticCleanup(ctx context.Context) (int, error) {
	if m.Policy == nil || len(m.Policy.AutomaticCleanup) == 0 || !m.automaticDue() {
		return 0, nil
	}
	inv, err := m.Inventory(ctx)
	if err != nil {
		return 0, err
	}
	submitted := 0
	for _, rule := range m.Policy.AutomaticCleanup {
		submitted += m.applyRule(ctx, inv, rule)
	}
	return submitted, nil
}

// applyRule previews twice so only items eligible now are bound into the plan.
func (m *Manager) applyRule(ctx context.Context, inv Inventory, rule AutomaticPolicy) int {
	ids, action := automaticCandidates(inv.Resources, rule, inv.ObservedAt)
	if len(ids) == 0 {
		return 0
	}
	first, _, err := m.Preview(ctx, action, ids)
	if err != nil || len(first.Items) == 0 {
		return 0
	}
	approved := make([]string, 0, len(first.Items))
	for _, item := range first.Items {
		approved = append(approved, item.ResourceID)
	}
	plan, _, err := m.Preview(ctx, action, approved)
	if err != nil || len(plan.Blocked) > 0 {
		return 0
	}
	actor := "policy:" + rule.ApprovalRecord + ":" + rule.ApprovedBy
	_, err = m.Submit(ctx, SubmitRequest{Action: action, ResourceIDs: approved, PlanSHA256: plan.PlanSHA256,
		Confirmation: plan.TypedConfirmation, Confirmed: true}, actor)
	if err != nil {
		return 0
	}
	return len(approved)
}

// automaticCandidates selects at most MaxPerRun filesystem resources in the rule's
// root. Age only applies after the owner declared the root disposable.
func automaticCandidates(resources []ManagedResource, rule AutomaticPolicy, now time.Time) ([]string, string) {
	action := ActionDelete
	if rule.Action == "PURGE_EXPIRED_QUARANTINE" {
		action = ActionPurge
	}
	minAge := time.Duration(rule.MinAgeSeconds) * time.Second
	var ids []string
	for _, r := range resources {
		if len(ids) >= rule.MaxPerRun || r.Backend != "filesystem" || !r.Allows(action) || !inRoot(r, rule.Root) {
			continue
		}
		if automaticDue(r, action, minAge, now) {
			ids = append(ids, r.ResourceID)
		}
	}
	return ids, action
}

func inRoot(r ManagedResource, root string) bool {
	location := r.Location
	if r.Quarantine != nil {
		location = r.Quarantine.OriginalLocation
	}
	return filepath.Dir(location) == root && !strings.Contains(r.Name, string(filepath.Separator))
}

func automaticDue(r ManagedResource, action string, minAge time.Duration, now time.Time) bool {
	if action == ActionPurge {
		return r.Quarantine != nil && !now.Before(r.Quarantine.RetainUntil) && now.Sub(r.Quarantine.QuarantinedAt) >= minAge
	}
	modified, ok := r.Details["modified_at"].(time.Time)
	return r.Quarantine == nil && ok && now.Sub(modified) >= minAge
}

// automaticDue rate-limits unattended cleanup to the policy's review interval.
func (m *Manager) automaticDue() bool {
	m.run.Lock()
	defer m.run.Unlock()
	now := m.now()
	if !m.lastAutomatic.IsZero() && now.Sub(m.lastAutomatic) < time.Duration(m.Policy.IntervalSeconds)*time.Second {
		return false
	}
	m.lastAutomatic = now
	return true
}
