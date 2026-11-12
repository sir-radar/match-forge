// Package testdb holds Go database tests to the same isolation rule as the Python
// integration tests (tests/integration/database_isolation.py).
//
// A test may only reach a database that the harness marked disposable for this run:
// its comment must equal the marker derived from MATCHFORGE_DISPOSABLE_DATABASE_TOKEN,
// it must be on the cluster the harness verified, and it must not register itself as
// the authoritative operating database. Anything that cannot be verified fails the test;
// setting TEST_DATABASE_URL alone is never enough.
package testdb

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

const (
	markerPrefix = "matchforge-disposable-test-database:v1:"
	ownedPrefix  = "matchforge-test-owned-database:v1:"
	tokenEnv     = "MATCHFORGE_DISPOSABLE_DATABASE_TOKEN"
	clusterEnv   = "MATCHFORGE_TEST_CLUSTER_IDENTIFIER"
	preexistEnv  = "MATCHFORGE_TEST_PREEXISTING_DATABASE_OIDS"
	protectedEnv = "MATCHFORGE_PROTECTED_DATABASE_IDENTITIES"
	activeEnv    = "MATCHFORGE_TEST_ISOLATION_ACTIVE"
	preparedEnv  = "MATCHFORGE_PREPARED_TEST_DATABASE_IDENTITY"
)

// Identity is the stable identity of a connected database.
type Identity struct {
	SystemIdentifier  string
	OID               int64
	Name              string
	Comment           *string
	SelfAuthoritative bool
}

// Policy is the run's isolation policy, read from the harness environment.
type Policy struct {
	Token       string
	Cluster     string
	Protected   map[string]bool
	Preexisting map[int64]bool
	// Prepared is the identity the harness proved fresh when it marked it.
	Prepared string
}

// Marker is the database comment that proves a database is disposable for token.
func Marker(token string) string {
	sum := sha256.Sum256([]byte(token))
	return markerPrefix + hex.EncodeToString(sum[:])
}

// OwnedMarker is the comment the Python guard puts on a database a test run created.
func OwnedMarker(token string) string {
	sum := sha256.Sum256([]byte(token))
	return ownedPrefix + hex.EncodeToString(sum[:])
}

// PolicyFromEnvironment reads the policy and fails closed when the harness did not run.
func PolicyFromEnvironment(getenv func(string) string) (Policy, error) {
	token, cluster, rawOIDs := getenv(tokenEnv), getenv(clusterEnv), getenv(preexistEnv)
	if len(token) < 32 || cluster == "" || rawOIDs == "" {
		return Policy{}, fmt.Errorf(
			"database tests must run through the disposable-database harness (make integration); %s, %s and %s are required",
			tokenEnv, clusterEnv, preexistEnv)
	}
	preexisting := map[int64]bool{}
	for _, value := range strings.Split(rawOIDs, ",") {
		if value == "" {
			continue
		}
		oid, err := strconv.ParseInt(value, 10, 64)
		if err != nil {
			return Policy{}, fmt.Errorf("invalid %s: %w", preexistEnv, err)
		}
		preexisting[oid] = true
	}
	protected := map[string]bool{}
	for _, value := range strings.Split(getenv(protectedEnv), ",") {
		if value = strings.TrimSpace(value); value != "" {
			protected[value] = true
		}
	}
	return Policy{Token: token, Cluster: cluster, Protected: protected, Preexisting: preexisting,
		Prepared: getenv(preparedEnv)}, nil
}

// Rejection returns why a connection to identity must be refused, or "" when allowed.
// Like the Python guard, it allows this run's marked database and databases created
// during the run (tagged as owned, or absent from the pre-run OID list).
func (policy Policy) Rejection(identity Identity) string {
	label := fmt.Sprintf("database %q (%s:%d)", identity.Name, identity.SystemIdentifier, identity.OID)
	marked := identity.Comment != nil && *identity.Comment == Marker(policy.Token)
	// Storage tests run VerifyAuthority against the run's own database, which records it
	// as authoritative in its own registry. Only that prepared identity, still carrying
	// this run's marker, is exempt; a copied marker elsewhere is refused.
	prepared := marked && policy.Prepared != "" &&
		policy.Prepared == fmt.Sprintf("%s:%d", identity.SystemIdentifier, identity.OID)
	switch {
	case identity.SelfAuthoritative && !prepared:
		return label + " is registered as the authoritative operating database"
	case policy.Protected[fmt.Sprintf("%s:%d", identity.SystemIdentifier, identity.OID)]:
		return label + " is a protected database identity"
	case identity.SystemIdentifier != policy.Cluster:
		return label + " is on a cluster this test run did not verify"
	case marked:
	case identity.Comment != nil && *identity.Comment == OwnedMarker(policy.Token):
	case !policy.Preexisting[identity.OID]:
	default:
		return label + " is not marked disposable for this test run"
	}
	return ""
}

const identitySQL = `
SELECT (SELECT system_identifier::text FROM pg_control_system()), d.oid::bigint, d.datname,
       shobj_description(d.oid, 'pg_database'),
       to_regclass('football.storage_protections') IS NOT NULL
FROM pg_database d WHERE d.datname = current_database()`

// Only run when the table exists: a partially migrated test database may lack it.
const selfAuthoritativeSQL = `
SELECT EXISTS (SELECT 1 FROM football.storage_protections p
  WHERE p.backend = 'postgres' AND p.role = 'AUTHORITATIVE_OPERATING_DATABASE'
    AND p.identity->>'system_identifier' = $1 AND (p.identity->>'oid')::bigint = $2)`

// ReadIdentity reads the connected database's identity without writing.
func ReadIdentity(ctx context.Context, url string) (Identity, error) {
	connection, err := pgx.Connect(ctx, url)
	if err != nil {
		return Identity{}, fmt.Errorf("cannot connect to verify database identity: %w", err)
	}
	defer connection.Close(ctx)
	var identity Identity
	var protections bool
	err = connection.QueryRow(ctx, identitySQL).Scan(
		&identity.SystemIdentifier, &identity.OID, &identity.Name, &identity.Comment, &protections)
	if err == nil && protections {
		err = connection.QueryRow(ctx, selfAuthoritativeSQL, identity.SystemIdentifier, identity.OID).
			Scan(&identity.SelfAuthoritative)
	}
	if err != nil {
		return Identity{}, fmt.Errorf("cannot verify database identity: %w", err)
	}
	return identity, nil
}

// Verify checks url against the harness policy.
func Verify(ctx context.Context, url string, getenv func(string) string) error {
	policy, err := PolicyFromEnvironment(getenv)
	if err != nil {
		return err
	}
	identity, err := ReadIdentity(ctx, url)
	if err != nil {
		return err
	}
	if reason := policy.Rejection(identity); reason != "" {
		return fmt.Errorf("integration test isolation: %s", reason)
	}
	return nil
}

// URL returns TEST_DATABASE_URL after proving it is this run's disposable database.
// The test is skipped when no URL is set and fails when the URL cannot be verified.
// It also makes Python child processes the test starts install the same guard.
func URL(t testing.TB) string {
	t.Helper()
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("requires the disposable integration database (make integration)")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := Verify(ctx, url, os.Getenv); err != nil {
		t.Fatal(err)
	}
	t.Setenv("DATABASE_URL", url)
	t.Setenv(activeEnv, "1")
	t.Setenv("PYTHONPATH", PythonPath(os.Getenv("PYTHONPATH")))
	return url
}

// PythonPath prepends the Python child-process guard to path, once.
func PythonPath(path string) string {
	site := siteDirectory()
	parts := []string{site}
	for _, part := range filepath.SplitList(path) {
		if part != "" && part != site {
			parts = append(parts, part)
		}
	}
	return strings.Join(parts, string(os.PathListSeparator))
}

func siteDirectory() string {
	_, file, _, _ := runtime.Caller(0)
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "..", "tests", "integration", "isolation_site"))
}
