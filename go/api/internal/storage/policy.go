// Package storage owns operational resource accounting and non-destructive lifecycle reviews.
package storage

import (
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"slices"
	"time"
)

type RootPolicy struct {
	Path          string `json:"path"`
	Subsystem     string `json:"subsystem"`
	WarningBytes  int64  `json:"warning_bytes"`
	CriticalBytes int64  `json:"critical_bytes"`
}
type Policy struct {
	DatabaseWarningBytes  int64        `json:"database_warning_bytes"`
	DatabaseCriticalBytes int64        `json:"database_critical_bytes"`
	Roots                 []RootPolicy `json:"roots"`
	ReserveBytes          int64        `json:"reserve_bytes"`
	WarningFreeBytes      int64        `json:"warning_free_bytes"`
	MaxEntries            int          `json:"max_entries"`
	ScanSeconds           int          `json:"scan_seconds"`
	IntervalSeconds       int          `json:"interval_seconds"`
	BackupIntervalSeconds int          `json:"backup_interval_seconds"`
	QuarantineSeconds     int          `json:"quarantine_seconds"`
	// Resource management (optional). Only direct children of managed roots are
	// ever offered for filesystem actions; protected paths always win.
	ManagedRoots          []ManagedRoot     `json:"managed_roots,omitempty"`
	ProtectedPaths        []string          `json:"protected_paths,omitempty"`
	EvidenceMaxAgeSeconds int               `json:"evidence_max_age_seconds,omitempty"`
	AutomaticCleanup      []AutomaticPolicy `json:"automatic_cleanup,omitempty"`
	// LifecycleCleanup enables the owner-approved five-hour cleanup of completed
	// disposable test databases and merged worktrees. Absent means disabled.
	LifecycleCleanup *LifecyclePolicy `json:"lifecycle_cleanup,omitempty"`
	// Maintenance enables the read-only daily, weekly and monthly reports.
	Maintenance *MaintenancePolicy `json:"maintenance,omitempty"`
}

// ManagedRoot declares a MatchForge-owned directory whose direct children are
// managed resources. Class "disposable" means the owner reviewed the root as
// regenerable output (caches, build output); "review" requires a per-resource
// owner disposition before any child becomes eligible.
type ManagedRoot struct {
	Path        string `json:"path"`
	Class       string `json:"class"`
	Description string `json:"description"`
}

// AutomaticPolicy is a narrowly scoped, owner-approved unattended action.
// Only "PURGE_EXPIRED_QUARANTINE" and "DELETE_DISPOSABLE" on filesystem
// disposable roots are supported; databases and worktrees are never automatic.
type AutomaticPolicy struct {
	Action         string `json:"action"`
	Root           string `json:"root"`
	MinAgeSeconds  int    `json:"min_age_seconds"`
	ApprovedBy     string `json:"approved_by"`
	ApprovalRecord string `json:"approval_record"`
	MaxPerRun      int    `json:"max_per_run"`
}

func LoadPolicy(path string) (Policy, error) {
	var p Policy
	f, err := os.Open(path)
	if err != nil {
		return p, err
	}
	defer f.Close()
	d := json.NewDecoder(io.LimitReader(f, 1<<20))
	d.DisallowUnknownFields()
	if err = d.Decode(&p); err != nil {
		return p, err
	}
	if d.Decode(new(any)) != io.EOF {
		return p, errors.New("policy must contain one JSON object")
	}
	return p, p.Validate()
}
func (p Policy) Validate() error {
	if err := p.validateLimits(); err != nil {
		return err
	}
	if err := validateRoots(p.Roots); err != nil {
		return err
	}
	return p.validateManagement()
}

func (p Policy) validateManagement() error {
	for i, root := range p.ManagedRoots {
		if err := p.validateManagedRoot(root, p.ManagedRoots[:i]); err != nil {
			return err
		}
	}
	if slices.ContainsFunc(p.ProtectedPaths, func(path string) bool { return !cleanAbsolute(path) }) {
		return errors.New("invalid protected path")
	}
	if p.EvidenceMaxAgeSeconds < 0 {
		return errors.New("invalid evidence age")
	}
	for _, a := range p.AutomaticCleanup {
		if err := p.validateAutomatic(a); err != nil {
			return err
		}
	}
	if p.Maintenance != nil {
		if err := p.Maintenance.validate(); err != nil {
			return err
		}
	}
	if p.LifecycleCleanup != nil {
		return p.LifecycleCleanup.validate(p.ProtectedPaths)
	}
	return nil
}

func (p Policy) validateManagedRoot(root ManagedRoot, earlier []ManagedRoot) error {
	if !cleanAbsolute(root.Path) || (root.Class != "disposable" && root.Class != "review") {
		return errors.New("invalid managed resource root")
	}
	if slices.ContainsFunc(earlier, func(other ManagedRoot) bool {
		return within(root.Path, other.Path) || within(other.Path, root.Path)
	}) {
		return errors.New("managed resource roots must not overlap")
	}
	if slices.ContainsFunc(p.ProtectedPaths, func(protected string) bool { return within(protected, root.Path) }) {
		return errors.New("a managed resource root lies inside a protected path")
	}
	return nil
}

func (p Policy) validateAutomatic(a AutomaticPolicy) error {
	if a.Action != "PURGE_EXPIRED_QUARANTINE" && a.Action != "DELETE_DISPOSABLE" {
		return errors.New("unsupported automatic cleanup action")
	}
	if !a.bounded() {
		return errors.New("automatic cleanup needs an approval record, a bounded batch and at least one day of age")
	}
	if !slices.ContainsFunc(p.ManagedRoots, func(root ManagedRoot) bool { return root.Path == a.Root && root.Class == "disposable" }) {
		return errors.New("automatic cleanup is limited to declared disposable roots")
	}
	return nil
}

func (a AutomaticPolicy) bounded() bool {
	return a.ApprovedBy != "" && a.ApprovalRecord != "" && a.MaxPerRun > 0 && a.MaxPerRun <= 100 && a.MinAgeSeconds >= 86400
}

func cleanAbsolute(path string) bool {
	return filepath.IsAbs(path) && filepath.Clean(path) == path && path != "/"
}

// EvidenceMaxAge returns the configured comparison lifetime.
func (p Policy) EvidenceMaxAge() time.Duration {
	if p.EvidenceMaxAgeSeconds > 0 {
		return time.Duration(p.EvidenceMaxAgeSeconds) * time.Second
	}
	return DefaultEvidenceMaxAge
}
func (p Policy) validateLimits() error {
	if p.ReserveBytes <= 0 || p.WarningFreeBytes < p.ReserveBytes {
		return errors.New("invalid recovery capacity reserve")
	}
	if p.MaxEntries <= 0 || p.ScanSeconds <= 0 || p.ScanSeconds > 3600 {
		return errors.New("invalid scan bounds")
	}
	if p.IntervalSeconds < 3600 || p.BackupIntervalSeconds < 86400 || p.QuarantineSeconds < 86400 {
		return errors.New("invalid lifecycle intervals")
	}
	return p.validateBudgets()
}
func (p Policy) validateDurationBounds() error {
	const maxSQLSeconds = 1<<31 - 1
	if p.IntervalSeconds > maxSQLSeconds || p.BackupIntervalSeconds > maxSQLSeconds {
		return errors.New("schedule interval exceeds PostgreSQL integer bounds")
	}
	if p.QuarantineSeconds > int(time.Duration(1<<63-1)/time.Second) {
		return errors.New("quarantine grace exceeds representable duration")
	}
	return nil
}
func validateRoots(roots []RootPolicy) error {
	if len(roots) == 0 {
		return errors.New("explicit managed roots required")
	}
	for i, r := range roots {
		if err := r.validate(); err != nil {
			return err
		}
		for _, other := range roots[:i] {
			if within(r.Path, other.Path) || within(other.Path, r.Path) {
				return errors.New("managed accounting roots must not overlap")
			}
		}
	}
	return nil
}
func (r RootPolicy) validate() error {
	if !filepath.IsAbs(r.Path) || filepath.Clean(r.Path) != r.Path || r.Path == "/" {
		return errors.New("invalid managed root")
	}
	if r.Subsystem == "" || r.WarningBytes <= 0 || r.CriticalBytes < r.WarningBytes {
		return errors.New("invalid subsystem budget")
	}
	return nil
}
func within(root, path string) bool {
	r, e := filepath.Rel(root, path)
	return e == nil && filepath.IsLocal(r)
}

type Reservation struct {
	RequestedBytes int64
	FreeBytes      int64
	ReservedBytes  int64
	ReserveBytes   int64
}

func (r Reservation) Admit() error {
	if r.RequestedBytes <= 0 || r.FreeBytes < 0 || r.ReservedBytes < 0 || r.ReserveBytes <= 0 {
		return errors.New("capacity estimates must be positive and verifiable")
	}
	if r.ReserveBytes > r.FreeBytes {
		return errors.New("storage admission denied: recovery reserve exceeds free capacity")
	}
	available := r.FreeBytes - r.ReserveBytes
	if r.ReservedBytes > available || r.RequestedBytes > available-r.ReservedBytes {
		return errors.New("storage admission denied: preserve verified recovery headroom")
	}
	return nil
}

type Resource struct {
	ID               string          `json:"resource_id"`
	Backend          string          `json:"backend"`
	Location         string          `json:"location"`
	Kind             string          `json:"kind"`
	Subsystem        string          `json:"subsystem"`
	Owner            string          `json:"owner"`
	LogicalBytes     int64           `json:"logical_bytes"`
	AllocatedBytes   *int64          `json:"allocated_bytes"`
	SHA256           string          `json:"sha256"`
	Protected        bool            `json:"protected"`
	References       int             `json:"references"`
	LeaseUntil       *time.Time      `json:"lease_until"`
	RetainUntil      *time.Time      `json:"retain_until"`
	RecoveryVerified bool            `json:"recovery_verified"`
	Reconstructable  bool            `json:"reconstructable"`
	Complete         bool            `json:"complete"`
	State            string          `json:"state"`
	Blockers         []string        `json:"blockers"`
	Details          json.RawMessage `json:"details"`
}

// Eligibility never equates byte duplication, age, or an expired lease with permission.
func (r Resource) Eligibility(now time.Time) []string {
	b := []string{}
	if r.Protected {
		b = append(b, "protected historical, operating or recovery resource")
	}
	if r.Owner == "" {
		b = append(b, "unknown owner")
	}
	if !r.Complete {
		b = append(b, "inventory incomplete or stale")
	}
	if r.References > 0 {
		b = append(b, "active consumers")
	}
	if r.LeaseUntil != nil && r.LeaseUntil.After(now) {
		b = append(b, "active ownership lease")
	}
	if !retentionSatisfied(r.RetainUntil, now) {
		b = append(b, "retention not satisfied")
	}
	if !r.RecoveryVerified || !r.Reconstructable {
		b = append(b, "verified recovery and reconstruction required")
	}
	return b
}

func retentionSatisfied(deadline *time.Time, now time.Time) bool {
	return deadline != nil && !deadline.After(now)
}

func (p Policy) validateBudgets() error {
	if p.DatabaseWarningBytes <= 0 || p.DatabaseCriticalBytes < p.DatabaseWarningBytes {
		return errors.New("invalid PostgreSQL capacity budget")
	}
	return p.validateDurationBounds()
}
