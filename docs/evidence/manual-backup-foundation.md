# Manual backup foundation implementation

Authorized scope: P00-01, P00-02, P01-01, P01-02 and manual Admin backup with
30-day reminders. Implementation branch: `ft/manual-backup-foundation`.
Operating activation, migrations, model changes, source acquisition, destructive
retention and cleanup remain unauthorized. No active Wayfinder map is involved.

## Planning handoff

All four investigation commits (`f86aec1`, `39a4b21`, `f254008`, `34a552f`)
are ancestors of main `01eed6c`, merged through
[PR #183](https://github.com/sir-radar/match-forge/pull/183). Existing baseline,
followup, final-read, correction and compression receipts and final aggregate log
match their recorded SHA-256 checksums. ADR 0005 now accepts Option B for the
owner-selected scope; the investigation's historical proposed text stays intact.
The companion F0–F11 plan and Probability Filter scope remain independent.

## P00-01 — operating release truth

Read-only observation: 10 November 2026, 10:33:54 UTC. Command:

```sh
set -a; . ./.env; set +a; . ./scripts/toolchain.sh
uv run --locked python -m scripts.foundation_release --output .local/foundation/release.json
```

- API is operating (`healthz=ok`, `readyz=ready`), but commit, lock checksum and
  worktree identity are `unknown`; version is `dev`. Deployed commit is unproven.
- PostgreSQL 18.6, database `football`; schema owners `football` and
  `pg_database_owner`. Extensions: btree_gist 1.8 and plpgsql 1.0.
- Latest applied migration: `202611100100`; `202611100200` is pending. No
  operating migration ran. Goose has versions, not applied historical SQL hashes;
  current repository checksums are captured without claiming historical parity.
- Runtime registry has zero registrations. 18,162 forecast records reference
  approved champion `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`
  across the existing baseline and rolling10 algorithms. The checked-in champion
  hash matches. No model or forecast changed.
- All 13 stage routes remain LEGACY. V2 code/test evidence is experimental,
  not operating adoption.
- FotMob and PitchAPI each have one running sync and a current provider lease.
  One historical-acquisition lease expired on 6 November; no reclaim was attempted.
  Operational scheduling is 30 seconds; history scheduling is disabled.
- Diagnostics use a repeatable-read, read-only transaction with statement/lock
  limits and rollback. HTTP GETs are separately timed observations.

Focused verification: two release/migration tests, Ruff and strict mypy passed.
The initial diagnostic was denied localhost access by the sandbox; the authorized
read-only retry passed. Full aggregate is deferred until final code changes.

## P00-02 — resource baseline and proposed budgets

Read-only sample started at 10:35:23 UTC. Private receipt:
`.local/foundation/resources.json`. It records `sysctl`, `vm_stat`, `ps`,
`docker stats --no-stream`, `shutil.disk_usage`, four bounded PostgreSQL queries
and five consecutive GETs for each path below. No load generator or provider
request ran. The final console summary failed to encode a PostgreSQL Decimal;
the JSON receipt had already been written successfully and was inspected directly.

| Measurement | Actual observation |
| --- | --- |
| Host | 17,179,869,184 bytes RAM; eight logical CPUs |
| Internal filesystem | 994,662,584,320 total; 263,648,190,464 free bytes |
| Operating DB | 14,027,781,823 bytes, including indexes/TOAST |
| WAL | 117,440,512 bytes; point sample, not a growth rate |
| PostgreSQL container | 2.71% sampled CPU; 287.3 MiB RAM |
| Redis container | 3.09% sampled CPU; 6.922 MiB RAM |
| DB activity | Two active, seven idle connections at observation |
| Temp counters | 52,225 files / 944,104,966,563 cumulative bytes; not simultaneous workspace |
| `/version` | 108 bytes; p50 0.694 ms, p95/p99 25.47 ms |
| Today's fixtures | 109,453 bytes; p50 16.83 ms, p95/p99 172.35 ms |
| Sync Admin | 63,599 bytes; p50 2,567.84 ms, p95/p99 4,134.36 ms |

Percentiles use nearest rank over only five samples; p95/p99 are the sample
maximum, not a production SLO. Concurrent existing workers affect these readings.
Database-wide block/transaction counters cannot attribute queries to a request;
per-request query counts and provider fairness latency remain UNVERIFIED. Current
workers and queue ages are retained in the release/resource receipts, without
claiming fairness from a point sample. Current Admin polling is 2.5 seconds while
active, 60 seconds idle and 120 seconds hidden; polling does not authorize backups.

Reuse the earlier 4,036,851-file inventory (SHA-256
`2497ab2521c81252ceef8276c32207a0b132699922f46850d7d3505887563a39`), not a new
recursive scan. Its 123.8 GB logical files, PostgreSQL and Docker populations
overlap; they are never summed into a recovery estimate. No comparable growth
time series exists. `/Volumes` contains only Macintosh HD and Recovery; external
drive capacity, filesystem, encryption and repository growth remain unverified.

Initial release proposals: one manual backup at a time, one pg_dump worker, two
Restic CPUs/readers, low process priority, and a 20% destination free-space
planning reserve. Preflight must include dump staging plus exact referenced file
sizes and independent restore workspace. No missing dependency may be omitted to
meet a budget. Peak RAM, full-scope backup/RTO and destination growth must be
measured before operating activation; these proposals are not passing targets.
Thirty-day manual backups cannot achieve the previously desired 24-hour RPO.

## P01-01 — snapshot and file recovery

The existing baseline command now supports `--complete-recovery`, reusing its
snapshot export, table digest and cutoff helpers. Recovery capture retains
database globals, a full dump, Git application archive and the exact registered
file set. Incomplete capture cannot become a passing recovery record. The old
baseline workflow remains compatible. Procedures and scope are in `docs/recovery.md`.

Executed focused checks: 19 baseline/file tests passed; Ruff formatting, lint and
complexity plus strict mypy passed for new recovery modules. The disposable
integration test passed in 14.19 seconds. It proves full table/migration and
historical-cutoff parity, original-source bytes after the source root is moved,
checksum corruption rejection, and isolated restoration. A separate networkless
PostgreSQL container replayed globals and the dump with original ownership;
only the test's own container/volumes and random databases were removed.

Earlier test failures exposed lost credentials in the restored connection,
a misclassified inline history column and PostgreSQL's temporary init-server
readiness. These were fixed directly; checks were not skipped or weakened.
The ordinary `verify-restore` drill deliberately does not apply global roles to
the existing cluster; fresh-cluster global restoration is a separate procedure.
No full operating backup or operating restore has run. Missing original sources,
unregistered custom roots and hardware verification remain fail-closed blockers.

## P01-02 — encrypted drive and manual Admin workflow

Implemented existing-work submission (`BACKUP` / `MANUAL_BACKUP`), explicit drive
enrollment, protected password-file/Keychain access, pinned Restic 0.19.1,
encrypted incremental snapshots, full read-back/checksum verification and verified
snapshot tags. UUID idempotency, existing bulk exclusion, lease checks, cancellation,
Origin/JSON/local Admin controls and process-group cleanup remain enforced. No
backup registry or scheduler was added. Migration `202611100300` is tested on
disposable databases only; normal operation does not require that migration or drive.

Admin `/admin/backup` provides server-rendered status, drive identity/capacity,
preflight and resource-impact confirmation, Back Up Now, progress/cancellation,
verification/error history, actual recovery-point age, 30-day due reminders,
new packed bytes/repository-file bytes and timed eject status. The reminder due
date uses successful verification; data-loss age uses the earlier database
snapshot time. Failure does not replace the previous good point or reset reminders.
Restore drills are explicit isolated operator commands; read-back restore errors
are displayed in backup history. No background macOS notification agent is enabled.

The documented enrollment never reformats, renames or erases a drive. It requires
the actual external volume UUID and authenticated repository ID, checks writable
filesystem/capacity, and uses an open directory descriptor for every repository
operation. A child changes to that pinned directory before executing Restic;
replacing the mount display path cannot redirect writes to internal storage.
Actual USB disconnection/eject behavior remains hardware-pending. A later read-only
drive observation is recorded below. The current-user Keychain entry is verified
nonempty without displaying or logging it. Restic uses `RESTIC_PASSWORD_COMMAND`;
the password is not copied into its environment. Independent key retention is
owner-promised, not yet attested. All seven example settings are present in the
ignored `.env`, preserving unrelated local values. NTC identity and the selected
Keychain service are configured; its existing enable flag is preserved. The
repository ID remains empty and recovery-key attestation false. Missing scope
dependencies and the pending migration still block activation. `.env` is never staged.

### Executed disposable evidence

- Restic 0.19.1 Homebrew Apple Silicon bottle checksum:
  `46e8a729f34715368444f8b7d4b6e99dca7ec575f7c677bba40bec71764c1dea`.
  GitHub downloads timed out; the checksum-verified Homebrew bottle succeeded.
- Initial technology pilot: 2,648,576 input bytes; 1,049,779 packed data bytes
  (about 60.4% reduction); unchanged second snapshot added zero data bytes in that
  relative-path pilot. Backup 0.767/0.692 seconds, full data check 0.722 seconds,
  restore 0.717 seconds. Exact bytes, wrong-key and corrupt-pack rejection passed.
  These are small fixture measurements, not operating capacity/savings promises.
- Actual wrapper tests use absolute payload paths and pinned directories. Parent
  directory metadata can add tree blobs; unchanged source files add zero data
  blobs. Snapshot metadata still consumes storage. No zero-growth claim is made.
- Full disposable capture/read-back/global-role/independent-application recovery
  test passed, including recovery from a different extracted application directory
  after the source data root moved. Later final aggregate measurements are recorded
  below; earlier focused whole-test durations included 42.65 and 49.06 seconds and
  must not be reported as operating RTOs.
- Shared-work integration proves bulk duplicate exclusion, live-lane independence,
  cancellation, same-request joining, failed-history preservation, old sync-list
  compatibility and pre-migration blocking. Generic retry cannot bypass preflight.
  Completion also validates verification fields against the submitted manual-backup
  work type, even if a child omits its backup marker. Valid generic sync behavior
  is preserved. Migration-200 regression tests stop at their exact target; their
  history/constraint/rollback assertions remain unchanged when migration 300 exists.
- Final focused recovery suite: four cases passed in 51.17 seconds. Two additional
  isolated reader cases passed in 4.22 seconds, proving valid dataset/model reads
  and rejection of corrupted restored artifacts. Unit tests reject operating-root
  restore destinations and insufficient space before creating destination files.
- Go/Python configured complexity and explicit new TypeScript complexity checks
  are at most 10. UI sections and boundary parsing have separate current consumers.
- Desktop Chromium and mobile WebKit journeys passed keyboard confirmation,
  cancellation, axe, 320-pixel reflow, text spacing, forced colors and reduced
  motion. Native button tab stops fixed the initially observed WebKit traversal
  problem. Screen-reader interaction and physical-drive write/disconnect tests remain unrun;
  no whole-site WCAG conformance claim is made.

### API/UI state coverage

| Resource/state | Intentional behavior and evidence |
| --- | --- |
| Empty / no recovery point | No invented date or size; due banner and empty history; component/shared fixture tests |
| Disabled / pending migration / disconnected / wrong drive / credentials | Explicit reason, disabled action and status retry; destination, Go HTTP and pre-migration DB tests |
| Slow / refresh / malformed / network failure | Keep previous valid status, show local error/retry; boundary/component tests; aborted navigation cannot publish a late response |
| Manual preflight / confirmation / duplicate / conflict | No automatic POST; explicit focus/confirmation, UUID replay and bulk exclusion; Go, component and real DB tests |
| Active / cancellation / verification failure | Existing phase/status polling and process-group cancellation; previous recovery point retained; Restic corruption/key tests and browser workflow |
| Verified / overdue / failed later attempt | Exact captured/verified clocks, 30-day boundary and retained good history; Go timing/database tests |
| Contract drift | Shared JSON fixture checked against JSON Schema, Go round-trip DTO and TypeScript parser in repository checks |

### Final operating limits and cleanup handoff

Read-only release observations at 11:48:30 and 14:55:35 UTC still report unknown
running commit/lock/worktree identity, latest migration `202611100100`, and pending
`202611100200` plus new `202611100300`. All routes remain LEGACY; no migration,
deployment, model promotion or cutover was performed. At 11:48, operating DB measured
14,036,047,551 bytes; source registry 82,650 rows / 7,566,375,177 registered bytes.
That source-byte sum overlaps other storage and is not a complete recovery size.

The operating recovery reference inspection is **BLOCKED**: at least one legacy
source resource lacks an unambiguous physical locator for its original hash.
Direct registered file-path columns showed zero checksum conflicts. Treating that
legacy manifest path as its different resource payload would invent a locator;
the implementation now rejects it explicitly. Its apparent repeated `a`/`c`
checksums are not authority to exclude it as a test. Resolve exact original-byte
locations or obtain an explicit evidence-backed scope decision. No registration,
source, historical identity or retired artifact was changed. Private receipts:
`.local/foundation/operating-recovery-scope.json`, `reference-conflicts.json` and
`reference-conflict-detail.json`; these are protected local diagnostics, not Git
deliverables. Exact full operating dataset size, complete original-file recovery,
external initial/incremental sizes, retention capacity and operating RTO remain
unverified.

At 14:53:17 UTC the newly connected `NTC` volume was inspected read-only:
external and writable, exFAT, 1,000,185,528,320 bytes capacity and
678,952,960,000 bytes free. Free space changed between observations; it is a point
sample, not reserved capacity. Stable volume UUID and mount metadata are retained
privately in `.local/foundation/external-drive.json`. Filesystem encryption is
unverified; mandatory Restic encryption is still required. No `MatchForgeBackup`
repository exists and no drive write was performed. The owner selected current-user
Keychain service `matchforge-restic-ntc`. Its nonempty entry passed a protected
read-only check. The complete essential scope still cannot be enumerated because
original-file dependencies are unresolved, so fit within available space with
reasonable headroom is **UNPROVEN**. Enrollment now uses the same scope estimator
as backup preflight and stays blocked. Independent key retention awaits attestation.
Private receipt: `.local/foundation/enrollment-preflight.json`. No reformat is
required or authorized.

The [separate cleanup proposal](../recovery-cleanup-proposal.md) identifies exact
duplicate reports, experimental DBs, old backups and caches with dependency,
recovery, risk and approval requirements. Both named report files still measure
1,913,464,815 bytes; none was deleted. Keep latest plus an earlier independently
verified point when capacity permits; sustainable additional retention awaits real
growth measurements. Automatic pruning remains disabled.

Next owner action: attest separate key retention, resolve capacity and enroll the drive,
resolve the legacy locator/original-file blockers, approve the scoped operating
migration/activation and measure a full real backup/isolated restore. Only then
select a later roadmap cohort; P02 source-proven identity/score work is a candidate,
not authorization to begin it. The F0–F11 plan, Probability Filter, Rust engine and
current champion are unchanged.

## Final verification and handoff

Implementation result: **PASS_WITH_WARNINGS**. Operating recovery acceptance:
**BLOCKED** by unresolved original-file scope/capacity and pending enrollment.
Implementation readiness is distinct from operating activation.

[Implementation PR #184](https://github.com/sir-radar/match-forge/pull/184)
targets main from `ft/manual-backup-foundation`. Checkpoints: ADR `e3169c2`,
P00-01 `06b0332`, P00-02 `fee996b`, P01-01 `6fb87ef`, P01-02/Admin `eec31e4`,
completion guard `1b12486`, owner Keychain/capacity requirements `c5324c7`.
The verified implementation commit is
`c5324c76b997f933b5a57939f9be62a4c9f8cece`.

Executed final aggregate:

```sh
env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATABASE_URL \
  -u FOOTBALL_DATA_ROOT VITEST_MAX_WORKERS=2 make check integration
```

**PASS**: formatting, Ruff/complexity, strict mypy, Clippy, Go vet/complexity lint,
migration validation, architecture boundaries, builds, project-status validation,
2,178 Python unit tests, 16 Rust tests, Go packages, 195 web tests and 982 reported
storage integration cases. The final PostgreSQL/Redis/Go API integration also passed.
Seven dependency NumPy deprecation warnings and one pre-existing frontend test-file
unused-variable warning remain. Earlier failed attempts are retained locally.
The final run bounds Vitest concurrency after an existing pagination test timed
out; its isolated case passed in 383 ms. Assertions/timeouts were not changed.
Protected final log SHA-256:
`79f7c7a5e378ae3a2dc5047f4d86c7d5f1c2a6ab57972df7c21f8676fc8bb53b`.

`cd web && pnpm exec playwright test e2e/backup.spec.ts`: two passed in 7.4 seconds.
The changed UI is unchanged by the later backend-only corrections. Keyboard,
cancellation, axe and responsive/media checks passed; no screen-reader conformance
claim is made. Keychain and enrollment guards pass focused tests, including no
directory creation for incomplete scope or insufficient capacity. The new duplicate
reference test failed before the fix and now retains known size requirements in
either order.

Final independently restored fixture (not the operating recovery scope):

| Measurement | Actual |
| --- | --- |
| Captured logical payload | 62,778,269 bytes |
| New packed data | 16,061,825 bytes |
| Repository files | 16,067,725 bytes |
| PostgreSQL dump / original source fixture | 902,235 / 24 bytes |
| Capture phase | 0.937 seconds |
| Isolated restore verification phase | 5.864 seconds |
| Global roles/ownership and extracted-application replay | PASS |

Packed data is about 74.4% below logical bytes for this fixture only. Real initial
and incremental sizes, sustainable retention and operating RTO remain unmeasured.
Private metric receipt: `.local/foundation/verified-fixture.json`.

Final read-only operating observation at 15:37:39 UTC still finds unknown release
identity, latest migration `202611100100`, pending 200/300, all routes LEGACY and
the unchanged champion. At 15:37:44 UTC, NTC identity/writability/exFAT remained
verified: 1,000,185,528,320 total and 679,785,791,488 free bytes. A 20% planning
reserve leaves 479,748,685,824 bytes for new backup data at that observation;
this does **not** establish that the unknown complete essential scope fits.
Test repositories, staging and receipts are on filesystems distinct from NTC.
No task drive write, enrollment, operating migration, deployment, acquisition,
promotion, protected deletion or automatic backup occurred. Separate recovery-key
retention remains owner-promised rather than attested. CI and final PR head status
are reported in the handoff; no merge is authorized.

## Owner-directed operating-scope recovery — in progress

The owner authorized continued original-location investigation, safe resolver fixes,
explicit missing-original declarations and a backup of every recoverable dependency.
No original evidence or registration is rewritten. The earlier implementation
verification remains historical; the expanded operating-recovery work is active.

A read-only inventory enumerated 193,532 reference rows and hashed 114,387 physical
objects. It retained 33 unresolved source locators and 236 initial physical issues
instead of stopping at the first error. These are issues to classify, not proof
that every file is missing. A single retained-storage search examined 4,132,248
files, hashing 11,376 targeted candidates; 154 copies matched 64 required hashes.
It found 19 moved evaluation reports. All 4,551 retained Git blobs were checked,
with no additional original-byte matches. Archive and historical DB tracing continue.

The resolver incorrectly treated 45 legacy Football-Data pathname identities and
one canonical acquisition-receipt logical digest as physical file hashes. The
legacy writer is visible before commit `55a7e35d`; the current provider evidence
reader explicitly distinguishes its logical digest from canonical bytes with a
trailing newline. These existing contracts now govern backup resolution. All 45
legacy raw resources passed exact registered SHA-256/size checks. Original CSV/ZIP
bytes, receipt bytes and immutable database identities remain unchanged. Focused
verification: 13 tests and strict typing passed for the resolver correction.

NTC directory enumeration currently times out despite readable mount metadata.
No repository is created until actual drive access, credentials and capacity pass.
The owner has been asked to check Finder/reconnect while independent work continues.

### Resolved inventory and recoverable-only preparation

The NTC directory-access issue cleared after macOS removable-volume authorization;
a bounded root read and the project-file search completed. No repair or reformat was
performed. The NTC search examined 7,503 files with no project-original matches.
A retained-archive search examined 100 project archives, 71,623 member entries and
79 candidate payloads, with no additional matches. Read-only tracing across 41
databases found no additional physical locations. Desktop, Documents, Downloads
and temporary-storage metadata searches examined another 137,563 files; one
permission-limited directory remains outside verified search coverage.

The corrected snapshot inventory at 20:39:56 UTC verified 115,083 unique files
(8,432,702,695 bytes) and recorded 159 unavailable dependencies. Nineteen moved
evaluation reports have exact retained checksum matches. Forty-five legacy raw
resources and the logical acquisition receipt now resolve using their established
contracts. Exact unavailable identifiers, hashes and registered paths are retained
in `operating-recovery-scope.json`; the count is dependencies, not necessarily
159 distinct original byte streams. Thirty-one dependencies have declared one- or
two-byte size/hash combinations that exhaustive enumeration proves impossible.
No registration is discarded because it resembles a fixture.

At 20:45:25 UTC, a fresh estimate included 115,116 available files because operating
acquisition continued. The unavailable-registration digest remained unchanged.
Database allocation plus referenced bytes and the application archive totalled
22,591,728,986 bytes. NTC had 679,785,529,344 free bytes; the estimate leaves about
657 GB free, above the existing 20% external reserve. Local staging/read-back/restore
allowance was conservatively four copies (90.4 GB) against 259.3 GB free. This fits
but is below the recommended 20% local-disk reserve after that allowance. Missing
originals prevent a complete-scope capacity or recovery guarantee.

The owner has now attested a separate secure password copy. Keychain remains the
password source; neither the password nor credential-bearing configuration is in
tracked evidence. No automatic backups are enabled. The expanded fixture passed
capture, encrypted Restic backup, read-back, isolated restore and exact gap matching;
strict full-scope verification and full-scope tags reject this partial result.
Operating execution still awaits final code verification and interface authorization.

Implementation research: [Restic 0.19.1 data verification](https://restic.readthedocs.io/en/stable/045_working_with_repos.html)
and [Python tar extraction rules](https://docs.python.org/3.13/library/tarfile.html).
Application replay accepts only validated relative regular files/directories and
rejects links; it does not rely solely on tar extraction filters.

The final binary-payload search checked 110 bytea columns across all 41 databases,
with no missing-hash matches and no query errors (44.7 seconds). macOS denied
Documents-directory access even for an escalated retry; no registered or historical
physical reference points there. This remains a stated search limitation. The owner
approved the one-time command-line backup and isolated restore, preserving the
Admin-only requirement for future backups. Operating migrations/deployment remain
unauthorized.

Final expanded aggregate: `env -u DATABASE_URL -u TEST_DATABASE_URL -u
FOOTBALL_DATABASE_URL -u FOOTBALL_DATA_ROOT VITEST_MAX_WORKERS=2 make check integration`
passed (exit 0). All configured formatting, lint, strict typing, complexity,
architecture, unit, build, project-status, web and storage/API integration checks
passed. Log raw-byte SHA-256: `fa180adf267512c677d387c5c2acff43bd9f5db6b793d9845c0a333b0d977c98`. Existing dependency deprecations and the
unchanged frontend test-file lint warning remain. Source changes were frozen
throughout the run.
