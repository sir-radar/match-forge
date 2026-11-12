package storage

import (
	"context"
	"errors"
	"path/filepath"
	"slices"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// lifecycleLockKey serializes cleanup workers across processes on the cluster.
const lifecycleLockKey = 0x6d66_7374_6c63 // "mfstlc"

// LifecycleRun summarizes one five-hour policy check.
type LifecycleRun struct {
	CheckedAt      time.Time `json:"checked_at"`
	Tracked        int       `json:"tracked"`
	Eligible       int       `json:"eligible"`
	Submitted      int       `json:"submitted"`
	Deleted        int       `json:"deleted"`
	Failed         int       `json:"failed"`
	ReclaimedBytes int64     `json:"reclaimed_bytes"`
	Skipped        string    `json:"skipped,omitempty"`
}

// RunLifecycleCleanup applies the owner-approved five-hour policy once: register
// new candidates, observe every tracked resource, persist decisions with audit
// events, then delete up to MaxPerRun eligible resources through the normal
// preview, protection trigger, revalidation and measurement path. A cluster-wide
// advisory lock keeps concurrent workers from acting at the same time.
func (m *Manager) RunLifecycleCleanup(ctx context.Context) (LifecycleRun, error) {
	run := LifecycleRun{CheckedAt: m.now()}
	if m.Policy == nil || m.Policy.LifecycleCleanup == nil {
		run.Skipped = "lifecycle cleanup is not enabled by the storage policy"
		return run, nil
	}
	var ready bool
	if err := m.Pool.QueryRow(ctx, `SELECT to_regclass('football.storage_lifecycle_resources') IS NOT NULL`).Scan(&ready); err != nil || !ready {
		run.Skipped = "storage lifecycle migration has not been deployed"
		return run, err
	}
	if !m.lifecycleDue(run.CheckedAt) {
		run.Skipped = "not due"
		return run, nil
	}
	conn, err := m.Pool.Acquire(ctx)
	if err != nil {
		return run, err
	}
	defer conn.Release()
	var locked bool
	if err = conn.QueryRow(ctx, `SELECT pg_try_advisory_lock($1)`, lifecycleLockKey).Scan(&locked); err != nil || !locked {
		run.Skipped = "another cleanup worker holds the lifecycle lock"
		return run, err
	}
	defer conn.Exec(context.WithoutCancel(ctx), `SELECT pg_advisory_unlock($1)`, lifecycleLockKey)
	return run, m.lifecycleOnce(ctx, &run)
}

func (m *Manager) lifecycleDue(now time.Time) bool {
	m.run.Lock()
	defer m.run.Unlock()
	if !m.lastLifecycle.IsZero() && now.Sub(m.lastLifecycle) < m.Policy.LifecycleCleanup.checkInterval() {
		return false
	}
	m.lastLifecycle = now
	return true
}

// lifecycleView is one consistent observation of everything the check needs.
type lifecycleView struct {
	inv     Inventory
	rows    map[string]databaseRow
	byKey   map[string]ManagedResource
	records map[string]LifecycleRecord
	cwds    []string
	cwdErr  error
}

func (m *Manager) lifecycleOnce(ctx context.Context, run *LifecycleRun) error {
	policy := *m.Policy.LifecycleCleanup
	view, err := m.lifecycleView(ctx, policy, run.CheckedAt)
	if err != nil {
		return err
	}
	eligible, err := m.decideAll(ctx, view, policy, run)
	if err != nil {
		return err
	}
	run.Eligible = len(eligible)
	for _, rec := range eligible[:min(len(eligible), policy.MaxPerRun)] {
		m.deleteEligible(ctx, rec, policy, run, run.CheckedAt)
	}
	return nil
}

// lifecycleView reads the inventory, registers new candidates and loads every
// open lifecycle record.
func (m *Manager) lifecycleView(ctx context.Context, policy LifecyclePolicy, now time.Time) (lifecycleView, error) {
	v := lifecycleView{rows: map[string]databaseRow{}, byKey: map[string]ManagedResource{}}
	var err error
	if v.inv, err = m.Inventory(ctx); err != nil {
		return v, err
	}
	if !v.inv.Authority.Verified {
		return v, errors.New("authoritative database identity is unverified; lifecycle cleanup is disabled")
	}
	databases, err := readDatabases(ctx, m.Pool)
	if err != nil {
		return v, err
	}
	for _, d := range databases {
		v.rows[PostgresIdentityKey(v.inv.Authority.SystemIdentifier, d.oid)] = d
	}
	for _, r := range v.inv.Resources {
		v.byKey[r.IdentityKey] = r
	}
	if err = m.discover(ctx, v.inv, v.rows, policy, now); err != nil {
		return v, err
	}
	v.cwds, v.cwdErr = processDirectories(ctx)
	v.records, err = lifecycleRecords(ctx, m.Pool, `state NOT IN ('DELETED','ABSENT')`)
	return v, err
}

// decideAll settles running deletions and persists a fresh decision for every
// other record, returning those that are eligible now.
func (m *Manager) decideAll(ctx context.Context, v lifecycleView, policy LifecyclePolicy, run *LifecycleRun) ([]LifecycleRecord, error) {
	now := run.CheckedAt
	var eligible []LifecycleRecord
	for _, rec := range sortedRecords(v.records) {
		run.Tracked++
		if rec.State == LifecycleDeleting {
			m.settle(ctx, rec, run, now)
			continue
		}
		d := DecideLifecycle(rec, m.observe(ctx, rec, v, policy), now, policy.inactivity())
		if d.Changed(rec) || rec.CheckedAt == nil {
			if err := saveDecision(ctx, m.Pool, rec, d, now); err != nil {
				return nil, err
			}
		}
		if d.State == LifecycleEligible {
			eligible = append(eligible, rec)
		}
	}
	return eligible, nil
}

func sortedRecords(records map[string]LifecycleRecord) []LifecycleRecord {
	result := make([]LifecycleRecord, 0, len(records))
	for _, r := range records {
		result = append(result, r)
	}
	slices.SortFunc(result, func(a, b LifecycleRecord) int { return strings.Compare(a.IdentityKey, b.IdentityKey) })
	return result
}

func (m *Manager) observe(ctx context.Context, rec LifecycleRecord, v lifecycleView, policy LifecyclePolicy) LifecycleObservation {
	switch {
	case rec.Class == ClassTestDatabase && policy.TestDatabases:
		return m.observeDatabase(ctx, rec, v.byKey, v.rows)
	case rec.Class == ClassWorktree && policy.Worktrees != nil:
		if v.cwdErr != nil {
			return LifecycleObservation{Present: true, Fingerprint: rec.Fingerprint, InUse: []string{"process working directories unavailable"}}
		}
		return m.observeWorktree(ctx, rec, v.byKey, v.cwds, *policy.Worktrees)
	}
	// A class the policy no longer enables stays tracked but cannot progress.
	return LifecycleObservation{Present: true, Fingerprint: rec.Fingerprint, Blockers: []string{"resource class is not enabled by the storage policy"}}
}

// deleteEligible claims one resource, rebuilds the plan from a fresh inventory,
// submits it with the policy actor and executes it synchronously.
func (m *Manager) deleteEligible(ctx context.Context, rec LifecycleRecord, policy LifecyclePolicy, run *LifecycleRun, now time.Time) {
	token, ok, err := claimLifecycle(ctx, m.Pool, rec.IdentityKey, now, 15*time.Minute)
	if err != nil || !ok {
		return
	}
	id := Identity(rec.Backend, rec.IdentityKey)
	plan, _, err := m.Preview(ctx, ActionDelete, []string{id})
	if err != nil || len(plan.Items) != 1 || len(plan.Blocked) > 0 {
		m.reject(ctx, rec, token, plan, err)
		return
	}
	batch, err := m.submit(ctx, SubmitRequest{Action: ActionDelete, ResourceIDs: []string{id}, PlanSHA256: plan.PlanSHA256,
		Confirmation: plan.TypedConfirmation, Confirmed: true}, policy.actor())
	if err != nil {
		m.reject(ctx, rec, token, plan, err)
		return
	}
	operation, err := batchOperation(ctx, m.Pool, batch.BatchID)
	if err == nil {
		err = markDeleting(ctx, m.Pool, rec.IdentityKey, token, operation)
	}
	if err != nil {
		m.logError("lifecycle deletion not recorded", err)
		return
	}
	run.Submitted++
	m.Execute(ctx, batch.BatchID)
	rec.OperationID, rec.State = &operation, LifecycleDeleting
	m.settle(ctx, rec, run, m.now())
}

func (m *Manager) reject(ctx context.Context, rec LifecycleRecord, token string, plan Plan, err error) {
	detail := map[string]any{"blocked": plan.Blocked}
	if err != nil {
		detail["error"] = err.Error()
	}
	releaseClaim(ctx, m.Pool, rec.IdentityKey, token)
	if e := lifecycleEvent(ctx, m.Pool, rec.IdentityKey, "REJECTED", detail); e != nil {
		m.logError("lifecycle rejection not recorded", e)
	}
}

func (m *Manager) settle(ctx context.Context, rec LifecycleRecord, run *LifecycleRun, now time.Time) {
	state, reclaimed, err := settleDeletion(ctx, m.Pool, rec, now)
	switch {
	case err != nil:
		m.logError("lifecycle deletion outcome not recorded", err)
	case state == "" || state == "PENDING" || state == "RUNNING":
	case state == "SUCCEEDED":
		run.Deleted++
		run.ReclaimedBytes += valueOr(reclaimed)
	default:
		run.Failed++
	}
}

func batchOperation(ctx context.Context, pool *pgxpool.Pool, batch string) (string, error) {
	var id string
	err := pool.QueryRow(ctx, `SELECT operation_id::text FROM football.storage_operations WHERE batch_id=$1`, batch).Scan(&id)
	return id, err
}

// discover registers worktrees under the policy roots and databases created by a
// registered test run. Nothing is registered by name: worktrees by Git
// directory, child databases by the exact ownership marker of a known run.
func (m *Manager) discover(ctx context.Context, inv Inventory, rows map[string]databaseRow, policy LifecyclePolicy, now time.Time) error {
	if policy.Worktrees != nil {
		for _, r := range inv.Resources {
			if r.Backend != "git" || r.Role == "PRIMARY_CHECKOUT" || !underRoot(r.Location, policy.Worktrees.Roots) || r.Classification == Protected && r.Role != "" {
				continue
			}
			rec := LifecycleRecord{IdentityKey: r.IdentityKey, Class: ClassWorktree, Backend: "git", Location: r.Location,
				OwnerKind: "WORKTREE_DISCOVERY", Identity: map[string]any{"git_dir": r.Identity["git_dir"], "path": r.Location},
				OwnerRef: map[string]any{"branch": r.Details["branch"]}}
			if err := registerLifecycle(ctx, m.Pool, rec, now); err != nil {
				return err
			}
		}
	}
	if !policy.TestDatabases {
		return nil
	}
	return m.discoverChildren(ctx, inv.Authority.SystemIdentifier, rows, now)
}

func (m *Manager) discoverChildren(ctx context.Context, system string, rows map[string]databaseRow, now time.Time) error {
	runs, err := lifecycleRecords(ctx, m.Pool, `owner_kind='INTEGRATION_HARNESS'`)
	if err != nil {
		return err
	}
	owners := map[string]LifecycleRecord{}
	for _, r := range runs {
		if marker, _ := r.OwnerRef["owned_marker"].(string); marker != "" {
			owners[marker] = r
		}
	}
	for key, d := range rows {
		parent, ok := owners[d.comment]
		if !ok || parent.Identity["system_identifier"] != system {
			continue
		}
		rec := LifecycleRecord{IdentityKey: key, Class: ClassTestDatabase, Backend: "postgres", Location: system + "/" + d.name,
			OwnerKind: "HARNESS_CHILD", OwnerRef: parent.OwnerRef,
			Identity: map[string]any{"system_identifier": system, "oid": d.oid, "database": d.name}}
		if err = registerLifecycle(ctx, m.Pool, rec, now); err != nil {
			return err
		}
	}
	return nil
}

func underRoot(path string, roots []string) bool {
	for _, root := range roots {
		if filepath.Dir(path) == root {
			return true
		}
	}
	return false
}
