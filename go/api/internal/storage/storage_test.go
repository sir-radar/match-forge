package storage

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func testPolicy(root string) Policy {
	return Policy{DatabaseWarningBytes: 1 << 50, DatabaseCriticalBytes: 1 << 51, Roots: []RootPolicy{{root, "evidence", 1000, 2000}}, ReserveBytes: 100, WarningFreeBytes: 200, MaxEntries: 100, ScanSeconds: 10, IntervalSeconds: 3600, BackupIntervalSeconds: 86400, QuarantineSeconds: 86400}
}
func TestAdmissionPreservesRecoveryHeadroom(t *testing.T) {
	for _, test := range []struct {
		r  Reservation
		ok bool
	}{{Reservation{500, 1000, 400, 100}, true}, {Reservation{501, 1000, 400, 100}, false}, {Reservation{1, 100, 0, 100}, false}, {Reservation{0, 1000, 0, 100}, false}, {Reservation{1, 1000, -1, 100}, false}, {Reservation{1, 0, 1 << 62, 1 << 62}, false}} {
		if (test.r.Admit() == nil) != test.ok {
			t.Errorf("admission %+v", test)
		}
	}
}
func TestPoliciesRejectOverlapAndMissingRecoveryReserve(t *testing.T) {
	p := testPolicy(t.TempDir())
	if err := p.Validate(); err != nil {
		t.Fatal(err)
	}
	p.Roots = append(p.Roots, RootPolicy{filepath.Join(p.Roots[0].Path, "child"), "other", 1, 2})
	if p.Validate() == nil {
		t.Fatal("nested roots double count")
	}
	p = testPolicy(t.TempDir())
	p.ReserveBytes = 0
	if p.Validate() == nil {
		t.Fatal("missing recovery headroom accepted")
	}
}
func TestEligibilityFailsClosedOnEveryProtection(t *testing.T) {
	now := time.Now()
	past := now.Add(-time.Hour)
	future := now.Add(time.Hour)
	good := Resource{Owner: "job", Complete: true, RetainUntil: &past, RecoveryVerified: true, Reconstructable: true}
	if b := good.Eligibility(now); len(b) != 0 {
		t.Fatal(b)
	}
	cases := []Resource{good, good, good, good, good, good, good}
	cases[0].Protected = true
	cases[1].Owner = ""
	cases[2].Complete = false
	cases[3].References = 1
	cases[4].LeaseUntil = &future
	cases[5].RetainUntil = nil
	cases[6].RecoveryVerified = false
	for _, r := range cases {
		if len(r.Eligibility(now)) == 0 {
			t.Fatal("unsafe resource eligible", r)
		}
	}
}
func TestScannerReportsPartialMeasurementsAndNeverFollowsSymlinks(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "small"), []byte("abc"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "link")); err != nil {
		t.Fatal(err)
	}
	p := testPolicy(root)
	r := ScanRoot(context.Background(), p, p.Roots[0])
	if r.Complete || r.LogicalBytes != 3 || !r.Protected {
		t.Fatalf("unsafe scan %+v", r)
	}
	p.MaxEntries = 1
	r = ScanRoot(context.Background(), p, p.Roots[0])
	if r.Complete {
		t.Fatal("entry bound ignored")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r = ScanRoot(ctx, p, p.Roots[0])
	if r.Complete {
		t.Fatal("cancelled scan complete")
	}
}
func archiveFixture(t *testing.T) (string, string) {
	t.Helper()
	source := t.TempDir()
	out := filepath.Join(t.TempDir(), "archive")
	for _, name := range []string{"a.json", "b.json"} {
		if err := os.WriteFile(filepath.Join(source, name), bytes.Repeat([]byte("football evidence\n"), 1000), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	return source, out
}
func TestArchiveDeduplicatesAndRestoresExactBytes(t *testing.T) {
	source, out := archiveFixture(t)
	m, err := Pack(source, out, []string{"a.json", "b.json"}, time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if m.LogicalBytes != m.UniqueBytes*2 || m.PackedBytes >= m.UniqueBytes {
		t.Fatalf("no dedup/compression %+v", m)
	}
	destination := filepath.Join(t.TempDir(), "restored")
	if err = RestoreArchive(out, destination); err != nil {
		t.Fatal(err)
	}
	original, _ := os.ReadFile(filepath.Join(source, "a.json"))
	restored, _ := os.ReadFile(filepath.Join(destination, "b.json"))
	if !bytes.Equal(original, restored) {
		t.Fatal("round trip changed bytes")
	}
	if err = RestoreArchive(out, source); err == nil {
		t.Fatal("restore replaced originals")
	}
}
func TestArchiveRejectsTraversalSymlinksCorruptionAndDuplicatePaths(t *testing.T) {
	for _, name := range []string{"../outside", "/absolute", "a.json/../b.json", "a.json/"} {
		source, out := archiveFixture(t)
		if _, err := Pack(source, out, []string{name}, time.Now().Add(time.Hour)); err == nil {
			t.Error("unsafe name", name)
		}
	}
	source, out := archiveFixture(t)
	if err := os.Symlink("a.json", filepath.Join(source, "link")); err != nil {
		t.Fatal(err)
	}
	if _, err := Pack(source, out, []string{"link"}, time.Now().Add(time.Hour)); err == nil {
		t.Fatal("symlink archived")
	}
	if _, err := Pack(source, out, []string{"a.json", "a.json"}, time.Now().Add(time.Hour)); err == nil {
		t.Fatal("duplicate path archived")
	}
	if _, err := Pack(source, out, []string{"a.json"}, time.Now().Add(time.Hour)); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(out, "payload.tar.gz"), []byte("corrupt"), 0o600); err != nil {
		t.Fatal(err)
	}
	if VerifyArchive(out) == nil {
		t.Fatal("corrupt archive verified")
	}
}
func TestArchiveManifestCannotEscapeRestoreRoot(t *testing.T) {
	source, out := archiveFixture(t)
	m, err := Pack(source, out, []string{"a.json"}, time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	m.Files[0].Path = "../escape"
	payload, _ := json.Marshal(m)
	if err = os.WriteFile(filepath.Join(out, "manifest.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	if RestoreArchive(out, filepath.Join(t.TempDir(), "restore")) == nil {
		t.Fatal("malicious manifest accepted")
	}
}
func TestRehearsalEnvironmentRemovesRoutingOverrides(t *testing.T) {
	env := databaseEnvironment([]string{"PGDATABASE=operating", "PGSERVICE=operating", "DATABASE_URL=secret", "FOOTBALL_DATABASE_URL=secret", "KEEP=value"}, "postgresql://isolated/test")
	if len(env) != 3 || env[0] != "KEEP=value" {
		t.Fatal("unsafe child routing", env)
	}
}

func TestArchiveRetryDoesNotReplacePublishedBytes(t *testing.T) {
	source, out := archiveFixture(t)
	until := time.Now().Add(time.Hour)
	first, err := Pack(source, out, []string{"a.json", "b.json"}, until)
	if err != nil {
		t.Fatal(err)
	}
	second, err := Pack(source, out, []string{"a.json", "b.json"}, until)
	if err != nil {
		t.Fatal(err)
	}
	if first.PayloadSHA256 != second.PayloadSHA256 {
		t.Fatal("retry replaced archive")
	}
	var content bytes.Buffer
	if err = ReadArchive(out, "b.json", &content); err != nil {
		t.Fatal(err)
	}
	if int64(content.Len()) != first.Files[1].Size {
		t.Fatal("registered archive reader changed bytes")
	}
	if err = os.WriteFile(filepath.Join(source, "a.json"), []byte("new unique evidence"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err = Pack(source, out, []string{"a.json", "b.json"}, until); err == nil {
		t.Fatal("changed original silently replaced archive")
	}
}

func TestArchivePublicationRejectsConcurrentEmptyDestination(t *testing.T) {
	staging := t.TempDir()
	destination := filepath.Join(filepath.Dir(staging), "existing")
	if err := os.Mkdir(destination, 0o700); err != nil {
		t.Fatal(err)
	}
	before, err := os.Stat(destination)
	if err != nil {
		t.Fatal(err)
	}
	if err = publishArchive(staging, destination); !errors.Is(err, os.ErrExist) {
		t.Fatalf("expected existing destination rejection, got %v", err)
	}
	after, err := os.Stat(destination)
	if err != nil || !os.SameFile(before, after) {
		t.Fatalf("existing directory identity changed: %v", err)
	}
}
func TestArchiveCapacityAndPermissionFailuresPreserveOriginals(t *testing.T) {
	source, out := archiveFixture(t)
	p := testPolicy(source)
	if AdmitArchive(p, source, out, []string{"a.json"}) == nil {
		t.Fatal("unmanaged destination admitted")
	}
	parent := t.TempDir()
	locked := filepath.Join(parent, "locked")
	if err := os.Mkdir(locked, 0o500); err != nil {
		t.Fatal(err)
	}
	defer os.Chmod(locked, 0o700)
	if _, err := Pack(source, filepath.Join(locked, "archive"), []string{"a.json"}, time.Now().Add(time.Hour)); err == nil {
		t.Fatal("permission failure hidden")
	}
	if _, err := os.Stat(filepath.Join(source, "a.json")); err != nil {
		t.Fatal("original lost after failure", err)
	}
}
func TestLifecycleQuarantinePlanRequiresAllProofAndGrace(t *testing.T) {
	now := time.Now()
	past := now.Add(-time.Hour)
	r := Resource{ID: "resource", Owner: "job", Complete: true, RetainUntil: &past, RecoveryVerified: true, Reconstructable: true}
	planned := PlanLifecycle([]Resource{r}, now, 24*time.Hour)
	if planned[0].Action != "QUARANTINE_REVIEW_REQUIRED" || !planned[0].EarliestDeletionAt.Equal(now.Add(24*time.Hour)) {
		t.Fatal(planned)
	}
	r.Protected = true
	planned = PlanLifecycle([]Resource{r}, now, 24*time.Hour)
	if planned[0].Action != "PRESERVE" || planned[0].ExpectedPhysicalSavings != nil {
		t.Fatal("protected resource received deletion/savings permission")
	}
}

func TestArchiveRejectsInvalidGzipFooterEvenWithMatchingPayloadDigest(t *testing.T) {
	source, out := archiveFixture(t)
	m, err := Pack(source, out, []string{"a.json"}, time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	payload, err := os.ReadFile(filepath.Join(out, "payload.tar.gz"))
	if err != nil {
		t.Fatal(err)
	}
	payload[len(payload)-8] ^= 0xff
	if err = os.WriteFile(filepath.Join(out, "payload.tar.gz"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(payload)
	m.PayloadSHA256 = hex.EncodeToString(sum[:])
	manifest, _ := json.Marshal(m)
	if err = os.WriteFile(filepath.Join(out, "manifest.json"), manifest, 0o600); err != nil {
		t.Fatal(err)
	}
	if VerifyArchive(out) == nil {
		t.Fatal("gzip checksum failure was hidden by tar EOF")
	}
}
