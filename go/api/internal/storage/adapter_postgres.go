package storage

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// QuarantinePrefix names a database isolated by Storage Management. The identity
// (system identifier + OID) is unchanged by the rename, so protection and
// evidence still bind to it.
const QuarantinePrefix = "matchforge_quarantine_"

// DefaultEvidenceMaxAge bounds how old a comparison may be before deletion must be
// re-verified.
const DefaultEvidenceMaxAge = 7 * 24 * time.Hour

type databaseRow struct {
	name        string
	oid         int64
	size        int64
	created     *time.Time
	allowConn   bool
	connections int
	comment     string
	// activity digests client-session and row-write statistics; it changes
	// whenever a client uses the database. Transaction and read counters are
	// excluded because autovacuum workers advance them on idle databases.
	activity string
}

func readDatabases(ctx context.Context, pool *pgxpool.Pool) ([]databaseRow, error) {
	rows, err := pool.Query(ctx, `SELECT d.datname,d.oid::bigint,pg_database_size(d.oid),d.datallowconn,
 (SELECT count(*) FROM pg_stat_activity a WHERE a.datid=d.oid AND a.pid<>pg_backend_pid())::int,
 coalesce(shobj_description(d.oid,'pg_database'),''),
 concat_ws('|',d.datname,s.sessions,s.session_time,s.tup_inserted,s.tup_updated,s.tup_deleted,s.temp_files,s.stats_reset)
 FROM pg_database d LEFT JOIN pg_stat_database s ON s.datid=d.oid
 WHERE NOT d.datistemplate ORDER BY pg_database_size(d.oid) DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var result []databaseRow
	for rows.Next() {
		var d databaseRow
		var counters string
		if err = rows.Scan(&d.name, &d.oid, &d.size, &d.allowConn, &d.connections, &d.comment, &counters); err != nil {
			return nil, err
		}
		d.activity = Fingerprint("pg_stat_database", counters)
		result = append(result, d)
	}
	if err = rows.Err(); err != nil {
		return nil, err
	}
	// Creation time needs file-read privilege; absence only weakens evidence binding.
	for i := range result {
		var created time.Time
		if pool.QueryRow(ctx, `SELECT (pg_stat_file('base/'||$1::bigint::text||'/PG_VERSION')).modification`, result[i].oid).Scan(&created) == nil {
			result[i].created = &created
		}
	}
	return result, nil
}

type databaseFacts struct {
	protections  map[string][]string
	evidence     map[string]storedEvidence
	reservations map[int64]string
	quarantined  map[string]QuarantineInfo
	lifecycle    map[string]LifecycleRecord
}

type storedEvidence struct {
	Evidence
	oid     int64
	created *time.Time
	size    int64
}

func loadDatabaseFacts(ctx context.Context, pool *pgxpool.Pool, system string) (databaseFacts, error) {
	facts := databaseFacts{evidence: map[string]storedEvidence{}}
	var err error
	if facts.protections, err = Protections(ctx, pool); err != nil {
		return facts, err
	}
	rows, err := pool.Query(ctx, `SELECT DISTINCT ON (identity_key) identity_key,evidence_id::text,finding,unique_identity_rows,
 tables,evidence_sha256,observed_at,source,database_oid,database_created_at,size_bytes
 FROM football.storage_database_evidence WHERE system_identifier=$1 ORDER BY identity_key,observed_at DESC`, system)
	if err != nil {
		return facts, err
	}
	for rows.Next() {
		var key string
		var e storedEvidence
		if err = rows.Scan(&key, &e.EvidenceID, &e.Finding, &e.UniqueIdentityRows, &e.Tables, &e.SHA256, &e.ObservedAt, &e.Source, &e.oid, &e.created, &e.size); err != nil {
			rows.Close()
			return facts, err
		}
		facts.evidence[key] = e
	}
	rows.Close()
	if err = rows.Err(); err != nil {
		return facts, err
	}
	if facts.reservations, err = managedReservations(ctx, pool, system); err != nil {
		return facts, err
	}
	if facts.quarantined, err = openQuarantines(ctx, pool, "postgres"); err != nil {
		return facts, err
	}
	facts.lifecycle, err = lifecycleRecords(ctx, pool, `backend='postgres' AND state IN ('ELIGIBLE','DELETING')`)
	return facts, err
}

// managedReservations returns managed rehearsal reservations whose producing job
// still holds its lease, keyed by database OID.
func managedReservations(ctx context.Context, pool *pgxpool.Pool, system string) (map[int64]string, error) {
	rows, err := pool.Query(ctx, `SELECT (r.resource_identity->>'oid')::bigint, r.owner_name FROM football.storage_reservations r
 JOIN football.work_items w USING(work_id) WHERE r.released_at IS NULL AND r.resource_identity ? 'oid'
 AND r.resource_identity->>'cluster'=$1`, system)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := map[int64]string{}
	for rows.Next() {
		var oid int64
		var owner string
		if err = rows.Scan(&oid, &owner); err != nil {
			return nil, err
		}
		result[oid] = owner
	}
	return result, rows.Err()
}

// ListDatabases assesses every database in the API's cluster.
func ListDatabases(ctx context.Context, pool *pgxpool.Pool, auth Authority, now time.Time, maxAge time.Duration) ([]ManagedResource, error) {
	databases, err := readDatabases(ctx, pool)
	if err != nil {
		return nil, err
	}
	system := auth.SystemIdentifier
	if system == "" {
		return nil, errors.New("cluster identity unavailable")
	}
	facts, err := loadDatabaseFacts(ctx, pool, system)
	if err != nil {
		return nil, err
	}
	result := make([]ManagedResource, 0, len(databases))
	for _, d := range databases {
		r := assessDatabase(d, auth, facts, now, maxAge)
		disposition, err := latestDisposition(ctx, pool, r.IdentityKey, r.EvidenceSHA256)
		if err != nil {
			return nil, err
		}
		applyDisposition(&r, disposition)
		r.finish()
		result = append(result, r)
	}
	return result, nil
}

func assessDatabase(d databaseRow, auth Authority, facts databaseFacts, now time.Time, maxAge time.Duration) ManagedResource {
	key := PostgresIdentityKey(auth.SystemIdentifier, d.oid)
	size := d.size
	r := ManagedResource{
		Backend: "postgres", Kind: "database", Name: d.name, Location: auth.SystemIdentifier + "/" + d.name,
		IdentityKey: key, Purpose: purposeFromName(d.name), LogicalBytes: &size, AllocatedBytes: &size,
		Complete: true, ObservedAt: now, ActiveConsumers: d.connections,
		Identity: map[string]any{"system_identifier": auth.SystemIdentifier, "oid": d.oid, "database": d.name},
		Details:  map[string]any{"allow_connections": d.allowConn, "created_at": d.created, "measurement": "pg_database_size; files inside the PostgreSQL volume"},
	}
	if q, ok := facts.quarantined[key]; ok {
		r.Quarantine = &q
		r.Purpose = "QUARANTINED"
	}
	if auth.Verified && d.oid == auth.OID {
		r.Role, r.Purpose, r.Recovery = "AUTHORITATIVE_OPERATING_DATABASE", "OPERATING", RecoveryWithGaps
		r.classify(Protected, AuthoritativeMessage)
		return r
	}
	protectDatabase(&r, d, auth, facts)
	if r.Quarantine != nil {
		r.classify(Eligible, "quarantined: connections disabled; restore or purge")
		return r
	}
	if applyLifecycle(&r, d, facts.lifecycle[key]) {
		return r
	}
	applyEvidence(&r, d, facts, now, maxAge)
	return r
}

// applyLifecycle offers deletion of a registered disposable test database only
// while the five-hour policy holds it ELIGIBLE (or its deletion is running), its
// marker still matches the creation record and its activity counters have not
// moved since that decision. Protection was applied first and always wins.
func applyLifecycle(r *ManagedResource, d databaseRow, lc LifecycleRecord) bool {
	if lc.Class != ClassTestDatabase || (lc.State != LifecycleEligible && lc.State != LifecycleDeleting) {
		return false
	}
	if lc.Fingerprint != d.activity || !testMarkerMatches(d.comment, lc) || !sameOID(lc.Identity, d.oid) {
		return false
	}
	r.Purpose = "TEST"
	r.EvidenceSHA256 = Fingerprint(lc.IdentityKey, lc.Fingerprint, lc.EligibleAt)
	r.Details["lifecycle"] = map[string]any{"state": lc.State, "eligible_at": lc.EligibleAt, "completion": lc.Completion}
	r.classify(Eligible, "verified disposable test database; the five-hour lifecycle policy is satisfied")
	return true
}

func sameOID(identity map[string]any, oid int64) bool {
	value, err := identityOID(identity)
	return err == nil && value == oid
}

// protectDatabase applies every hard protection: unverifiable authority, system
// database, recorded protections, managed reservations and active consumers.
func protectDatabase(r *ManagedResource, d databaseRow, auth Authority, facts databaseFacts) {
	if !auth.Verified {
		r.classify(Protected, "Authoritative database identity could not be verified; database deletion is disabled until it is. "+auth.Problem)
	}
	if d.name == "postgres" {
		r.Role, r.Purpose = "SYSTEM_DATABASE", "SYSTEM"
		r.classify(Protected, "PostgreSQL maintenance database")
	}
	for _, reason := range facts.protections[r.IdentityKey] {
		r.Role = strings.SplitN(reason, ":", 2)[0]
		r.classify(Protected, reason)
	}
	if owner, ok := facts.reservations[d.oid]; ok {
		r.classify(Protected, "owned by an unreleased managed rehearsal reservation ("+owner+")")
	}
	if d.connections > 0 {
		r.classify(Protected, fmt.Sprintf("%d active connection(s); a workload is using this database", d.connections))
	}
}

func applyEvidence(r *ManagedResource, d databaseRow, facts databaseFacts, now time.Time, maxAge time.Duration) {
	e, ok := facts.evidence[r.IdentityKey]
	if !ok {
		r.review("not yet compared with the authoritative database", "Run Compare to check for canonical identities absent from the operating database.")
		return
	}
	current := e.Evidence
	current.StaleReason = staleReason(e, d, now, maxAge)
	current.Current = current.StaleReason == ""
	r.Evidence = &current
	r.EvidenceSHA256 = e.SHA256
	if !current.Current {
		r.classify(ReviewRequired, "comparison evidence is stale: "+current.StaleReason)
		r.Remediation = append(r.Remediation, "Run Compare again.")
		return
	}
	switch e.Finding {
	case "NO_UNIQUE_CANONICAL_IDENTITIES":
		r.classify(Eligible, "no canonical identities absent from the authoritative database")
	case "UNIQUE_CANONICAL_IDENTITIES_PRESENT":
		r.review(fmt.Sprintf("%d canonical identity row(s) exist only in this database", valueOr(e.UniqueIdentityRows)),
			"Reconcile valid rows into the operating database through governed admission, or record that the unique rows are not required.")
	default:
		r.classify(ReviewRequired, "comparison was inconclusive: "+e.Finding)
		r.Remediation = append(r.Remediation, "Investigate the schema difference or error, then compare again.")
	}
}

func staleReason(e storedEvidence, d databaseRow, now time.Time, maxAge time.Duration) string {
	switch {
	case e.oid != d.oid:
		return "database OID changed"
	case e.created != nil && d.created != nil && !e.created.Equal(*d.created):
		return "database was recreated"
	case sizeDrift(e.size, d.size):
		return fmt.Sprintf("size changed from %d to %d bytes", e.size, d.size)
	case now.Sub(e.ObservedAt) > maxAge:
		return "comparison is older than the evidence limit"
	}
	return ""
}

func valueOr(v *int64) int64 {
	if v == nil {
		return 0
	}
	return *v
}

func sizeDrift(before, after int64) bool {
	delta := before - after
	if delta < 0 {
		delta = -delta
	}
	return delta > 64<<20 && delta*100 > before
}

// databaseExecutor performs fenced PostgreSQL lifecycle operations. It never
// accepts SQL or names from a client: the target is resolved by OID.
type databaseExecutor struct{ pool *pgxpool.Pool }

func (x databaseExecutor) resolve(ctx context.Context, r ManagedResource) (string, error) {
	oid, err := identityOID(r.Identity)
	if err != nil {
		return "", err
	}
	var name string
	err = x.pool.QueryRow(ctx, `SELECT datname FROM pg_database WHERE oid=$1::oid AND NOT datistemplate AND datname<>current_database()`, oid).Scan(&name)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", errors.New("database identity no longer exists")
	}
	return name, err
}

func identityOID(identity map[string]any) (int64, error) {
	switch v := identity["oid"].(type) {
	case int64:
		return v, nil
	case float64:
		return int64(v), nil
	case json.Number:
		return v.Int64()
	case string:
		return strconv.ParseInt(v, 10, 64)
	}
	return 0, errors.New("database identity has no OID")
}

func (x databaseExecutor) fence(ctx context.Context, name string) error {
	if _, err := x.pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{name}.Sanitize()+` WITH ALLOW_CONNECTIONS false`); err != nil {
		return err
	}
	var connections int
	if err := x.pool.QueryRow(ctx, `SELECT count(*) FROM pg_stat_activity WHERE datname=$1`, name).Scan(&connections); err != nil {
		return err
	}
	if connections > 0 {
		_, _ = x.pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{name}.Sanitize()+` WITH ALLOW_CONNECTIONS true`)
		return fmt.Errorf("%d connection(s) appeared; deletion abandoned", connections)
	}
	return nil
}

func (x databaseExecutor) Delete(ctx context.Context, r ManagedResource) (Measurement, error) {
	m := Measurement{Method: "pg_database_size of the exact OID, then verified absence"}
	name, err := x.resolve(ctx, r)
	if err != nil {
		return m, err
	}
	oid, _ := identityOID(r.Identity)
	if err = x.pool.QueryRow(ctx, `SELECT pg_database_size($1::oid)`, oid).Scan(&m.BeforeBytes); err != nil {
		return m, err
	}
	m.ClusterBefore = clusterBytes(ctx, x.pool)
	if r.Quarantine == nil {
		if err = x.fence(ctx, name); err != nil {
			return m, err
		}
	}
	// No FORCE: an unexpected session makes the drop fail instead of being killed.
	if _, err = x.pool.Exec(ctx, `DROP DATABASE `+pgx.Identifier{name}.Sanitize()); err != nil {
		if r.Quarantine == nil {
			_, _ = x.pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{name}.Sanitize()+` WITH ALLOW_CONNECTIONS true`)
		}
		return m, err
	}
	var exists bool
	if err = x.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM pg_database WHERE oid=$1::oid)`, oid).Scan(&exists); err != nil {
		return m, err
	}
	if exists {
		return m, errors.New("database still present after DROP DATABASE")
	}
	m.VerifiedAbsent = true
	m.ClusterAfter = clusterBytes(ctx, x.pool)
	m.ReclaimedBytes = &m.BeforeBytes
	return m, nil
}

func (x databaseExecutor) Quarantine(ctx context.Context, r ManagedResource, _ string) (Measurement, string, error) {
	m := Measurement{Method: "rename and disallow connections; files stay in the cluster"}
	name, err := x.resolve(ctx, r)
	if err != nil {
		return m, "", err
	}
	oid, _ := identityOID(r.Identity)
	target := fmt.Sprintf("%s%d", QuarantinePrefix, oid)
	if err = x.fence(ctx, name); err != nil {
		return m, "", err
	}
	if _, err = x.pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{name}.Sanitize()+` RENAME TO `+pgx.Identifier{target}.Sanitize()); err != nil {
		_, _ = x.pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{name}.Sanitize()+` WITH ALLOW_CONNECTIONS true`)
		return m, "", err
	}
	zero := int64(0)
	m.ReclaimedBytes = &zero
	return m, r.Identity["system_identifier"].(string) + "/" + target, nil
}

func (x databaseExecutor) Restore(ctx context.Context, r ManagedResource) (Measurement, error) {
	m := Measurement{Method: "rename back and allow connections"}
	if r.Quarantine == nil {
		return m, errors.New("resource is not quarantined")
	}
	name, err := x.resolve(ctx, r)
	if err != nil {
		return m, err
	}
	original := strings.TrimPrefix(r.Quarantine.OriginalLocation, r.Identity["system_identifier"].(string)+"/")
	var taken bool
	if err = x.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)`, original).Scan(&taken); err != nil {
		return m, err
	}
	if taken {
		return m, errors.New("original database name is now used by another database; restore refused")
	}
	if _, err = x.pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{name}.Sanitize()+` RENAME TO `+pgx.Identifier{original}.Sanitize()); err != nil {
		return m, err
	}
	_, err = x.pool.Exec(ctx, `ALTER DATABASE `+pgx.Identifier{original}.Sanitize()+` WITH ALLOW_CONNECTIONS true`)
	zero := int64(0)
	m.ReclaimedBytes = &zero
	return m, err
}

func clusterBytes(ctx context.Context, pool *pgxpool.Pool) *int64 {
	var total int64
	if pool.QueryRow(ctx, `SELECT coalesce(sum(pg_database_size(oid)),0)::bigint FROM pg_database`).Scan(&total) != nil {
		return nil
	}
	return &total
}
