package storage

import (
	"context"
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
)

// CanonicalTables are compared by primary key. Work queues and metrics are
// excluded because every rehearsal creates its own operational rows.
var CanonicalTables = []string{
	"competitions", "seasons", "teams", "players", "matches", "event_catalog",
	"product_competitions", "product_teams", "product_team_aliases", "product_fixtures",
	"product_team_match_history", "product_match_history_decisions", "product_identity_admissions",
	"product_provider_mapping_decisions", "fixture_identity_resolutions", "team_provider_mappings",
	"match_provider_mappings", "player_provider_mappings", "player_source_facts", "product_forecasts",
	"baseline_forecasts", "model_artifacts", "model_artifact_files", "source_resources",
	"source_snapshots", "resource_observation_artifacts", "product_read_reports",
}

type TableComparison struct {
	Present       bool     `json:"present"`
	Columns       []string `json:"columns,omitempty"`
	Schema        string   `json:"schema,omitempty"`
	Rows          int64    `json:"rows"`
	Absent        int64    `json:"absent_from_authoritative"`
	AbsentSamples []string `json:"absent_samples"`
}

type CompareStatus struct {
	ResourceID string     `json:"resource_id"`
	Name       string     `json:"name"`
	State      string     `json:"state"`
	Error      string     `json:"error,omitempty"`
	StartedAt  *time.Time `json:"started_at"`
	FinishedAt *time.Time `json:"finished_at"`
}

type reference struct {
	authority Authority
	keys      map[string][]int64
	columns   map[string][]string
	builtAt   time.Time
}

type comparator struct {
	mu      sync.Mutex
	queue   []CompareStatus
	running bool
	ref     *reference
}

var compares comparator

// CompareQueue reports queued, running and recent comparisons.
func CompareQueue() []CompareStatus {
	compares.mu.Lock()
	defer compares.mu.Unlock()
	return slices.Clone(compares.queue)
}

// StartCompare queues read-only comparisons for the selected databases.
func (m *Manager) StartCompare(ctx context.Context, ids []string) (int, error) {
	if len(ids) == 0 || len(ids) > MaxBatch {
		return 0, errors.New("select between 1 and 50 databases")
	}
	byID, err := m.resourcesByID(ctx)
	if err != nil {
		return 0, err
	}
	compares.mu.Lock()
	defer compares.mu.Unlock()
	queued := 0
	for _, id := range dedupe(ids) {
		if r, ok := byID[id]; ok && comparable(r) && !queuedCompare(id) {
			compares.queue = append(compares.queue, CompareStatus{ResourceID: id, Name: r.Name, State: "QUEUED"})
			queued++
		}
	}
	compares.queue = compares.queue[max(0, len(compares.queue)-200):]
	if queued > 0 && !compares.running {
		compares.running = true
		go m.drainCompares(context.WithoutCancel(ctx))
	}
	return queued, nil
}

func (m *Manager) resourcesByID(ctx context.Context) (map[string]ManagedResource, error) {
	inv, err := m.Inventory(ctx)
	if err != nil {
		return nil, err
	}
	if !inv.Authority.Verified {
		return nil, errors.New("authoritative identity unverified; comparison refused")
	}
	byID := map[string]ManagedResource{}
	for _, r := range inv.Resources {
		byID[r.ResourceID] = r
	}
	return byID, nil
}

func comparable(r ManagedResource) bool {
	return r.Backend == "postgres" && r.Role != "AUTHORITATIVE_OPERATING_DATABASE" && r.Quarantine == nil && r.Name != "postgres"
}

// queuedCompare must be called with compares.mu held.
func queuedCompare(id string) bool {
	return slices.ContainsFunc(compares.queue, func(c CompareStatus) bool {
		return c.ResourceID == id && (c.State == "QUEUED" || c.State == "RUNNING")
	})
}

func (m *Manager) drainCompares(ctx context.Context) {
	for {
		compares.mu.Lock()
		index := slices.IndexFunc(compares.queue, func(c CompareStatus) bool { return c.State == "QUEUED" })
		if index < 0 {
			compares.running = false
			compares.mu.Unlock()
			return
		}
		now := time.Now().UTC()
		compares.queue[index].State, compares.queue[index].StartedAt = "RUNNING", &now
		item := compares.queue[index]
		compares.mu.Unlock()
		err := m.compareOne(ctx, item.ResourceID)
		compares.mu.Lock()
		done := time.Now().UTC()
		for i := range compares.queue {
			if compares.queue[i].ResourceID == item.ResourceID && compares.queue[i].State == "RUNNING" {
				compares.queue[i].FinishedAt = &done
				compares.queue[i].State = "SUCCEEDED"
				if err != nil {
					compares.queue[i].State, compares.queue[i].Error = "FAILED", err.Error()
				}
			}
		}
		compares.mu.Unlock()
	}
}

func (m *Manager) reference(ctx context.Context, auth Authority) (*reference, error) {
	compares.mu.Lock()
	ref := compares.ref
	compares.mu.Unlock()
	if ref != nil && ref.authority.IdentityKey() == auth.IdentityKey() && time.Since(ref.builtAt) < 30*time.Minute {
		return ref, nil
	}
	conn, err := m.Pool.Acquire(ctx)
	if err != nil {
		return nil, err
	}
	defer conn.Release()
	ref = &reference{authority: auth, keys: map[string][]int64{}, builtAt: time.Now()}
	if ref.columns, err = primaryKeys(ctx, conn.Conn()); err != nil {
		return nil, err
	}
	for table, columns := range ref.columns {
		keys, err := keyHashes(ctx, conn.Conn(), table, columns)
		if err != nil {
			return nil, err
		}
		slices.Sort(keys)
		ref.keys[table] = slices.Compact(keys)
	}
	compares.mu.Lock()
	compares.ref = ref
	compares.mu.Unlock()
	return ref, nil
}

func primaryKeys(ctx context.Context, conn *pgx.Conn) (map[string][]string, error) {
	rows, err := conn.Query(ctx, `SELECT c.relname, array_agg(a.attname::text ORDER BY k.ord)
 FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
 CROSS JOIN LATERAL unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
 JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
 WHERE i.indisprimary AND n.nspname='football' AND c.relname=ANY($1) GROUP BY c.relname`, CanonicalTables)
	if err != nil {
		return nil, err
	}
	result := map[string][]string{}
	for rows.Next() {
		var table string
		var columns []string
		if err = rows.Scan(&table, &columns); err != nil {
			rows.Close()
			return nil, err
		}
		result[table] = columns
	}
	rows.Close()
	return result, rows.Err()
}

func keyExpression(columns []string) string {
	quoted := make([]string, len(columns))
	for i, c := range columns {
		quoted[i] = pgx.Identifier{c}.Sanitize()
	}
	return "hashtextextended(row(" + strings.Join(quoted, ",") + ")::text,0)"
}

func keyHashes(ctx context.Context, conn *pgx.Conn, table string, columns []string) ([]int64, error) {
	rows, err := conn.Query(ctx, `SELECT `+keyExpression(columns)+` FROM football.`+pgx.Identifier{table}.Sanitize())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var keys []int64
	for rows.Next() {
		var k int64
		if err = rows.Scan(&k); err != nil {
			return nil, err
		}
		keys = append(keys, k)
	}
	return keys, rows.Err()
}

func (m *Manager) compareTarget(ctx context.Context, resourceID string) (Authority, databaseRow, error) {
	auth := VerifyAuthority(ctx, m.Pool)
	if !auth.Verified {
		return auth, databaseRow{}, errors.New("authoritative identity unverified")
	}
	databases, err := readDatabases(ctx, m.Pool)
	if err != nil {
		return auth, databaseRow{}, err
	}
	for _, d := range databases {
		if d.oid != auth.OID && Identity("postgres", PostgresIdentityKey(auth.SystemIdentifier, d.oid)) == resourceID {
			return auth, d, nil
		}
	}
	return auth, databaseRow{}, errors.New("database not found or authoritative")
}

// connectReadOnly opens the exact candidate database and re-checks its identity.
func (m *Manager) connectReadOnly(ctx context.Context, auth Authority, target databaseRow) (*pgx.Conn, error) {
	config := m.Pool.Config().ConnConfig.Copy()
	config.Database = target.name
	config.RuntimeParams["default_transaction_read_only"] = "on"
	config.RuntimeParams["statement_timeout"] = "900000"
	conn, err := pgx.ConnectConfig(ctx, config)
	if err != nil {
		return nil, err
	}
	var oid int64
	var system string
	err = conn.QueryRow(ctx, `SELECT (SELECT oid::bigint FROM pg_database WHERE datname=current_database()),
 (SELECT system_identifier::text FROM pg_control_system())`).Scan(&oid, &system)
	if err == nil && (oid != target.oid || system != auth.SystemIdentifier) {
		err = errors.New("database identity changed during comparison")
	}
	if err != nil {
		_ = conn.Close(ctx)
		return nil, err
	}
	return conn, nil
}

// closeAndWait closes the comparison session and waits briefly until PostgreSQL
// has ended its backend. Closing is asynchronous on the server; without the wait
// the next inventory can count the finished comparison as an active consumer.
func (m *Manager) closeAndWait(ctx context.Context, conn *pgx.Conn) {
	pid := conn.PgConn().PID()
	_ = conn.Close(ctx)
	for deadline := time.Now().Add(5 * time.Second); time.Now().Before(deadline); time.Sleep(20 * time.Millisecond) {
		var present bool
		if m.Pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid=$1)`, pid).Scan(&present) != nil || !present {
			return
		}
	}
}

func (m *Manager) compareOne(ctx context.Context, resourceID string) error {
	auth, target, err := m.compareTarget(ctx, resourceID)
	if err != nil {
		return err
	}
	ref, err := m.reference(ctx, auth)
	if err != nil {
		return err
	}
	conn, err := m.connectReadOnly(ctx, auth, target)
	if err != nil {
		return err
	}
	defer m.closeAndWait(ctx, conn)
	tables, finding, unique, err := compareTables(ctx, conn, ref)
	if err != nil {
		return err
	}
	content, err := contentFingerprint(ctx, conn)
	if err != nil {
		return err
	}
	payload, _ := json.Marshal(tables)
	key := PostgresIdentityKey(auth.SystemIdentifier, target.oid)
	// Physical size stays out of the digest: pg_database_size changes without any
	// content change (relcache init file, free-space and visibility maps), which
	// would void owner dispositions spontaneously. Large size drift still makes
	// evidence stale (staleReason); content outside the canonical tables is bound
	// through contentFingerprint instead.
	digest := Fingerprint("matchforge-database-comparison-v2", key, target.created, auth.IdentityKey(), finding, tables, content)
	_, err = m.Pool.Exec(ctx, `INSERT INTO football.storage_database_evidence(identity_key,system_identifier,database_oid,
 database_name,database_created_at,size_bytes,authoritative_identity_key,finding,unique_identity_rows,tables,evidence_sha256,source)
 VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'ADMIN_COMPARE')`, key, auth.SystemIdentifier, target.oid, target.name, target.created,
		target.size, auth.IdentityKey(), finding, unique, payload, digest)
	return err
}

// contentFingerprint summarises everything in the candidate database that the
// canonical-table comparison does not cover, using only values that change when
// a client changes the database: user schemas, relations and their storage
// files (TRUNCATE, VACUUM FULL and rewrites replace them), column definitions,
// cumulative row-write counters, sequence positions, function bodies and large
// objects. It deliberately excludes physical sizes and planner statistics,
// which autovacuum and relation-cache maintenance change on their own. A
// statistics reset or crash recovery clears the write counters, so the digest
// changes and any disposition bound to it lapses (fail closed).
func contentFingerprint(ctx context.Context, conn *pgx.Conn) (string, error) {
	var summary string
	err := conn.QueryRow(ctx, `WITH user_ns AS (
 SELECT oid, nspname FROM pg_namespace
 WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(toast_)?temp_'),
rels AS (
 SELECT string_agg(concat_ws('|',n.nspname,c.relname,c.relkind,c.relpersistence,c.relfilenode,
   coalesce(s.n_tup_ins,0),coalesce(s.n_tup_upd,0),coalesce(s.n_tup_del,0)), E'\n' ORDER BY n.nspname,c.relname) AS v
 FROM pg_class c JOIN user_ns n ON n.oid=c.relnamespace LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
 WHERE c.relpersistence<>'t'),
cols AS (
 SELECT string_agg(concat_ws('|',n.nspname,c.relname,a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull),
   E'\n' ORDER BY n.nspname,c.relname,a.attnum) AS v
 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN user_ns n ON n.oid=c.relnamespace
 WHERE a.attnum>0 AND NOT a.attisdropped AND c.relpersistence<>'t'),
seqs AS (
 SELECT string_agg(concat_ws('|',schemaname,sequencename,last_value), E'\n' ORDER BY schemaname,sequencename) AS v
 FROM pg_sequences WHERE schemaname IN (SELECT nspname FROM user_ns)),
procs AS (
 SELECT string_agg(concat_ws('|',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),md5(p.prosrc)),
   E'\n' ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS v
 FROM pg_proc p JOIN user_ns n ON n.oid=p.pronamespace)
SELECT encode(sha256(convert_to(concat_ws(E'\n--\n',
 (SELECT string_agg(nspname, ',' ORDER BY nspname) FROM user_ns),
 (SELECT v FROM rels),(SELECT v FROM cols),(SELECT v FROM seqs),(SELECT v FROM procs),
 (SELECT count(*)::text FROM pg_largeobject_metadata)),'UTF8')),'hex')`).Scan(&summary)
	return summary, err
}

func compareTables(ctx context.Context, conn *pgx.Conn, ref *reference) (map[string]TableComparison, string, int64, error) {
	columns, err := primaryKeys(ctx, conn)
	if err != nil {
		return nil, "", 0, err
	}
	tables := map[string]TableComparison{}
	var unique int64
	finding := "NO_UNIQUE_CANONICAL_IDENTITIES"
	for table, refColumns := range ref.columns {
		result, err := compareTable(ctx, conn, table, columns[table], refColumns, ref.keys[table])
		if err != nil {
			return nil, "", 0, err
		}
		if result.Schema != "" {
			finding = "UNRESOLVED_SCHEMA_DIFFERENCE"
		}
		unique += result.Absent
		tables[table] = result
	}
	if unique > 0 && finding == "NO_UNIQUE_CANONICAL_IDENTITIES" {
		finding = "UNIQUE_CANONICAL_IDENTITIES_PRESENT"
	}
	return tables, finding, unique, nil
}

func compareTable(ctx context.Context, conn *pgx.Conn, table string, candidate, refColumns []string, reference []int64) (TableComparison, error) {
	if candidate == nil {
		return TableComparison{Present: false, AbsentSamples: []string{}}, nil
	}
	if !slices.Equal(candidate, refColumns) {
		return TableComparison{Present: true, Schema: "PRIMARY_KEY_DIFFERS", Columns: candidate, AbsentSamples: []string{}}, nil
	}
	keys, err := keyHashes(ctx, conn, table, candidate)
	if err != nil {
		return TableComparison{}, err
	}
	result := TableComparison{Present: true, Rows: int64(len(keys)), AbsentSamples: []string{}}
	var missing []int64
	for _, k := range keys {
		if _, found := slices.BinarySearch(reference, k); !found {
			result.Absent++
			missing = append(missing, k)
		}
	}
	if len(missing) > 0 {
		result.AbsentSamples, err = keySamples(ctx, conn, table, candidate, missing[:min(5, len(missing))])
	}
	return result, err
}

func keySamples(ctx context.Context, conn *pgx.Conn, table string, columns []string, hashes []int64) ([]string, error) {
	quoted := make([]string, len(columns))
	for i, c := range columns {
		quoted[i] = pgx.Identifier{c}.Sanitize()
	}
	rows, err := conn.Query(ctx, `SELECT row(`+strings.Join(quoted, ",")+`)::text FROM football.`+pgx.Identifier{table}.Sanitize()+
		` WHERE `+keyExpression(columns)+`=ANY($1) LIMIT 5`, hashes)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, pgx.RowTo[string])
}
