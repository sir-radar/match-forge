package storage

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"os"
	"slices"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// MaxBatch bounds one approval so progress, cancellation and retries stay simple.
const MaxBatch = 50

var (
	ErrStalePlan    = errors.New("the plan changed since preview; preview again")
	ErrConfirmation = errors.New("typed confirmation does not match")
	ErrBusy         = errors.New("another operation is open for one of these resources")
)

type Measurement struct {
	Method         string `json:"method"`
	BeforeBytes    int64  `json:"before_bytes"`
	ReclaimedBytes *int64 `json:"reclaimed_bytes"`
	VerifiedAbsent bool   `json:"verified_absent"`
	ClusterBefore  *int64 `json:"cluster_before_bytes,omitempty"`
	ClusterAfter   *int64 `json:"cluster_after_bytes,omitempty"`
	HostFreeBefore *int64 `json:"host_free_before_bytes,omitempty"`
	HostFreeAfter  *int64 `json:"host_free_after_bytes,omitempty"`
	Note           string `json:"note,omitempty"`
}

// Manager assesses and operates on managed resources. Every decision is made on
// the server from live observations; nothing a client sends can widen it.
type Manager struct {
	Pool       *pgxpool.Pool
	Repository string
	Policy     *Policy
	Logger     *slog.Logger
	Now        func() time.Time
	run        sync.Mutex
	// lastAutomatic is guarded by run.
	lastAutomatic time.Time
}

type Inventory struct {
	ObservedAt time.Time         `json:"observed_at"`
	Authority  Authority         `json:"authority"`
	Resources  []ManagedResource `json:"resources"`
	Summary    Summary           `json:"summary"`
	Policy     PolicyStatus      `json:"policy"`
	Warnings   []string          `json:"warnings"`
}

type PolicyStatus struct {
	Configured       bool              `json:"configured"`
	ManagedRoots     []ManagedRoot     `json:"managed_roots"`
	ProtectedPaths   []string          `json:"protected_paths"`
	AutomaticCleanup []AutomaticPolicy `json:"automatic_cleanup"`
	QuarantineDays   float64           `json:"quarantine_days"`
}

type Summary struct {
	HostTotalBytes         *int64           `json:"host_total_bytes"`
	HostFreeBytes          *int64           `json:"host_free_bytes"`
	PostgresBytes          int64            `json:"postgres_bytes"`
	AuthoritativeBytes     int64            `json:"authoritative_bytes"`
	OtherDatabaseBytes     int64            `json:"other_database_bytes"`
	DatabaseCount          int              `json:"database_count"`
	WorktreeBytes          int64            `json:"worktree_bytes"`
	ManagedFileBytes       int64            `json:"managed_file_bytes"`
	QuarantinedBytes       int64            `json:"quarantined_bytes"`
	ByClassification       map[string]int64 `json:"bytes_by_classification"`
	CountByClassification  map[string]int   `json:"count_by_classification"`
	EstimatedReclaimable   int64            `json:"estimated_reclaimable_bytes"`
	VerifiedReclaimedBytes int64            `json:"verified_reclaimed_bytes"`
	Note                   string           `json:"note"`
}

func (m *Manager) now() time.Time {
	if m.Now != nil {
		return m.Now()
	}
	return time.Now().UTC()
}

func (m *Manager) quarantineRetention() time.Duration {
	if m.Policy != nil && m.Policy.QuarantineSeconds > 0 {
		return time.Duration(m.Policy.QuarantineSeconds) * time.Second
	}
	return 7 * 24 * time.Hour
}

func (m *Manager) limits() (time.Duration, int) {
	if m.Policy != nil {
		return m.Policy.EvidenceMaxAge(), m.Policy.MaxEntries
	}
	return DefaultEvidenceMaxAge, 2_000_000
}

func (m *Manager) Inventory(ctx context.Context) (Inventory, error) {
	now := m.now()
	inv := Inventory{ObservedAt: now, Resources: []ManagedResource{}, Warnings: []string{}, Policy: m.policyStatus()}
	inv.Authority = VerifyAuthority(ctx, m.Pool)
	if !inv.Authority.Verified {
		inv.Warnings = append(inv.Warnings, "Authoritative database identity is unverified: "+inv.Authority.Problem)
	}
	if err := m.addDatabases(ctx, &inv, now); err != nil {
		return inv, err
	}
	if err := m.addFiles(ctx, &inv, now); err != nil {
		return inv, err
	}
	for i := range inv.Resources {
		if q := inv.Resources[i].Quarantine; q != nil {
			q.RetainUntil = q.QuarantinedAt.Add(m.quarantineRetention())
		}
	}
	var err error
	inv.Summary, err = m.summarize(ctx, inv.Resources)
	return inv, err
}

func (m *Manager) policyStatus() PolicyStatus {
	if m.Policy == nil {
		return PolicyStatus{ManagedRoots: []ManagedRoot{}, ProtectedPaths: []string{}, AutomaticCleanup: []AutomaticPolicy{}, QuarantineDays: m.quarantineRetention().Hours() / 24}
	}
	return PolicyStatus{Configured: true, ManagedRoots: m.Policy.ManagedRoots, ProtectedPaths: nonNil(m.Policy.ProtectedPaths),
		AutomaticCleanup: m.Policy.AutomaticCleanup, QuarantineDays: m.quarantineRetention().Hours() / 24}
}

func (m *Manager) addDatabases(ctx context.Context, inv *Inventory, now time.Time) error {
	if inv.Authority.SystemIdentifier == "" {
		return nil
	}
	maxAge, _ := m.limits()
	databases, err := ListDatabases(ctx, m.Pool, inv.Authority, now, maxAge)
	inv.Resources = append(inv.Resources, databases...)
	return err
}

func (m *Manager) addFiles(ctx context.Context, inv *Inventory, now time.Time) error {
	protections, err := Protections(ctx, m.Pool)
	if err != nil {
		return err
	}
	cwds, err := processDirectories(ctx)
	if err != nil {
		// Without process evidence nothing on disk can be shown as unused.
		inv.Warnings = append(inv.Warnings, "Process working directories unavailable; filesystem and worktree actions are disabled.")
		cwds = []string{"/"}
	}
	m.addWorktrees(ctx, inv, protections, cwds, now)
	if m.Policy == nil {
		inv.Warnings = append(inv.Warnings, "No storage policy: only databases and worktrees are managed.")
		return nil
	}
	quarantined, err := openQuarantines(ctx, m.Pool, "filesystem")
	if err != nil {
		return err
	}
	inv.Resources = append(inv.Resources, ListFilesystem(ctx, *m.Policy, protections, quarantined, cwds, now)...)
	return nil
}

func (m *Manager) addWorktrees(ctx context.Context, inv *Inventory, protections map[string][]string, cwds []string, now time.Time) {
	if m.Repository == "" {
		return
	}
	_, maxEntries := m.limits()
	worktrees, err := ListWorktrees(ctx, m.Repository, protections, cwds, maxEntries, now)
	if err != nil {
		inv.Warnings = append(inv.Warnings, "Worktree inventory incomplete: "+err.Error())
		return
	}
	inv.Resources = append(inv.Resources, worktrees...)
}

func (m *Manager) summarize(ctx context.Context, resources []ManagedResource) (Summary, error) {
	s := Summary{ByClassification: map[string]int64{}, CountByClassification: map[string]int{},
		Note: "Databases are measured inside the PostgreSQL volume and are not added to host directory totals. Worktrees and managed roots may overlap; the reclaimable estimate counts nested locations once."}
	if c, err := DiskCapacity(valueOrDefault(m.Repository, "/")); err == nil {
		s.HostTotalBytes, s.HostFreeBytes = &c.TotalBytes, &c.FreeBytes
	}
	var eligible []ManagedResource
	for _, r := range resources {
		s.add(r)
		if r.Allows(ActionDelete) || r.Allows(ActionPurge) {
			eligible = append(eligible, r)
		}
	}
	s.EstimatedReclaimable = uniqueBytes(eligible)
	err := m.Pool.QueryRow(ctx, `SELECT coalesce(sum(reclaimed_bytes),0)::bigint FROM football.storage_operations
 WHERE state='SUCCEEDED' AND action IN ('DELETE','PURGE')`).Scan(&s.VerifiedReclaimedBytes)
	return s, err
}

func (s *Summary) add(r ManagedResource) {
	bytes := valueOr(r.AllocatedBytes)
	s.ByClassification[string(r.Classification)] += bytes
	s.CountByClassification[string(r.Classification)]++
	switch {
	case r.Quarantine != nil:
		s.QuarantinedBytes += bytes
	case r.Backend == "postgres":
		s.addDatabase(r, bytes)
	case r.Backend == "git":
		s.WorktreeBytes += bytes
	default:
		s.ManagedFileBytes += bytes
	}
}

func (s *Summary) addDatabase(r ManagedResource, bytes int64) {
	s.PostgresBytes += bytes
	s.DatabaseCount++
	if r.Role == "AUTHORITATIVE_OPERATING_DATABASE" {
		s.AuthoritativeBytes = bytes
		return
	}
	s.OtherDatabaseBytes += bytes
}

func valueOrDefault(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

// uniqueBytes sums allocations once per identity and skips locations nested in
// another selected location, so overlapping resources are not double-counted.
func uniqueBytes(resources []ManagedResource) int64 {
	seen := map[string]bool{}
	var paths []string
	var total int64
	sorted := slices.Clone(resources)
	sort.Slice(sorted, func(i, j int) bool { return len(sorted[i].Location) < len(sorted[j].Location) })
	for _, r := range sorted {
		if seen[r.IdentityKey] || r.AllocatedBytes == nil {
			continue
		}
		seen[r.IdentityKey] = true
		if r.Backend != "postgres" {
			if slices.ContainsFunc(paths, func(p string) bool { return within(p, r.Location) }) {
				continue
			}
			paths = append(paths, r.Location)
		}
		total += *r.AllocatedBytes
	}
	return total
}

type PlanItem struct {
	ResourceID     string         `json:"resource_id"`
	Name           string         `json:"name"`
	Backend        string         `json:"backend"`
	Location       string         `json:"location"`
	IdentityKey    string         `json:"identity_key"`
	Classification Classification `json:"classification"`
	EvidenceSHA256 string         `json:"evidence_sha256"`
	ExpectedBytes  *int64         `json:"expected_bytes"`
	Reasons        []string       `json:"reasons"`
	Remediation    []string       `json:"remediation"`
	Overlaps       string         `json:"overlaps,omitempty"`
}

type Plan struct {
	Action               string     `json:"action"`
	Items                []PlanItem `json:"items"`
	Blocked              []PlanItem `json:"blocked"`
	PlanSHA256           string     `json:"plan_sha256"`
	ExpectedUniqueBytes  int64      `json:"expected_unique_bytes"`
	TypedConfirmation    string     `json:"typed_confirmation"`
	Irreversible         bool       `json:"irreversible"`
	Consequences         []string   `json:"consequences"`
	AuthoritativeChecked bool       `json:"authoritative_verified"`
}

func validAction(action string) bool {
	return slices.Contains([]string{ActionDelete, ActionQuarantine, ActionRestore, ActionPurge}, action)
}

// Preview computes the exact plan. Blocked resources never prevent independent
// eligible resources from being included.
func (m *Manager) Preview(ctx context.Context, action string, ids []string) (Plan, map[string]ManagedResource, error) {
	plan := Plan{Action: action, Items: []PlanItem{}, Blocked: []PlanItem{}, Consequences: []string{}}
	if !validAction(action) {
		return plan, nil, errors.New("unsupported action")
	}
	if len(ids) == 0 || len(ids) > MaxBatch {
		return plan, nil, fmt.Errorf("select between 1 and %d resources", MaxBatch)
	}
	inv, err := m.Inventory(ctx)
	if err != nil {
		return plan, nil, err
	}
	plan.AuthoritativeChecked = inv.Authority.Verified
	selected := plan.partition(inv.Resources, ids)
	m.describe(&plan, selected)
	plan.PlanSHA256 = planDigest(plan)
	return plan, selected, nil
}

// partition splits the request into executable items and individually blocked ones.
func (plan *Plan) partition(resources []ManagedResource, ids []string) map[string]ManagedResource {
	byID := map[string]ManagedResource{}
	for _, r := range resources {
		byID[r.ResourceID] = r
	}
	selected := map[string]ManagedResource{}
	for _, id := range dedupe(ids) {
		r, ok := byID[id]
		if !ok {
			plan.Blocked = append(plan.Blocked, PlanItem{ResourceID: id, Reasons: []string{"resource no longer exists or is not managed"}, Remediation: []string{}})
			continue
		}
		item := planItem(r, plan.Action)
		if !r.Allows(plan.Action) {
			item.Reasons = append(slices.Clone(item.Reasons), plan.Action+" is not available for this resource")
			plan.Blocked = append(plan.Blocked, item)
			continue
		}
		selected[id] = r
		plan.Items = append(plan.Items, item)
	}
	sort.Slice(plan.Items, func(i, j int) bool { return plan.Items[i].ResourceID < plan.Items[j].ResourceID })
	return selected
}

func (m *Manager) describe(plan *Plan, selected map[string]ManagedResource) {
	switch plan.Action {
	case ActionDelete, ActionPurge:
		allowed := make([]ManagedResource, 0, len(selected))
		for _, r := range selected {
			allowed = append(allowed, r)
		}
		plan.ExpectedUniqueBytes = uniqueBytes(allowed)
		markOverlaps(plan.Items)
		plan.Irreversible = true
		plan.TypedConfirmation = fmt.Sprintf("DELETE %d", len(plan.Items))
		plan.Consequences = append(plan.Consequences, "Permanently removes the listed resources. There is no undo.")
		if slices.ContainsFunc(allowed, func(r ManagedResource) bool { return r.Backend == "postgres" }) {
			plan.Consequences = append(plan.Consequences, "Dropped databases can only be recreated from an independent backup; their comparison evidence remains recorded.")
		}
	case ActionQuarantine:
		plan.Consequences = append(plan.Consequences, fmt.Sprintf("Isolates the resources without freeing space. They stay restorable for %.0f days before purge is suggested.", m.quarantineRetention().Hours()/24))
	default:
		plan.Consequences = append(plan.Consequences, "Returns quarantined resources to their original names or paths.")
	}
}

func planItem(r ManagedResource, action string) PlanItem {
	item := PlanItem{ResourceID: r.ResourceID, Name: r.Name, Backend: r.Backend, Location: r.Location, IdentityKey: r.IdentityKey,
		Classification: r.Classification, EvidenceSHA256: r.EvidenceSHA256, Reasons: r.Reasons, Remediation: r.Remediation}
	if action == ActionDelete || action == ActionPurge {
		item.ExpectedBytes = r.AllocatedBytes
	}
	return item
}

func markOverlaps(items []PlanItem) {
	for i := range items {
		for j := range items {
			if i != j && items[i].Backend != "postgres" && items[j].Backend != "postgres" && within(items[j].Location, items[i].Location) {
				items[i].Overlaps = items[j].Location
			}
		}
	}
}

func planDigest(p Plan) string {
	type bound struct{ ID, Key, Evidence, Class string }
	items := make([]bound, 0, len(p.Items))
	for _, i := range p.Items {
		items = append(items, bound{i.ResourceID, i.IdentityKey, i.EvidenceSHA256, string(i.Classification)})
	}
	return Fingerprint("matchforge-storage-plan-v1", p.Action, items)
}

func dedupe(ids []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, id := range ids {
		if !seen[id] {
			seen[id] = true
			out = append(out, id)
		}
	}
	return out
}

type SubmitRequest struct {
	Action       string   `json:"action"`
	ResourceIDs  []string `json:"resource_ids"`
	PlanSHA256   string   `json:"plan_sha256"`
	Confirmation string   `json:"confirmation"`
	Confirmed    bool     `json:"confirmed"`
}

type Batch struct {
	BatchID    string `json:"batch_id"`
	Operations int    `json:"operations"`
}

// Submit re-runs the preview, requires the exact same plan and confirmation,
// records durable operations, then executes them in the background.
func (m *Manager) Submit(ctx context.Context, req SubmitRequest, actor string) (Batch, error) {
	plan, selected, err := m.Preview(ctx, req.Action, req.ResourceIDs)
	if err != nil {
		return Batch{}, err
	}
	if len(plan.Blocked) > 0 || len(plan.Items) == 0 || plan.PlanSHA256 != req.PlanSHA256 {
		return Batch{}, ErrStalePlan
	}
	if !req.Confirmed || (plan.TypedConfirmation != "" && req.Confirmation != plan.TypedConfirmation) {
		return Batch{}, ErrConfirmation
	}
	batch := Batch{BatchID: newUUID(), Operations: len(plan.Items)}
	if err = m.record(ctx, batch, plan, selected, confirmationRecord(req, plan), actor); err != nil {
		return batch, err
	}
	go m.Execute(context.WithoutCancel(ctx), batch.BatchID)
	return batch, nil
}

func (m *Manager) record(ctx context.Context, batch Batch, plan Plan, selected map[string]ManagedResource, confirmation, actor string) error {
	tx, err := m.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	for _, item := range plan.Items {
		r := selected[item.ResourceID]
		payload, _ := json.Marshal(boundIdentity(r))
		_, err = tx.Exec(ctx, `INSERT INTO football.storage_operations(operation_id,batch_id,action,resource_id,backend,location,
 identity_key,identity,plan_sha256,approved_by,confirmation,expected_bytes)
 VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`, newUUID(), batch.BatchID, plan.Action, r.ResourceID, r.Backend, r.Location,
			r.IdentityKey, payload, plan.PlanSHA256, actor, confirmation, item.ExpectedBytes)
		if err != nil && strings.Contains(err.Error(), "storage_operations_one_open_per_identity") {
			return ErrBusy
		}
		if err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

// boundIdentity is the identity an operation is fenced to at execution time.
func boundIdentity(r ManagedResource) map[string]any {
	identity := map[string]any{"evidence_sha256": r.EvidenceSHA256}
	for k, v := range r.Identity {
		identity[k] = v
	}
	if r.Quarantine != nil {
		identity["quarantine_operation_id"] = r.Quarantine.OperationID
	}
	return identity
}

func confirmationRecord(req SubmitRequest, plan Plan) string {
	if plan.TypedConfirmation != "" {
		return "typed:" + req.Confirmation
	}
	return "confirmed"
}

type operationRow struct {
	ID, Action, ResourceID, Backend, Location, IdentityKey string
	Identity                                               map[string]any
}

// Execute runs the batch's pending operations one at a time.
func (m *Manager) Execute(ctx context.Context, batchID string) {
	m.run.Lock()
	defer m.run.Unlock()
	rows, err := m.Pool.Query(ctx, `SELECT operation_id::text,action,resource_id,backend,location,identity_key,identity
 FROM football.storage_operations WHERE batch_id=$1 AND state='PENDING' ORDER BY created_at,operation_id`, batchID)
	if err != nil {
		m.logError("storage batch unavailable", err)
		return
	}
	ops, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (operationRow, error) {
		var o operationRow
		err := row.Scan(&o.ID, &o.Action, &o.ResourceID, &o.Backend, &o.Location, &o.IdentityKey, &o.Identity)
		return o, err
	})
	if err != nil {
		m.logError("storage batch unreadable", err)
		return
	}
	for _, op := range ops {
		m.executeOne(ctx, op)
	}
}

func (m *Manager) executeOne(ctx context.Context, op operationRow) {
	// Claim: the trigger re-checks protection on the RUNNING transition.
	tag, err := m.Pool.Exec(ctx, `UPDATE football.storage_operations SET state='RUNNING',started_at=clock_timestamp()
 WHERE operation_id=$1 AND state='PENDING'`, op.ID)
	if err != nil {
		m.finish(ctx, op.ID, "BLOCKED", nil, nil, "protection check rejected execution: "+err.Error())
		return
	}
	if tag.RowsAffected() != 1 {
		return // cancelled or claimed elsewhere
	}
	r, reason := m.revalidate(ctx, op)
	if reason != "" {
		m.finish(ctx, op.ID, "BLOCKED", nil, nil, reason)
		return
	}
	measurement, quarantine, err := m.dispatch(ctx, op, r)
	if err != nil {
		m.finish(ctx, op.ID, "FAILED", &measurement, nil, err.Error())
		return
	}
	m.finish(ctx, op.ID, "SUCCEEDED", &measurement, quarantine, "")
}

// revalidate re-assesses the exact resource immediately before execution.
func (m *Manager) revalidate(ctx context.Context, op operationRow) (ManagedResource, string) {
	inv, err := m.Inventory(ctx)
	if err != nil {
		return ManagedResource{}, "revalidation failed: " + err.Error()
	}
	if op.Backend == "postgres" && !inv.Authority.Verified {
		return ManagedResource{}, "authoritative database identity is unverified; database operations are disabled"
	}
	for _, r := range inv.Resources {
		if r.ResourceID != op.ResourceID {
			continue
		}
		if r.IdentityKey != op.IdentityKey {
			return r, "resource identity changed since approval"
		}
		if evidence, _ := op.Identity["evidence_sha256"].(string); evidence != r.EvidenceSHA256 {
			return r, "evidence changed since approval; preview again"
		}
		if !r.Allows(op.Action) {
			return r, "no longer eligible: " + strings.Join(r.Reasons, "; ")
		}
		return r, ""
	}
	return ManagedResource{}, "resource no longer exists"
}

type executor interface {
	Delete(context.Context, ManagedResource) (Measurement, error)
	Quarantine(context.Context, ManagedResource, string) (Measurement, string, error)
	Restore(context.Context, ManagedResource) (Measurement, error)
}

func (m *Manager) executorFor(backend string) (executor, error) {
	switch backend {
	case "postgres":
		return databaseExecutor{pool: m.Pool}, nil
	case "filesystem":
		if m.Policy == nil {
			return nil, errors.New("storage policy not configured")
		}
		return fileExecutor{policy: *m.Policy}, nil
	case "git":
		return worktreeExecutor{repository: m.Repository}, nil
	}
	return nil, errors.New("unsupported backend")
}

func (m *Manager) dispatch(ctx context.Context, op operationRow, r ManagedResource) (Measurement, *string, error) {
	x, err := m.executorFor(op.Backend)
	if err != nil {
		return Measurement{}, nil, err
	}
	switch op.Action {
	case ActionDelete, ActionPurge:
		measurement, err := x.Delete(ctx, r)
		return measurement, nil, err
	case ActionQuarantine:
		measurement, target, err := x.Quarantine(ctx, r, op.ID)
		return measurement, &target, err
	case ActionRestore:
		measurement, err := x.Restore(ctx, r)
		return measurement, nil, err
	}
	return Measurement{}, nil, fmt.Errorf("%s is not supported for %s", op.Action, op.Backend)
}

func (m *Manager) finish(ctx context.Context, id, state string, measurement *Measurement, quarantine *string, message string) {
	payload := []byte("{}")
	var reclaimed *int64
	if measurement != nil {
		payload, _ = json.Marshal(measurement)
		if state == "SUCCEEDED" {
			reclaimed = measurement.ReclaimedBytes
		}
	}
	var errorText *string
	if message != "" {
		errorText = &message
	}
	_, err := m.Pool.Exec(ctx, `UPDATE football.storage_operations SET state=$2,finished_at=clock_timestamp(),
 measurement=$3,reclaimed_bytes=$4,quarantine_location=$5,error=$6 WHERE operation_id=$1 AND state IN ('PENDING','RUNNING')`,
		id, state, payload, reclaimed, quarantine, errorText)
	if err != nil {
		m.logError("storage operation outcome not recorded", err)
	}
	InvalidateMeasurements()
}

// Cancel stops pending operations of a batch; a running one finishes or fails.
func (m *Manager) Cancel(ctx context.Context, batchID string) (int64, error) {
	tag, err := m.Pool.Exec(ctx, `UPDATE football.storage_operations SET state='CANCELLED',finished_at=clock_timestamp(),
 error='cancelled by administrator' WHERE batch_id=$1 AND state='PENDING'`, batchID)
	return tag.RowsAffected(), err
}

// Recover resolves operations interrupted by a restart. A RUNNING deletion is
// only marked SUCCEEDED when the exact resource is verifiably absent.
func (m *Manager) Recover(ctx context.Context) error {
	if _, err := m.Pool.Exec(ctx, `UPDATE football.storage_operations SET state='CANCELLED',finished_at=clock_timestamp(),
 error='API restarted before execution; preview again' WHERE state='PENDING'`); err != nil {
		return err
	}
	rows, err := m.Pool.Query(ctx, `SELECT operation_id::text,action,resource_id,backend,location,identity_key,identity
 FROM football.storage_operations WHERE state='RUNNING'`)
	if err != nil {
		return err
	}
	ops, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (operationRow, error) {
		var o operationRow
		err := row.Scan(&o.ID, &o.Action, &o.ResourceID, &o.Backend, &o.Location, &o.IdentityKey, &o.Identity)
		return o, err
	})
	if err != nil {
		return err
	}
	for _, op := range ops {
		absent := m.absent(ctx, op)
		if (op.Action == ActionDelete || op.Action == ActionPurge) && absent {
			m.finish(ctx, op.ID, "SUCCEEDED", &Measurement{Method: "interrupted; absence verified on restart", VerifiedAbsent: true,
				Note: "reclaimed bytes were not measured because the operation was interrupted"}, nil, "")
			continue
		}
		m.finish(ctx, op.ID, "FAILED", nil, nil, "interrupted by restart; inspect the resource and preview again")
	}
	return nil
}

func (m *Manager) absent(ctx context.Context, op operationRow) bool {
	switch op.Backend {
	case "postgres":
		oid, err := identityOID(op.Identity)
		if err != nil {
			return false
		}
		var exists bool
		if m.Pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM pg_database WHERE oid=$1::oid)`, oid).Scan(&exists) != nil {
			return false
		}
		return !exists
	default:
		path := op.Location
		if q, ok := op.Identity["quarantine_location"].(string); ok && q != "" {
			path = q
		}
		_, err := os.Lstat(path)
		return errors.Is(err, fs.ErrNotExist)
	}
}

// openQuarantines returns resources quarantined and not yet restored or purged.
func openQuarantines(ctx context.Context, pool *pgxpool.Pool, backend string) (map[string]QuarantineInfo, error) {
	rows, err := pool.Query(ctx, `SELECT q.identity_key,q.operation_id::text,q.location,coalesce(q.quarantine_location,''),q.finished_at
 FROM football.storage_operations q WHERE q.backend=$1 AND q.action='QUARANTINE' AND q.state='SUCCEEDED'
 AND NOT EXISTS(SELECT 1 FROM football.storage_operations later WHERE later.identity_key=q.identity_key
  AND later.state='SUCCEEDED' AND later.action IN ('RESTORE','PURGE','DELETE') AND later.created_at>q.finished_at)`, backend)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := map[string]QuarantineInfo{}
	for rows.Next() {
		var key string
		var q QuarantineInfo
		if err = rows.Scan(&key, &q.OperationID, &q.OriginalLocation, &q.QuarantineLocation, &q.QuarantinedAt); err != nil {
			return nil, err
		}
		q.RetainUntil = q.QuarantinedAt.Add(7 * 24 * time.Hour)
		result[key] = q
	}
	return result, rows.Err()
}

type OperationRecord struct {
	OperationID        string          `json:"operation_id"`
	BatchID            string          `json:"batch_id"`
	Action             string          `json:"action"`
	ResourceID         string          `json:"resource_id"`
	Backend            string          `json:"backend"`
	Location           string          `json:"location"`
	State              string          `json:"state"`
	ApprovedBy         string          `json:"approved_by"`
	ExpectedBytes      *int64          `json:"expected_bytes"`
	ReclaimedBytes     *int64          `json:"reclaimed_bytes"`
	Measurement        json.RawMessage `json:"measurement"`
	QuarantineLocation *string         `json:"quarantine_location"`
	Error              *string         `json:"error"`
	CreatedAt          time.Time       `json:"created_at"`
	StartedAt          *time.Time      `json:"started_at"`
	FinishedAt         *time.Time      `json:"finished_at"`
}

func (m *Manager) Operations(ctx context.Context, limit int) ([]OperationRecord, error) {
	rows, err := m.Pool.Query(ctx, `SELECT operation_id::text,batch_id::text,action,resource_id,backend,location,state,approved_by,
 expected_bytes,reclaimed_bytes,measurement,quarantine_location,error,created_at,started_at,finished_at
 FROM football.storage_operations ORDER BY created_at DESC, operation_id LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (OperationRecord, error) {
		var o OperationRecord
		err := row.Scan(&o.OperationID, &o.BatchID, &o.Action, &o.ResourceID, &o.Backend, &o.Location, &o.State, &o.ApprovedBy,
			&o.ExpectedBytes, &o.ReclaimedBytes, &o.Measurement, &o.QuarantineLocation, &o.Error, &o.CreatedAt, &o.StartedAt, &o.FinishedAt)
		return o, err
	})
}

// Protect records an owner protection for a resource. Protection can be added
// through Storage Management but never removed there.
func (m *Manager) Protect(ctx context.Context, resourceID, reason, actor string) error {
	r, err := m.find(ctx, resourceID)
	if err != nil {
		return err
	}
	identity, _ := json.Marshal(r.Identity)
	_, err = m.Pool.Exec(ctx, `INSERT INTO football.storage_protections(backend,identity_key,identity,role,reason,recorded_by)
 VALUES($1,$2,$3,'OWNER_PROTECTED',$4,$5) ON CONFLICT(identity_key,role) DO NOTHING`, r.Backend, r.IdentityKey, identity, reason, actor)
	return err
}

// Dispose records an owner disposition bound to the resource's current evidence.
func (m *Manager) Dispose(ctx context.Context, resourceID, evidence, disposition, rationale, actor string) error {
	r, err := m.find(ctx, resourceID)
	if err != nil {
		return err
	}
	if r.EvidenceSHA256 == "" || r.EvidenceSHA256 != evidence {
		return ErrStalePlan
	}
	_, err = m.Pool.Exec(ctx, `INSERT INTO football.storage_dispositions(identity_key,evidence_sha256,disposition,rationale,recorded_by)
 VALUES($1,$2,$3,$4,$5)`, r.IdentityKey, evidence, disposition, rationale, actor)
	return err
}

func (m *Manager) find(ctx context.Context, resourceID string) (ManagedResource, error) {
	inv, err := m.Inventory(ctx)
	if err != nil {
		return ManagedResource{}, err
	}
	for _, r := range inv.Resources {
		if r.ResourceID == resourceID {
			return r, nil
		}
	}
	return ManagedResource{}, errors.New("resource not found")
}

func (m *Manager) logError(message string, err error) {
	if m.Logger != nil {
		m.Logger.Error(message, "error", err)
	}
}

func newUUID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[:4], b[4:6], b[6:8], b[8:10], b[10:])
}
