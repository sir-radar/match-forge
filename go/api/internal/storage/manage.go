package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Classification is the resource-specific risk class shown to administrators.
// Only ELIGIBLE resources expose destructive actions, and the server recomputes it
// immediately before execution; a client-supplied class is never trusted.
type Classification string

const (
	Protected      Classification = "PROTECTED"
	ReviewRequired Classification = "REVIEW_REQUIRED"
	Eligible       Classification = "ELIGIBLE"
)

// Recovery labels keep FULL_RECOVERY and RECOVERABLE_ONLY distinct.
const (
	RecoveryFull         = "FULLY_RECOVERABLE"
	RecoveryWithGaps     = "RECOVERABLE_WITH_DECLARED_GAPS"
	RecoveryDisposable   = "INDEPENDENTLY_DISPOSABLE"
	RecoveryPending      = "RECOVERY_VERIFICATION_PENDING"
	RecoveryProtected    = "PROTECTED_OR_UNRECOVERABLE"
	AuthoritativeMessage = "This is MatchForge's authoritative operating database. Deletion is permanently disabled through Storage Management."
)

// Actions an adapter may offer. Destructive ones require owner credential and,
// for DELETE and PURGE, a typed confirmation.
const (
	ActionDelete     = "DELETE"
	ActionQuarantine = "QUARANTINE"
	ActionRestore    = "RESTORE"
	ActionPurge      = "PURGE"
)

type ManagedResource struct {
	ResourceID      string          `json:"resource_id"`
	Backend         string          `json:"backend"`
	Kind            string          `json:"kind"`
	Name            string          `json:"name"`
	Location        string          `json:"location"`
	IdentityKey     string          `json:"identity_key"`
	Identity        map[string]any  `json:"identity"`
	Purpose         string          `json:"purpose"`
	LogicalBytes    *int64          `json:"logical_bytes"`
	AllocatedBytes  *int64          `json:"allocated_bytes"`
	Complete        bool            `json:"measurement_complete"`
	ObservedAt      time.Time       `json:"observed_at"`
	Classification  Classification  `json:"classification"`
	Role            string          `json:"role"`
	Reasons         []string        `json:"reasons"`
	Remediation     []string        `json:"remediation"`
	Actions         []string        `json:"actions"`
	ActiveConsumers int             `json:"active_consumers"`
	Recovery        string          `json:"recovery"`
	Evidence        *Evidence       `json:"evidence"`
	Disposition     *Disposition    `json:"disposition"`
	Quarantine      *QuarantineInfo `json:"quarantine"`
	Details         map[string]any  `json:"details"`
	// EvidenceSHA256 is the digest an owner disposition must bind to (database
	// comparison evidence or a filesystem/worktree fingerprint).
	EvidenceSHA256 string `json:"evidence_sha256"`
	// hard marks a safety blocker that no owner disposition may resolve.
	hard bool
}

type Evidence struct {
	EvidenceID         string          `json:"evidence_id"`
	Finding            string          `json:"finding"`
	UniqueIdentityRows *int64          `json:"unique_identity_rows"`
	Tables             json.RawMessage `json:"tables"`
	SHA256             string          `json:"evidence_sha256"`
	ObservedAt         time.Time       `json:"observed_at"`
	Source             string          `json:"source"`
	Current            bool            `json:"current"`
	StaleReason        string          `json:"stale_reason,omitempty"`
}

type Disposition struct {
	Disposition string    `json:"disposition"`
	Rationale   string    `json:"rationale"`
	RecordedBy  string    `json:"recorded_by"`
	RecordedAt  time.Time `json:"recorded_at"`
}

type QuarantineInfo struct {
	OperationID        string    `json:"operation_id"`
	OriginalLocation   string    `json:"original_location"`
	QuarantineLocation string    `json:"quarantine_location"`
	QuarantinedAt      time.Time `json:"quarantined_at"`
	RetainUntil        time.Time `json:"retain_until"`
}

func (r *ManagedResource) classify(class Classification, reason ...string) {
	// Classes only ever tighten during one assessment.
	rank := map[Classification]int{Eligible: 0, ReviewRequired: 1, Protected: 2}
	if r.Classification == "" || rank[class] > rank[r.Classification] {
		r.Classification = class
	}
	if class != Eligible {
		r.hard = true
	}
	r.Reasons = append(r.Reasons, reason...)
}

// review marks content that an owner may resolve with a disposition bound to the
// exact evidence digest (for example, unique rows judged to be rehearsal output).
func (r *ManagedResource) review(reason, remediation string) {
	if r.Classification == "" || r.Classification == Eligible {
		r.Classification = ReviewRequired
	}
	r.Reasons = append(r.Reasons, reason)
	r.Remediation = append(r.Remediation, remediation)
}

func (r *ManagedResource) finish() {
	if r.Classification == "" {
		r.Classification = ReviewRequired
		r.Reasons = append(r.Reasons, "safety status could not be established")
	}
	r.Reasons = nonNil(r.Reasons)
	r.Remediation = nonNil(r.Remediation)
	r.Details = nonNilMap(r.Details)
	r.Identity = nonNilMap(r.Identity)
	r.ResourceID = Identity(r.Backend, r.IdentityKey)
	r.Actions = r.availableActions()
	if r.Recovery == "" {
		r.Recovery = recoveryFor[r.Classification]
	}
}

var recoveryFor = map[Classification]string{Eligible: RecoveryDisposable, ReviewRequired: RecoveryPending, Protected: RecoveryProtected}

func (r *ManagedResource) availableActions() []string {
	if r.Quarantine != nil {
		if r.Classification == Protected {
			return []string{ActionRestore}
		}
		return []string{ActionRestore, ActionPurge}
	}
	if r.Classification != Eligible {
		return []string{}
	}
	if r.Backend == "git" {
		return []string{ActionDelete}
	}
	return []string{ActionDelete, ActionQuarantine}
}

func nonNil(values []string) []string {
	if values == nil {
		return []string{}
	}
	return values
}

func nonNilMap(values map[string]any) map[string]any {
	if values == nil {
		return map[string]any{}
	}
	return values
}

// Allows reports whether the action is offered for the resource as assessed now.
func (r ManagedResource) Allows(action string) bool { return slices.Contains(r.Actions, action) }

// Authority is the verified identity of the authoritative operating database.
type Authority struct {
	SystemIdentifier string `json:"system_identifier"`
	OID              int64  `json:"oid"`
	Database         string `json:"database"`
	Verified         bool   `json:"verified"`
	Problem          string `json:"problem,omitempty"`
}

func (a Authority) IdentityKey() string { return PostgresIdentityKey(a.SystemIdentifier, a.OID) }

func PostgresIdentityKey(system string, oid int64) string {
	return fmt.Sprintf("postgres:%s:%d", system, oid)
}

// VerifyAuthority binds the database the API is connected to (the one every
// operating service uses through DATABASE_URL) as the authoritative operating
// database on first use, then requires every later check to match that exact
// system identifier and OID. Any mismatch or read failure fails closed: database
// deletion is disabled until the identity is verified again.
func VerifyAuthority(ctx context.Context, pool *pgxpool.Pool) Authority {
	var a Authority
	if err := pool.QueryRow(ctx, `SELECT (SELECT system_identifier::text FROM pg_control_system()),
 d.oid::bigint, d.datname FROM pg_database d WHERE d.datname=current_database()`).Scan(&a.SystemIdentifier, &a.OID, &a.Database); err != nil {
		a.Problem = "cannot read the connected database identity: " + err.Error()
		return a
	}
	identity, _ := json.Marshal(map[string]any{"system_identifier": a.SystemIdentifier, "oid": a.OID, "database": a.Database})
	_, err := pool.Exec(ctx, `INSERT INTO football.storage_protections(backend,identity_key,identity,role,reason,recorded_by)
 SELECT 'postgres',$1,$2,'AUTHORITATIVE_OPERATING_DATABASE',
 'Operating database used by the API, workers and orchestrator through DATABASE_URL.','api:connected-operating-database'
 WHERE NOT EXISTS(SELECT 1 FROM football.storage_protections WHERE role='AUTHORITATIVE_OPERATING_DATABASE'
 AND identity->>'system_identifier'=$3)
 ON CONFLICT DO NOTHING`, a.IdentityKey(), identity, a.SystemIdentifier)
	if err != nil {
		a.Problem = "cannot register the authoritative identity: " + err.Error()
		return a
	}
	var registered string
	if err = pool.QueryRow(ctx, `SELECT identity_key FROM football.storage_protections
 WHERE role='AUTHORITATIVE_OPERATING_DATABASE' AND identity->>'system_identifier'=$1`, a.SystemIdentifier).Scan(&registered); err != nil {
		a.Problem = "authoritative identity unavailable: " + err.Error()
		return a
	}
	if registered != a.IdentityKey() {
		a.Problem = "the connected database is not the registered authoritative database (" + registered + "); database operations are disabled"
		return a
	}
	a.Verified = true
	return a
}

// Protections returns every protection keyed by identity.
func Protections(ctx context.Context, q interface {
	Query(context.Context, string, ...any) (pgx.Rows, error)
}) (map[string][]string, error) {
	rows, err := q.Query(ctx, `SELECT identity_key, role||': '||reason FROM football.storage_protections ORDER BY recorded_at`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := map[string][]string{}
	for rows.Next() {
		var key, reason string
		if err = rows.Scan(&key, &reason); err != nil {
			return nil, err
		}
		result[key] = append(result[key], reason)
	}
	return result, rows.Err()
}

// Fingerprint is a stable digest of the observed facts that an owner reviewed.
func Fingerprint(parts ...any) string {
	payload, _ := json.Marshal(parts)
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

func latestDisposition(ctx context.Context, pool *pgxpool.Pool, identityKey, evidence string) (*Disposition, error) {
	if evidence == "" {
		return nil, nil
	}
	var d Disposition
	err := pool.QueryRow(ctx, `SELECT disposition,rationale,recorded_by,recorded_at FROM football.storage_dispositions
 WHERE identity_key=$1 AND evidence_sha256=$2 ORDER BY recorded_at DESC LIMIT 1`, identityKey, evidence).Scan(&d.Disposition, &d.Rationale, &d.RecordedBy, &d.RecordedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return &d, err
}

// applyDisposition lets a recorded owner decision resolve a REVIEW_REQUIRED
// resource. It can never lift PROTECTED: protection is checked first and wins.
func applyDisposition(r *ManagedResource, d *Disposition) {
	r.Disposition = d
	if d == nil {
		return
	}
	switch d.Disposition {
	case "PRESERVE":
		r.classify(Protected, "owner decided to preserve this resource")
	case "UNIQUE_DATA_NOT_REQUIRED":
		if r.Classification == ReviewRequired && !r.hard {
			r.Classification = Eligible
			r.Reasons = append(r.Reasons, "owner recorded that the reviewed unique content is not required")
			r.Remediation = nil
		}
	}
}

func purposeFromName(name string) string {
	switch {
	case strings.Contains(name, "test"):
		return "TEST"
	case strings.Contains(name, "rehearsal"), strings.Contains(name, "_r3_"), strings.Contains(name, "_fr_"):
		return "REHEARSAL"
	case strings.Contains(name, "restore"), strings.Contains(name, "recovery"):
		return "RESTORE"
	case strings.Contains(name, "shadow"), strings.Contains(name, "phase"), strings.Contains(name, "integration"):
		return "DEVELOPMENT"
	default:
		return "UNKNOWN"
	}
}
