package testdb

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func environment(values map[string]string) func(string) string {
	return func(key string) string { return values[key] }
}

func TestPolicyFailsClosedWithoutHarness(t *testing.T) {
	for _, values := range []map[string]string{
		{},
		{tokenEnv: token},
		{clusterEnv: "7679"},
		{tokenEnv: token, clusterEnv: "7679"},
		{tokenEnv: "short", clusterEnv: "7679", preexistEnv: "1"},
		{tokenEnv: token, clusterEnv: "7679", preexistEnv: "x"},
	} {
		if _, err := PolicyFromEnvironment(environment(values)); err == nil {
			t.Fatalf("policy accepted %v", values)
		}
	}
}

func TestRejections(t *testing.T) {
	policy, err := PolicyFromEnvironment(environment(map[string]string{
		tokenEnv: token, clusterEnv: "7679", protectedEnv: "7679:777", preexistEnv: "1,777,900",
		preparedEnv: "7679:900",
	}))
	if err != nil {
		t.Fatal(err)
	}
	marker, other, empty := Marker(token), Marker(strings.Repeat("b", 64)), ""
	owned := OwnedMarker(token)
	for _, check := range []struct {
		identity Identity
		reason   string
	}{
		{Identity{SystemIdentifier: "7679", OID: 1, Comment: &marker, SelfAuthoritative: true}, "authoritative"},
		{Identity{SystemIdentifier: "7679", OID: 777, Comment: &marker}, "protected"},
		{Identity{SystemIdentifier: "other", OID: 1, Comment: &marker}, "did not verify"},
		{Identity{SystemIdentifier: "7679", OID: 1}, "not marked"},
		{Identity{SystemIdentifier: "7679", OID: 1, Comment: &empty}, "not marked"},
		{Identity{SystemIdentifier: "7679", OID: 1, Comment: &other}, "not marked"},
		{Identity{SystemIdentifier: "7679", OID: 1, Comment: &marker}, ""},
		{Identity{SystemIdentifier: "7679", OID: 1, Comment: &owned}, ""},
		{Identity{SystemIdentifier: "7679", OID: 5000}, ""},
		{Identity{SystemIdentifier: "7679", OID: 5000, SelfAuthoritative: true}, "authoritative"},
		{Identity{SystemIdentifier: "7679", OID: 900, Comment: &marker, SelfAuthoritative: true}, ""},
		{Identity{SystemIdentifier: "7679", OID: 900, SelfAuthoritative: true}, "authoritative"},
		{Identity{SystemIdentifier: "7679", OID: 901, Comment: &marker, SelfAuthoritative: true}, "authoritative"},
	} {
		got := policy.Rejection(check.identity)
		if (check.reason == "") != (got == "") || !strings.Contains(got, check.reason) {
			t.Fatalf("%+v: got %q, want %q", check.identity, got, check.reason)
		}
	}
}

func TestMarkerMatchesPythonHarnessAndHidesToken(t *testing.T) {
	// sha256 of 64 "a" characters, as tests/integration/database_isolation.py derives it.
	want := markerPrefix + "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"
	if got := Marker(token); got != want || strings.Contains(got, token) {
		t.Fatalf("marker %q", got)
	}
}

func TestPythonPathPrependsGuardOnce(t *testing.T) {
	site := siteDirectory()
	if _, err := os.Stat(filepath.Join(site, "sitecustomize.py")); err != nil {
		t.Fatal(err)
	}
	path := PythonPath(PythonPath("/src"))
	if path != site+string(os.PathListSeparator)+"/src" {
		t.Fatalf("PYTHONPATH %q", path)
	}
}
