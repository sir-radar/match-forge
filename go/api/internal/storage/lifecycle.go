package storage

import "time"

type LifecycleAction struct {
	ResourceID              string     `json:"resource_id"`
	Action                  string     `json:"action"`
	Blockers                []string   `json:"blockers"`
	EarliestDeletionAt      *time.Time `json:"earliest_deletion_at"`
	ExpectedPhysicalSavings *int64     `json:"expected_physical_savings"`
	RecoveryCoverage        string     `json:"recovery_coverage"`
	Rollback                string     `json:"rollback"`
}

// Plans describe quarantine/grace/rollback requirements. They never confer permission.
func PlanLifecycle(resources []Resource, now time.Time, grace time.Duration) []LifecycleAction {
	result := make([]LifecycleAction, 0, len(resources))
	for _, r := range resources {
		blockers := append([]string{}, r.Blockers...)
		blockers = append(blockers, r.Eligibility(now)...)
		action := LifecycleAction{ResourceID: r.ID, Action: "PRESERVE", Blockers: blockers, RecoveryCoverage: "UNVERIFIED", Rollback: "Restore exact original identity/path and verified bytes from an independently verified retained copy; preserve all registrations."}
		if len(blockers) == 0 {
			deadline := now.Add(grace)
			action.Action = "QUARANTINE_REVIEW_REQUIRED"
			action.EarliestDeletionAt = &deadline
			action.RecoveryCoverage = "VERIFIED_RETAINED_COPY"
		}
		result = append(result, action)
	}
	return result
}
