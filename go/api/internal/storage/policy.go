// Package storage owns operational resource accounting and non-destructive lifecycle reviews.
package storage

import (
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
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
	return validateRoots(p.Roots)
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
