# MatchForge environment storage audit — 11 November 2026

Read-only investigation. Nothing was deleted, moved, pruned, vacuumed, restarted or
reconfigured. The only writes are this directory and scratch output outside the
repository. This is a dated observation, not a cleanup authorization; every
reclamation figure below is a proposal that needs an owner decision.

`<repo>` is the main checkout on the owner's machine. GB means
10^9 bytes. "Allocated" is `st_blocks × 512`; "logical" is `st_size`.

## 1. Answer

MatchForge occupies about **318 GB** of the internal disk (about 308 GB after
correcting for APFS clones), which is 45% of the 714 GB Data volume. Football data
is a small part of it:

| What | Size | Share |
| --- | ---: | ---: |
| Live operating data: `football` database (14.2 GB) and `.local/football-data` (11.1 GB) | 25.4 GB | 8% |
| **40 leftover rehearsal, restore and shadow databases** in the same PostgreSQL cluster | **139.5 GB** | 44% |
| **Task evidence, reports, pre-change dumps and restore output** under `<repo>/.local` | **about 131 GB** | 41% |
| Worktrees, caches and build output (in the repository and in `/private/tmp`) | about 22 GB | 7% |

The premise "the database is about 20 GB" is true only of the operating database.
The PostgreSQL volume is **154.8 GB** because every restore rehearsal since
14 October left its database behind.

Growth is not driven by ingestion. Between the 10 November inventory
([storage-recovery.md](../../architecture/unified-redesign-2026-11-10/storage-recovery.md))
and this audit, about 31 hours apart:

| Layer | 10 Nov | 11 Nov | Change | Cause |
| --- | ---: | ---: | ---: | --- |
| All databases (`pg_database_size`) | 143.62 GB | 153.73 GB | +10.1 GB | `football_p02_rehearsal` 9.85 GB; operating DB +0.24 GB |
| `.local` allocated file bytes | 135.75 GB | 150.04 GB | +14.3 GB | `foundation/` 12.2 GB (restore output 9.8 GB), `review-gaps/` 1.25 GB, `p02-audit/` 0.43 GB |
| `.local/football-data` | 10.97 GB | 11.13 GB | +0.16 GB | Provider payloads |
| Free space in the APFS container | 262.76 GB | 226.56 GB | −36.2 GB | 24.4 GB explained above; the rest is outside MatchForge data (swap, other applications) |

So in that interval operating data grew by about 0.4 GB and task residue by about
24 GB. Over the 30 days from 12 October, provider payloads grew 0.19 GB per day on
average (5.59 GB), while surviving task files and leftover databases created in the
same period total about 265 GB.

## 2. Storage inventory and measurement boundaries

| Boundary | Allocated | Logical | Files | Source |
| --- | ---: | ---: | ---: | --- |
| APFS container `disk3` | 768.10 GB used of 994.66 GB; 226.56 GB free | | | `diskutil apfs list` |
| Data volume | 713.76 GB | | | same |
| Main checkout `<repo>` | 154.64 GB | 142.22 GB | 4,341,773 | full walk, 640 s, 0 errors |
| — of which `<repo>/.local` | 150.04 GB | 137.60 GB | 4,239,720 | same |
| — of which caches, builds, `.venv`, `web`, `target`, `.tools` | 4.5 GB | | | same |
| — of which Git objects | 0.02 GB | | | `git count-objects` |
| MatchForge directories in `/private/tmp` | 7.84 GB | 7.51 GB | 122,543 | walk, 0 errors |
| PostgreSQL volume `football-forecasting_postgres-data` | 154.8 GB | 153.73 GB (sum of 44 databases) | | `docker system df -v`, `pg_database_size` |
| Other MatchForge Docker volumes, images, layers, logs | 1.03 GB | | | `docker system df -v`, `docker logs` |
| **MatchForge on the internal disk** | **about 318 GB** | | | sum of the rows above, no overlap |
| External restic repository `/Volumes/NTC/MatchForgeBackup` | 4.22 GB | 24.46 GB captured | | 10 Nov receipt; drive not mounted |
| Shared developer toolchains in the home directory | 19.6 GB | | | `du -sk`; not exclusive to MatchForge |
| macOS swap volume | 28.99 GB | | | `diskutil`; 27.6 GB swap in use |
| Remaining Data-volume usage | about 375 GB | | | not MatchForge; not scanned |

Double-counting controls: hard-linked inodes are counted once (0.32 GB excluded);
symlinks are not followed; database sizes are reported inside the volume figure, not
added to it; `.local/data-status-remediation/populated/data` (9.99 GB) is an APFS
clone of `.local/football-data` and therefore inflates `du` without using disk,
which is why the corrected total is about 308 GB.

Per-category detail with owner, use, last modification, consumers, classification,
confidence, reclaimable space and risk: [evidence/inventory.tsv](evidence/inventory.tsv).
Every `.local` entry: [evidence/local-directories.tsv](evidence/local-directories.tsv).

### Classification summary

| Class | Size | Main members |
| --- | ---: | --- |
| 1 Essential operating | 25.5 GB | `football` DB, `.local/football-data`, Redis, source tree |
| 2 Protected recovery | about 23 GB local, 4.2 GB external | 20 pre-change dumps and SQL backups (22.9 GB, including `.local/backups`), backup receipts; external restic repository |
| 3 Protected reproducibility | about 88 GB | `remediation/matchforge-audit` 52.2 GB, `remediation/matchforge-architecture-v2` 25.0 GB, `shadow-v4` 8.8 GB, evaluation runs |
| 4 Regenerable | about 9 GB local, 19.6 GB shared | Go, uv and Cargo caches, `.venv`, `node_modules`, `.next`, images |
| 5 Potentially redundant | about 160 GB | 39 idle non-operating databases 129.6 GB, restore output 9.8 GB, cloned restore tree, proven duplicate files |
| 6 Abandoned or temporary | about 22 GB | `football_p02_rehearsal` (task still open) 9.9 GB, six worktrees of merged branches 10.9 GB, staging and benchmark leftovers |
| 7 Unknown ownership | 0.15 GB | `matchforge-global-audit-pg` container and anonymous volume, Sprint-1 prototype DB |

Classes 2 and 3 overlap physically with class 5 where a protected directory contains
proven duplicates; the inventory file assigns each directory once.

## 3. Top consumers

- 50 largest directories: [evidence/top50-directories.tsv](evidence/top50-directories.tsv)
- 50 largest files: [evidence/top50-files.tsv](evidence/top50-files.tsv)
- By extension: [evidence/extensions.tsv](evidence/extensions.tsv). JSON is 106.2 GB
  in 4,045,744 files; `.dump` is 20.2 GB in 19 files.

Largest items:

| Item | Allocated | Note |
| --- | ---: | --- |
| 8 `football_fr_*` databases | 68.3 GB | Each a full restored copy, 8.0–8.9 GB |
| `.local/remediation/matchforge-audit/phases/R3` | 52.1 GB | 1,858 files; 40.4 GB is 29 versions of two review reports |
| 14 `football_r3_*` databases | 29.5 GB | Seven are 3.9–4.4 GB copies |
| `.local/remediation/matchforge-architecture-v2` | 25.0 GB | 3,337,036 files |
| `football` (operating) | 14.2 GB | About 9.4 GB when restored fresh |
| `.local/foundation` | 12.2 GB | 9.8 GB is restore-rehearsal output |
| `.local/data-status-remediation` | 11.8 GB | 10.0 GB is an APFS clone |
| 2 `football_architecture_v2_*` databases | 11.4 GB | |
| `.local/football-data` | 11.1 GB | Operating data |
| `.local/forecast-readiness-execution` | 9.9 GB | Six full dumps |

## 4. Duplication analysis

### Proven

Method: every file of 1 MiB or more (9,091 files) was grouped by size, fingerprinted,
then fully hashed with SHA-256 (32.2 GB hashed). Physical sharing was tested by
comparing the first device extent of each copy (`F_LOG2PHYS`). Full list:
[evidence/exact-duplicates.tsv](evidence/exact-duplicates.tsv).

| Finding | Logical duplicate | Physically recoverable |
| --- | ---: | ---: |
| All exact-duplicate groups ≥ 1 MiB (2,497 groups) | 20.03 GB | 14.73 GB |
| — inside `remediation/matchforge-audit` (two 1.91 GB and two 1.32 GB reports stored twice, audit triplicates) | | 3.92 GB |
| — `operating-ntc-restore` large files vs live `football-data` and architecture-v2 | | 3.67 GB |
| — `shadow-v4` vs `architecture-v2` and `issue04` | | 2.66 GB |
| — StatsBomb raw snapshot copies in `phase3a-…` and `liga-f-recovery-…` vs `football-data/raw` | | 1.88 GB |
| — row-hash exports stored three times in architecture-v2 phases 0, 0-restore, 1 | | 0.94 GB |
| — `.venv`, `node_modules`, `target` and tool binaries across worktrees | | about 1.2 GB |
| `operating-ntc-restore/data` vs live `football-data` (all sizes): 115,297 of 115,316 files have the same path and size, 400 of 400 sampled hashes match, 0 shared extents | 8.36 GB | **8.65 GB** |
| `data-status-remediation/populated/data` vs live `football-data`: 112,092 of 112,092 files match and all share extents | 9.70 GB | **about 0** (APFS clone) |

The clone result matters in both directions: removing the cloned tree would free
almost nothing, and it currently costs almost nothing. Source:
[evidence/football-data-copies.json](evidence/football-data-copies.json).

Source registry duplication stays negligible: the 10 November inventory measured
24.4 MB of duplicate registered source content (0.32%).

### Possible, not proven

- **Databases.** The 8 `football_fr_*`, 7 large `football_r3_*`, `v4_integration`,
  `ds_populated` and `p02_rehearsal` databases are restored copies of the operating
  database at different moments, each followed by rehearsal changes. They are near
  duplicates of each other and of the dumps they came from. No row-level comparison
  was run, so the unique content of each is unknown.
- **R3 report versions.** `RETAINED_SEASON_TEAM_IDENTITY_REVIEW.json` exists in 15
  versions (24.2 GB) and `TEAM_IDENTITY_REVIEW.json` in 14 (16.2 GB), one per audit
  round. Only two pairs are byte-identical; the rest differ in size and were not
  diffed.
- **Small files.** The 4.3 million files under 1 MiB were not hashed individually,
  apart from the two tree comparisons above.
- **Dump chain.** 20 full dumps (22.9 GB) are successive states of one database;
  pg_dump custom format is already compressed (a 64 MiB sample compressed to 98.8%).

## 5. Root causes, ranked by measured impact

| # | Cause | Measured impact | Earliest responsible stage | Confidence | Severity |
| --- | --- | ---: | --- | --- | --- |
| 1 | Rehearsal, restore and shadow databases are created per task and never dropped | 139.5 GB in 40 databases; +9.9 GB on 11 Nov alone | Task step "restore the dump into a new dated database". `scripts/integration.sh`, `scripts/storage-integration.sh` and `scripts/backup_recovery.py` drop what they create; ad-hoc task databases have no teardown or registry | High | Critical |
| 2 | Audit reports are re-exported in full, uncompressed, on every round | 52.1 GB; 40.4 GB in 29 versions of two reports | R3 remediation report writer (13–20 Oct) | High | High |
| 3 | One JSON file per observation or decision | 3,683,731 files of 0.5–2 KiB use 15.1 GB; `architecture-v2/phase-4/artifacts` is 6.7 GB logical but 16.4 GB allocated | Architecture V2 phase-4 replay and shadow-v4 observation writers | High | High |
| 4 | A full pg_dump before each change, all kept on the internal disk | 22.9 GB in 20 files; four dumps (6.65 GB) within 13 hours on 9–10 Nov | Pre-change backup step in remediation and forecast-readiness tasks | High | Medium |
| 5 | Restore-rehearsal file output is kept after verification | 9.8 GB physical (`operating-ntc-restore`) | Backup foundation restore drill, 10 Nov | High | Medium |
| 6 | Worktrees with private `.venv`, `node_modules`, `target` and `.local` | 10.9 GB in six worktrees whose branches are 0 commits ahead of `origin/main` | Task setup; AGENTS.md asks for the existing checkout unless tasks run concurrently | High | Medium |
| 7 | Table and TOAST bloat in the operating database | 4.4–4.8 GB (operating 14.24 GB vs 9.4–9.9 GB freshly restored) | Sync writers that rewrite unchanged rows: `product_competitions` has 1,659 rows, 556,855 updates, 120 kB of live TOAST in a 2.39 GB TOAST relation | High | Medium |
| 8 | Provider payloads stored as uncompressed JSON | 5.65 GB, 0.19 GB per day | `OperationalStoreMixin._record_response` publishes raw bytes | High | Low today |
| 9 | No retention on caches, sync logs or temp staging | Caches 3.2 GB; 22,089 sync-run logs (0.09 GB); `/private/tmp` staging and caches 0.43 GB | Makefile caches, `admin_sync.go` log path, backup-status staging build | High | Low |

Answers to the specific growth questions:

- **Continuous writers:** the Go API sync runner and Python sync commands
  (`fotmob-sync`, `pitchapi-sync`, `refresh-public-reports`) were running. They add
  payloads, one log per run and database rows. This is the 0.19 GB per day.
- **Historical records duplicated during ingestion:** no. Payloads are content
  addressed; registry duplication is 0.32%.
- **Temporary files left after success:** yes, for task-level work (causes 1, 4, 5, 6).
  The pipeline's own staging (`storage/raw.py`, `storage/parquet.py`,
  `manual_backup.py`) cleans up; `.local/backup-staging` is empty.
- **Failed jobs:** one retained failed run
  (`pitchapi-…-transport-failed-20260928T105218Z`, 0.05 GB). Not material.
- **Worktrees and disposable databases remaining:** yes, causes 1 and 6.
- **Audit evidence without retention limits:** yes, causes 2 and 3. No limit exists.
- **Backups recapturing unchanged material:** local pg_dumps are always full
  (cause 4). The external restic repository deduplicates: 24.46 GB captured became
  3.97 GB packed.
- **Identical payloads in several subsystems:** yes for restore output and raw
  snapshot copies (section 4), 12.4 GB physical.
- **Compression missing:** yes for JSON evidence and payloads. zlib level 6 on the
  first 64 MiB reduced a 1.91 GB review report to 17.9% and the 1.50 GB
  dispositions JSONL to 18.9%. The 10 November study measured ZSTD-3 at 9.1% on
  operational JSON.
- **Lifecycle cleanup:** absent. No scheduler, timer or launch agent for cleanup or
  backup exists (`automatic_backups: false` in the 10 November receipt).
- **Forecast evaluation and model training:** not a driver. `football-data/models`
  is 0.44 GB, `forecasts` 0.04 GB, PitchAPI evaluation runs about 0.6 GB together.

Growth timeline from file creation times, surviving files only
([evidence/file-creation-by-week.tsv](evidence/file-creation-by-week.tsv)), and
database creation times ([evidence/postgres-cluster.txt](evidence/postgres-cluster.txt)):

| Week | Files created | Databases created | Event |
| --- | ---: | ---: | --- |
| 12–18 Oct | 61.3 GB | 40.9 GB | R3 remediation audit; architecture V2 phase 0 |
| 19–25 Oct | 24.7 GB | 0 | Architecture V2 phases 4 and 33 |
| 26 Oct–1 Nov | 9.9 GB | 0.1 GB | Shadow V4 |
| 2–8 Nov | 19.3 GB | 32.7 GB | Data-status remediation, forecast-readiness, recovery |
| 9–11 Nov | 12.7 GB | 63.0 GB | Forecast-readiness resume, V4 integration, backup foundation, P02 |

Restored and cloned trees inherit the creation time of their originals, so about
19 GB shown in earlier weeks was actually written on 2 and 10 November.

## 6. Reclamation opportunities

None of this is authorized. Figures are physical estimates and are not additive
with each other where noted.

### A. Reclaimable after verification only (about 31 GB)

| Item | Estimate | Prerequisite |
| --- | ---: | --- |
| `.local/foundation/operating-ntc-restore` | 9.8 GB | Keep `verification.json`; confirm the 19 files that exist only in the restore are the recorded moved originals |
| Worktrees of merged branches (three in `<repo>`, three in `/private/tmp`) | 8.4 GB | `git status` clean in each; first move `/private/tmp/matchforge-v4-post-remediation-integration/.local/v4-integration/backup` (2.48 GB) to durable storage |
| Byte-identical second copies inside `remediation/matchforge-audit` | 3.9 GB | Path consumers checked; one copy and its hash retained; independent backup exists |
| `.local/go-mod-cache`, `uv-cache`, `go-cache` | 3.1 GB | No build running; network or offline rebuild confirmed |
| Raw-snapshot and row-hash duplicate copies | 2.8 GB | Same as above |
| Shadow-v4 copies duplicated elsewhere | 2.7 GB | Retention decision for shadow-v4 |
| Benchmark, staging and cache leftovers | 0.9 GB | None beyond confirming no process uses them |

### B. Reclaimable after archival or migration (about 215 GB, of which about 4 GB overlaps A)

| Item | Estimate | Prerequisite |
| --- | ---: | --- |
| 39 idle non-operating databases | up to 129.6 GB | Per database: name its evidence consumers, take or locate a dump, verify a restore from it, store the dump off the internal disk, then drop |
| `football_p02_rehearsal` | 9.9 GB | P02 task closed |
| Compress and archive R3 JSON evidence | about 39 GB | Lossless container with verified byte-exact round trip; sample ratio 18%, not yet measured on all files |
| Pack `architecture-v2/phase-4/artifacts` and other one-record trees | about 14–15 GB | Same; readers that expect individual paths updated or the tree declared cold |
| Move all but the newest two verified dumps to external storage | about 19 GB | External drive mounted, restic check passed |
| Rewrite bloated operating tables | 4.4–4.8 GB | Maintenance window and backup; exclusive locks during `VACUUM FULL`, or `pg_repack` |

### C. Long-term, from architectural changes

- Compress provider payloads at publication: about 90% of 0.19 GB per day, and about
  5 GB of the existing 5.65 GB if back-converted.
- A managed rehearsal-database lifecycle removes the largest growth term entirely.
  At the 9–11 November pace it was 63 GB in three days.
- Skipping no-op updates stops TOAST and index bloat from re-forming after a rewrite.
- Shared dependency caches across worktrees save about 1.7 GB per worktree.

Cost comparison:

| Measure | Saving | CPU, memory, I/O | Complexity | Recovery risk |
| --- | --- | --- | --- | --- |
| Drop archived rehearsal databases | Very high | Negligible | Low | Medium until each archive is restore-tested |
| zstd on new payloads and evidence | High on JSON | Low at level 3; read path decompresses | Medium: readers and manifests must accept the new representation | Low with original-byte hash retained |
| Pack small files | High | One sequential pass | Medium | Low with verified round trip |
| Content-addressed store with dedup | Low for sources (0.3%), high for restore output | Hashing cost | High | Low |
| Table rewrite | 4–5 GB | Heavy I/O, exclusive lock | Low | Low with a prior backup |
| Tiered external archive | High | Copy time | Medium: needs the drive present | Medium: single external device |

## 7. Data-protection risks found

1. **A cited backup lives in `/private/tmp`.** The 1,847,231,178-byte dump recorded in
   `docs/evidence/v4-post-remediation-integration.json` is at
   `/private/tmp/matchforge-v4-post-remediation-integration/.local/v4-integration/backup/database.dump`.
   No second copy was found in the repository. `/private/tmp` is not durable.
2. **Every local recovery point shares one disk with the operating database.** All
   20 dumps and all 40 restored databases are in the same APFS container.
3. **One external snapshot, drive absent.** The 10 November restic capture is
   `RECOVERABLE_ONLY`, `full_recovery: false`, with 159 unavailable dependencies,
   22 datasets and 26 model artifacts reported missing. `/Volumes/NTC` is not
   mounted, and no automatic backup exists.
4. **The Docker volume has no host-level protection.** OrbStack is configured with
   `data_allow_backup: false`; there are no APFS or Time Machine local snapshots.
5. **Headroom.** 226.6 GB is free. 9–11 November added about 76 GB in three days
   (63.0 GB of databases, 12.7 GB of files); at that pace the free space lasts about
   nine days. The operating database also wrote 929 GB of temporary files cumulatively
   (55,403 files), so transient peaks need headroom too.
6. **Clone coupling.** `populated/data` shares blocks with live `football-data`.
   Rewriting live files in place (for example compressing them) would make both
   copies consume space.
7. **Evidence that may be the only original.** `docs/recovery-cleanup-proposal.md`
   already notes that old dumps may hold the only original bytes for missing-source
   cases. Nothing here contradicts that.

## 8. Storage lifecycle blueprint

Compatible with the proposal in
[storage-recovery.md](../../architecture/unified-redesign-2026-11-10/storage-recovery.md)
and its five classes (TEMPORARY, OPERATIONAL, REGENERABLE, ARCHIVABLE, PROTECTED).
It reuses the work orchestration tables (`football.work_items`, migration
`202610180700`), the manual backup work type (`202611100300`),
`scripts/backup_recovery.py`, restic, `ImmutableFileStore` and the Admin backup
status page. No new scheduler or storage engine.

1. **Storage registry.** One table recording every task-created resource: kind
   (database, worktree, dump, evidence directory, restore output), exact identifier,
   owning task or branch, lifecycle class, created time, review-by time, consumers,
   and the verified archive that covers it. Nothing is created outside it.
2. **Single entry point for rehearsal databases.** Extend
   `scripts/backup_recovery.py` (it already creates and drops databases) so every
   rehearsal database is registered, named by convention, limited by count and total
   bytes, and torn down or archived at task close. A task that needs to keep one
   states why in the registry.
3. **Daily inventory job.** A work item that records `pg_database_size` per
   database, `docker system df`, free bytes and bounded `du` of registered roots
   into a time-series table. This gives the growth slope the 10 November document
   could not compute. The full four-million-file walk stays a monthly job.
4. **Evidence writer rules.** New evidence is written compressed (zstd) with the
   original-byte SHA-256 in its manifest; round N of a report stores only what
   changed from round N−1 or a reference to the unchanged file; per-record output
   goes to JSONL or Parquet, not one file per record.
5. **Archive tier.** Dumps beyond the newest two verified points, closed-task
   evidence and archived rehearsal dumps go to the external restic repository. Local
   eviction happens only after `restic check` and a sampled restore, recorded in the
   registry.
6. **Dry-run planner and approval.** A weekly job lists registry entries past their
   review-by time with size, consumers and covering archive. It deletes nothing.
   The owner approves per entry; the executor rechecks references immediately
   before acting, as the existing design requires.
7. **Admission by free bytes.** Before a restore, dump or large acquisition, compare
   projected peak with measured free bytes minus a reserve. Refuse visibly instead
   of filling the disk.
8. **Worktree and cache hygiene.** One worktree parent inside the repository, never
   `/private/tmp`; shared `UV_CACHE_DIR`, pnpm store and `CARGO_TARGET_DIR`;
   worktrees registered like any other resource.
9. **Database hygiene.** Guard sync updates with `IS DISTINCT FROM` so unchanged
   rows are not rewritten; add a bloat report (live bytes vs relation bytes) to the
   daily inventory; schedule rewrites in a maintenance window when the ratio
   exceeds an agreed threshold.
10. **Payload compression.** Add a compressed representation to the immutable store
    with representation metadata as already designed; keep readers for the old one.

### Prioritized plan

| Step | Content | Depends on |
| --- | --- | --- |
| P0 | Protect: move the `/private/tmp` backup to durable storage; mount the external drive; take and verify a current external backup | Owner go-ahead |
| P1 | Decide retention for the 40 databases and the six worktrees using `inventory.tsv`; archive, verify, then drop what is approved (section 6A and the database row of 6B) | P0 |
| P2 | Storage registry, rehearsal-database entry point and daily inventory (items 1–3) | Authorization as a foundation task |
| P3 | Evidence writer rules, archive tier and dry-run planner (items 4–6); compress and pack existing R3 and architecture-v2 evidence | P2 |
| P4 | No-op update guards, table rewrite, payload compression (items 9–10) | P2; maintenance window |

## 9. Limits and remaining unknowns

This audit is **not exhaustive**. Reconciled: the main checkout, MatchForge paths in
`/private/tmp`, all Docker resources visible to the daemon, the PostgreSQL cluster.

Not reconciled:

- **OrbStack disk image on the host.** The data folder is blocked by macOS privacy
  controls (`Operation not permitted`). The VM reports 147 GiB used of 348 GiB; the
  sparse image on the host may be larger if freed blocks were not returned.
- **External drive.** `/Volumes/NTC` is not mounted. Its figures come from the
  10 November receipt.
- **Other worktrees' Git state.** This session is confined to its own worktree, so
  uncommitted changes in the other six worktrees were not checked.
- **Unique content of each leftover database** and whether each can be rebuilt from
  an existing dump.
- **Differences between the R3 report versions.**
- **Small-file duplication** outside the two tree comparisons.
- **APFS clones** are detected by first extent only; partially shared files are not.
- **About 375 GB of non-MatchForge usage** on the Data volume was deliberately not
  scanned. Shared toolchains (19.6 GB) are not attributed to MatchForge.
- **Why the `product_competitions` TOAST relation is not reused** despite 793
  autovacuum runs. The update count is measured; the vacuum behaviour is not
  explained.
- During the audit another session dropped `football_p02_dev` (17.8 MB) and pushed a
  branch; the cluster went from 45 to 44 databases between measurements.

## 10. Evidence

| File | Content |
| --- | --- |
| [evidence/inventory.tsv](evidence/inventory.tsv) | Classified inventory with all required attributes |
| [evidence/walk-summary.json](evidence/walk-summary.json) | Walk totals, method, size histogram, duplicate totals |
| [evidence/top50-directories.tsv](evidence/top50-directories.tsv), [evidence/top50-files.tsv](evidence/top50-files.tsv) | Largest consumers |
| [evidence/local-directories.tsv](evidence/local-directories.tsv) | Every entry under `.local` |
| [evidence/exact-duplicates.tsv](evidence/exact-duplicates.tsv) | 400 largest proven duplicate groups with hashes and extent counts |
| [evidence/football-data-copies.json](evidence/football-data-copies.json) | Live tree vs cloned and restored copies |
| [evidence/file-creation-by-week.tsv](evidence/file-creation-by-week.tsv), [evidence/extensions.tsv](evidence/extensions.tsv) | Timeline and file types |
| [evidence/postgres-cluster.txt](evidence/postgres-cluster.txt) | Databases, creation times, sizes, connections, settings, WAL |
| [evidence/postgres-football-relations.txt](evidence/postgres-football-relations.txt), [evidence/postgres-football-bloat.txt](evidence/postgres-football-bloat.txt) | Relation sizes, unused indexes, TOAST and update counts |
| [evidence/docker-system-df.txt](evidence/docker-system-df.txt) | Images, containers, volumes |
| [evidence/scripts/](evidence/scripts) | The read-only scripts and SQL used |
