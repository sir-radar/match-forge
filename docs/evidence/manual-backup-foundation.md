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
Actual USB disconnection/eject behavior remains hardware-pending. Physical device
capacity, encryption, key custody and independent password retention are unverified.
All seven new example settings were added to the existing ignored `.env` without
replacing local values; activation remains false and `.env` is never staged.

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
- Final focused recovery suite: four cases passed in 51.17 seconds. Two additional
  isolated reader cases passed in 4.22 seconds, proving valid dataset/model reads
  and rejection of corrupted restored artifacts. Unit tests reject operating-root
  restore destinations and insufficient space before creating destination files.
- Go/Python configured complexity and explicit new TypeScript complexity checks
  are at most 10. UI sections and boundary parsing have separate current consumers.
- Desktop Chromium and mobile WebKit journeys passed keyboard confirmation,
  cancellation, axe, 320-pixel reflow, text spacing, forced colors and reduced
  motion. Native button tab stops fixed the initially observed WebKit traversal
  problem. Screen-reader interaction and physical-drive testing remain unrun;
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

The final read-only release observation at 11:48:30 UTC still reports unknown
running commit/lock/worktree identity, latest migration `202611100100`, and pending
`202611100200` plus new `202611100300`. All routes remain LEGACY; no migration,
deployment, model promotion or cutover was performed. Operating DB measured
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
unverified. A connected 1 TB drive is not assumed from the owner's hardware choice.

The [separate cleanup proposal](../recovery-cleanup-proposal.md) identifies exact
duplicate reports, experimental DBs, old backups and caches with dependency,
recovery, risk and approval requirements. Both named report files still measure
1,913,464,815 bytes; none was deleted. Keep latest plus an earlier independently
verified point when capacity permits; sustainable additional retention awaits real
growth measurements. Automatic pruning remains disabled.

Next owner action: connect/enroll the actual drive, retain its independent key,
resolve the legacy locator/original-file blockers, approve the scoped operating
migration/activation and measure a full real backup/isolated restore. Only then
select a later roadmap cohort; P02 source-proven identity/score work is a candidate,
not authorization to begin it. The F0–F11 plan, Probability Filter, Rust engine and
current champion are unchanged.

Final aggregate and Git delivery: pending at this checkpoint; see subsequent
verification entry. Implementation readiness is distinct from operating activation.
