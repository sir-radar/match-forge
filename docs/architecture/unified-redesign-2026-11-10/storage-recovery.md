# Storage, archival, export and recovery design

Checkpoint I1. Measurements are dated observations; lifecycle/backup changes are
**PROPOSED, NOT IMPLEMENTED**. No file was deleted, rewritten, compressed in
place, archived for eviction, or restored over the operating database.

## Measured capacity and accounting

Host: 16 GiB RAM, 8 logical CPUs. `df -k .` reported 256,599,560 KiB available
(262.76 GB) and 73% filesystem utilization during one observation; a separate
sample differed while other processes ran. `diskutil apfs listSnapshots` reported
no snapshots for the inspected Data volume. This does not inspect every volume,
Docker VM filesystem or external backup disk.

`du -sk` reported `.local` 132,559,784 KiB. A subsequent no-symlink metadata walk
completed in **544.304 seconds**, with **4,036,851 files**, no errors,
123,786,349,952 logical bytes and 135,745,224,704 allocated file bytes.
Allocation is `st_blocks × 512`; directory blocks, hard-linked paths, APFS shared extents, sparse
VM allocation and concurrent writes prevent exact unique-physical-byte summing.
Receipt: `.local/unified-architecture-investigation/inventory.json`, SHA-256
`2497ab2521c81252ceef8276c32207a0b132699922f46850d7d3505887563a39`.

| Directory/category | Logical bytes | Allocated file bytes | Disposition |
| --- | ---: | ---: | --- |
| `.local/remediation` | 67,139,710,980 | 77,187,743,744 | Protected audit/V2/baseline/rehearsal evidence; inspect dependencies, not blanket TTL |
| `.local/data-status-remediation` | 11,467,611,761 | 11,751,071,744 | Recovery evidence, dumps and retained artifacts; not assumed disposable |
| `.local/forecast-readiness-execution` | 9,898,669,434 | 9,905,455,104 | Execution/recovery evidence |
| `.local/shadow-v4` | 7,871,513,034 | 8,767,426,560 | Experimental evidence; needs ownership/retention review |
| `.local/football-data/operational` | 5,300,601,439 | 5,515,472,896 | Provider payloads; preserve originals and source lineage |
| `.local/football-data/raw` | 4,183,663,651 | 4,189,556,736 | Registered source bytes; protected |
| `.local/backups` | 3,535,155,326 | 3,535,183,872 | Only 13 files here; backups elsewhere also count |
| `.local/football-data/models` | 422,702,925 | 444,018,688 | Immutable fitted artifacts and manifests |
| `.local/football-data/normalized` | 314,321,927 | 315,887,616 | Analytical datasets; existing Parquet compression |
| `.local/football-data/observations` | 13,595,607 | 50,446,336 | 12,310 small immutable observation artifacts |
| `.local/football-data/forecasts` | 6,229,571 | 40,845,312 | Stored file forecasts; not equal to every DB forecast registration |
| `.local/football-data/work` | 510,256 | 4,501,504 | 1,099 work files; live references must be checked |
| `.local/football-data/manifests` | 1,215,973 | 1,249,280 | Preserve integrity and snapshot references |

All `football-data/*` categories total 10,644,947,637 logical bytes and
10,968,510,464 allocated bytes across 129,111 files. Other recovery/acquisition,
report and cache directories explain the remainder of `.local`.

Across `.local`, file extensions include JSON 85,750,166,753 logical bytes,
19 `.dump` files totaling 20,237,090,623 bytes, gzip 3,140,730,070 bytes,
JSONL 1,839,545,569 bytes and Parquet 903,144,592 bytes. These overlap directory
categories and must not be added again. Logs/temp/failed work are mixed with
recovery evidence; extensions do not confer deletion authority.

Selected non-`.local` allocated directory measurements: `.git` 22,420 KiB,
`web/node_modules` 539,952 KiB, `web/.next` 239,840 KiB, `target` 942,052 KiB,
`.venv` 854,400 KiB, `.tools` 1,038,428 KiB and `data` 48 KiB. Build/test caches
also exist inside `.local`: Go modules 1,227,657,216 allocated bytes, uv
1,012,256,768 and Go build 463,523,840. They may be regenerable, subject to an
active-job lock and offline reconstruction requirements; no cleanup ran.

### PostgreSQL, WAL and Docker

| Layer | Observed bytes/size | Meaning |
| --- | ---: | --- |
| Operating `football` DB | 13,996,840,639 | `pg_database_size`, includes indexes/TOAST |
| All 41 non-template DBs | 143,619,336,807 | Operating plus experimental/restore/Postgres DBs; not new physical host usage |
| Largest experimental DB | `football_v4_integration_20261110`: 9,391,486,655 | Preserve until separately reviewed retention/restore dependencies allow retirement |
| WAL directory | 83,886,080 | Point-in-time retained WAL, not a growth rate |
| Docker local volumes | 145.7 GB; four total, three active | Includes PostgreSQL VM-layer storage; overlaps the DB sizes above |
| Docker images | 1.223 GB; three images | Reported reclaimable 415.3 MB is not authorization to remove pinned images |
| Docker containers/build cache | 213 kB / 0 B | Reported by `docker system df` |

Operating largest relations: `product_competitions` 2,634,547,200 bytes,
`product_provider_mapping_decisions` 2,268,741,632,
`event_observations` 2,069,118,976,
`product_provider_resource_observations` 1,409,835,008,
`product_read_reports` 1,118,445,568,
`fixture_identity_resolutions` 888,791,040. `product_competitions` has only 1,659
estimated live rows; inspect TOAST payloads, update patterns and physical bloat
before choosing maintenance. Do not infer reclaimable bytes from relation size.
`event_observations` statistics reported zero estimated live tuples, but an exact
count found **2,609,128** rows. Statistics are estimates, not evidence of emptiness
or a reason to delete the relation. No VACUUM FULL, REINDEX or schema operation ran.

There is no trustworthy single unique-physical MatchForge total: measured local
files/directories and Docker DB/volume layers are reported separately. Adding
Docker volume bytes to database bytes would double-count. A future daily inventory
must bind timestamps, roots and VM/APFS allocation semantics before claiming a
precise total or growth slope. No comparable storage time series was available;
recent net growth is **UNVERIFIED**.

## Compression and exact-content reuse

The [three-repeat sample experiment](research.md#compression-experiment) verifies
exact byte round trips. ZSTD-3 stored 9.12% of sampled operational JSON and 21.23%
of sampled CSV; Parquet retained 97.90% and gzip grew slightly. ZSTD-9 improves
JSON ratio at higher CPU cost. Existing `storage/parquet.py` uses ZSTD level 9.
Do not extrapolate sample ratios across 123.8 GB of mixed evidence or infer backup
savings from two dump prefixes.

Source registry metadata: 82,517 resource registrations, 80,540 distinct hashes,
7,551,788,395 registered bytes and 7,527,396,664 bytes after grouping exact hashes.
Thus **24,391,731 bytes** is the metadata-derived upper bound for duplicate
registered source contents, only about 0.323% of registered bytes. This does not
verify every referenced file, APFS unique extents or all unregistered report
copies. Two selected 1,913,464,815-byte remediation JSON reports were then streamed
through SHA-256: both equal
`472c519ecfc9a2592cba008500cd9c237c414211129c4c727c3e75ac3040ae31`.
The bounded 2.405-second check establishes 1,913,464,815 duplicate logical bytes
for that pair, separate from source-registry duplicates. It does not establish
unique physical extent savings or deletion eligibility. Private receipt:
`.local/unified-architecture-investigation/report-dedup.json`.

Proposed representation metadata extends existing artifact/source storage owners:
original byte SHA-256 and size, physical object SHA-256 and size, codec/version,
archive/object locator, source registration, representation status and verification
receipt. For raw sources, “original content” means exact original bytes, not
canonicalized JSON. Model/dataset logical state checksums remain distinct.
Preserve every acquisition/registration/time even when physical objects coincide.
No EAV football facts belong in representation metadata.

Write a new representation to an exclusive temporary path, stream/hash and fsync
as required by the current publication contract, atomically publish, decompress
and verify original bytes, then register the immutable representation. Race/retry
must converge to the same object or fail on conflict. Old paths/readers remain
supported throughout rollout. Current raw verifiers expect original bytes;
switching a file to `.zst` without reader/manifest compatibility would break them.
An interrupted write leaves unregistered bytes, not a passing archive record.

GC/eviction requires current references, active-reader/job/backup pins, retention
and provider constraints, approved disposition and a verified independent copy.
Recheck under ordered locks immediately before an authorized unlink. A crashed
or stale planner cannot delete by old reference counts. No filename-age policy,
symlink traversal, arbitrary configured-parent deletion or last-copy removal.

## Lifecycle, pressure and storage budgets

| Class | Real examples and eligibility | Proposed schedule / guard |
| --- | --- | --- |
| TEMPORARY | Completed extraction/staging files with proven no active input/reference | Cleanup after verified operation; interrupted/unknown ownership retained |
| OPERATIONAL | Logs, leases/checkpoints, active diagnostics | Bounded log rotation and evidence retention by exact owner; preserve failure receipts |
| REGENERABLE | Build caches and derived reports whose inputs/toolchain are retained | Optional weekly dry-run review; reconstruct sample before deletion, no active use |
| ARCHIVABLE | Cold immutable sources, old evidence/model candidates with accepted retention | Verify archive retrieval and independent backup before any local eviction |
| PROTECTED | Original sources, immutable forecasts/models, decisions, protected protocols/holdouts and required parity | No automatic removal without explicit contract/disposition and dependency-safe recovery |

Daily lightweight measurements and monthly deeper dependency audits are proposed;
weekly cleanup is dry-run-first and applies only to proven eligible objects.
Do not repeatedly walk four million files for each Admin page. Incrementally
index owned publication manifests and bounded changed paths in existing storage
metadata; reconcile periodically against actual files.

Use available **bytes**, not unvalidated 70/80/90 percent thresholds. Required
headroom is the maximum of authorized snapshot staging, full isolated restore
(DB + referenced files + temporary decompression), largest in-flight acquisition
and observed WAL/temp bursts, plus normal growth during the longest operation and
a measured owner-approved safety reserve. Not all terms were measured, so no
cleanup/admission threshold is declared accepted. One current-size operating DB
plus the prior 1,847,231,178-byte dump plus unique registered source contents
already implies about **23.37 GB** before models/other evidence, WAL, restoration
workspace and safety reserve. Source registrations are not the complete file set.

If projected peak exceeds verified headroom, pause new optional backfill,
compression, candidate fitting and extra shadow copies; preserve live/result
publication, current champion and recovery bytes within safe bounds. Disk-full
publication must fail visibly before partial registration, not delete protected
inputs to continue. Compare future scenarios symbolically using measured daily
net growth `g`: retained increment after `d` days is `d × g`, with backup/dedup
and working-copy multipliers measured separately. No historical growth rate or
future-provider volume is invented.

Cold storage may use compressed local objects, an external SSD or optional object
storage; routine offline serving must retain active model/input/read dependencies.
An offline archive results in an explicit unavailable dependency, not provider
refetch, fabricated replacement or corrupt checksum acceptance. Device/path moves
require locator verification, not original identity changes.

## Backup consistency and economical default

Reuse `capture_architecture_v2_baseline.py`: exported repeatable-read snapshot,
custom dump, full migration/checksum list, registrations, table hashes, historical
cutoffs and verified source-byte archive. Add complete **referenced-file** coverage
for observation/capability artifacts, analytical datasets, model state/manifests,
forecasts/evaluations, training/calibration/holdout/run artifacts and decisions.
Configuration export contains versions and secret references, not plaintext keys.
Secrets/backup decryption keys need separate restricted, recoverable storage.

File-before-DB immutable publication makes a DB snapshot a useful reference set:
copy exactly the files referenced by that snapshot and verify every hash. New
unregistered files after the snapshot are not required; they are not mistaken for
missing data. Pin the snapshot's dependencies against future GC/archival while
enumerating/copying; keep network/file copying outside publication locks. Snapshot
exporter must remain alive while pg_dump imports it. A missing registered file
makes the backup incomplete for full recovery even when the dump is valid.

Proposed default: existing consistent PostgreSQL custom dumps plus encrypted,
deduplicated file snapshots to owner-supplied external storage. Evaluate restic
0.19.1 in a later disposable pilot rather than implement custom encryption/chunk
storage. The MatchForge manifest remains the cross-store consistency contract;
a generic restic snapshot of a live database directory cannot replace pg_dump.
Retain dump identity, snapshot/cutoff, file closure and checksums, code/lock,
PostgreSQL/tool/codec versions, source rights, configuration references, destination
and COMPLETE/INCOMPLETE verification status. Do not recursively back up backup,
cache or unowned parent directories.

Daily opportunity and on-demand pre-change backups are a proposed starting
cadence; target RPO of at most one day applies only while the machine/destination
can execute and the complete verified chain meets it. Sleep/offline time makes
actual backup age visible; a timer tick is not a backup. Offsite replication is
optional and rights/price approved separately; an external disk is the economical
initial second failure domain. Do not claim 3-2-1 protection with copies on the
same internal disk. No paid destination or new credentials were provisioned.

Prefer changed-file deduplication after an initial snapshot; each logical snapshot
must still have a complete restore closure. Retain the latest verified good chain
and a previous independently verified chain before rotating anything. Actual
retention duration/count depends on measured growth, source restrictions and owner
recovery needs; no arbitrary deletion count is approved here. Interrupted or
wrong-key backups remain INCOMPLETE and cannot displace the last good copy.

WAL/PITR and PostgreSQL physical incremental backup are alternatives for a later
measured RPO need. They add base/version/WAL-chain operations and restore tests;
current snapshot dumps already meet the simpler prototype mechanism. Do not
install a WAL archive or restic scheduler under this investigation.

## Restore and export acceptance

Existing evidence is narrower than a full new disaster-recovery claim:
`docs/evidence/v4-post-remediation-integration.json` records a 10 November
05:07:56 UTC dump, 1,847,231,178 bytes, SHA-256
`375c5d9daee0ec97b1e124441950850ac8d2c68931cae89eaab57995ff4fcacd`, restored and
upgraded in isolation. Its 49 protected table hashes / 9,370,649 rows and 314,876
same-cutoff eligible results reproduced. It retains source/model gaps separately.
`make postgres-restore-test` proves disposable database recovery, not all original
source/model files, complete machine recovery, or an accepted RTO. No new full
operating restore drill was run in this investigation.

Proposed restore procedure:

1. Select a sealed backup, verify authorization, destination/key access, manifest,
   hashes, version compatibility, required migration/toolchain and free workspace.
2. Create a new guarded database and separate file root. Disable provider
   schedules, model fitting/promotion and external effects in the restored app.
3. Restore the exact dump; restore the complete referenced original file set,
   preserving paths/bytes and representation metadata. No operating overwrite.
4. Validate all applied versions/checksums, canonical/mapping decisions, table and
   historical-cutoff hashes, raw/dataset/model logical/physical integrity,
   forecast/evaluation/artifact links, holdout-spend state and lineage.
5. Treat restored leases/tokens as stale; fence old workers before any controlled
   resumption. Resume only bounded authorized work after owner adoption.
6. Reproduce approved non-protected forecast fixtures and smoke-test actual Go/
   Next reads; verify code/lock/DB/model/route provenance from running restored
   services. Record start/end time, peak disk/RAM and all missing dependencies.
7. Require explicit owner authorization for operating activation, with retained
   old DB/files/routes and recovery plan. Never overwrite an operating DB by
   default or claim a read-only preview is a restore.

P01/P17 must exercise corrupt dump/object, wrong encryption key, missing model or
source/manifest, interrupted copy, archive path traversal, disk-full, disconnected
external disk, incompatible version, restarted worker, partial restore and lost
host scenarios. RTO is measured from selected recovery start to verified usable
service, including file/key acquisition, not merely pg_restore time. No fixed RTO
is defensible before that full drill; owner accepts the measured target and
recovery trade-off. Periodic monthly isolated drills and drills before risky
migrations/evictions are proposed; they must not overlap active acquisition beyond
verified resource capacity.

Portable export is separate: SQL custom archive plus manifest for system
reconstruction; JSON for identities/decisions/config references; Parquet for
qualified analytical observations/features; CSV only for selected flat results
with IDs, units, periods, temporal bounds and provenance retained in a companion
manifest. A CSV cannot reconstruct a full system. Export filters apply source
retention/redistribution rights, privacy/minors rules and role authorization.
Restricted data stays local; no public redistribution was authorized. Admin
Storage and Backup & Recovery pages show actual measurements, last complete backup,
restore-test outcome, destination availability and dry-run consequences, with
SSR/paginated history and explicit separate confirmation for consequential restore.
