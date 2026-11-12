# Storage protection — 11 November 2026

P0: **PASS_WITH_WARNINGS**. The audit, temporary integration backup and supporting
recovery evidence now have verified independent encrypted external copies.
**The lifecycle system is not implemented. P1–P6 remain pending.** This is the
owner handoff required by AGENTS.md section 5 after a phase gate.

The [original audit](https://github.com/sir-radar/match-forge/pull/192), commit
`a6655648365d031ea965bb67a8df21a730d59293`, remains unchanged. It was already committed
when this task started; its worktree was clean. The refined owner request's P0–P6
order takes precedence over the earlier prompt's phase order. The complete earlier
prompt is retained outside Git, SHA-256 `9bb389a103d1b06587d9449f9a73b462e2c1d4662633bc84865b9c910cad14e0`.

## Protection performed

Existing `capture_files`, `verify_files`, `BackupConfig`, `Restic`, recovery
inventory and restore checks were reused. No new registry, scheduler or service
was introduced. This task removed no original database, worktree, backup or evidence.
No operating database writes, migrations, source acquisition or model changes ran.

- Primary capture: 83 files, 2,477,474,141 bytes. Includes the
  complete audit directory, all 54 files in the temporary v4 backup directory,
  integration evidence, original recovery gap manifest and prior receipt.
- Supplemental capture: 116 files, 271,396,177 bytes. Includes
  all four audit scratch JSON files, original v4 restore scripts/results and the
  previous missing-dependency investigation, including archive and historical DB searches.
- Verification records: final receipts, manifests, runners, original requirements,
  reconciled inventory, recovered code bytes and local task trackers are encrypted
  separately. Large generated artifacts are not added to Git.
- Both data captures passed `restic check --read-data`, `restore --verify`, exact
  manifest-hash comparison and verification of every restored file. The final
  small verification-record capture passed independent readback and file hashing.

The temporary dump is unchanged at
`/private/tmp/matchforge-v4-post-remediation-integration/.local/v4-integration/backup/database.dump`:
1,847,231,178 bytes, SHA-256
`375c5d9daee0ec97b1e124441950850ac8d2c68931cae89eaab57995ff4fcacd`.
Its companion row hashes and manifests are preserved too. Tracked consumers include
`docs/evidence/v4-post-remediation-integration.json`, its Markdown report,
`docs/recovery-cleanup-proposal.md`, the architecture storage/recovery report and
`docs/project-status.json`. Untracked restore scripts and receipts were included
rather than treating the dump as an independent file. The retained experimental
`football_v4_integration_20261110` database remains protected: the pre-change dump
does not prove that all later rehearsal changes are recoverable.

## Independent restore results

The v4 dump was read from the external readback, then restored into a new PostgreSQL
container using the operating image, with no network. All 49 recorded table
hashes (9,370,649 rows), the historical eligibility result
(314,876 rows) and the exact migration history matched.
Only this task's disposable container and its volume were removed after the drill.

The latest pre-existing external operating snapshot selected by the drill, `64e8a642186d3dd3f9572251bcb4150c24649c93bcf8d3961c67e4431749d782`,
was captured at 02:47:09 UTC and independently verified at 15:16:18 UTC on
11 November 2026. It passed the existing isolated database/file restore:
137 relation hashes, 2 historical cutoffs, restored dependency
inventory and artifact-reader outcomes. Status: `PASS_RECOVERABLE`,
`full_recovery: false`, 159 declared unavailable dependencies. Its newly created
restore database and temporary readback/restore directories were removed. The
existing backups and earlier restore evidence were retained.

## Recovery gaps and current backup configuration

The read-only inventory observed at 14:33:01 UTC on 11 November initially found
160 gaps: the original 159 plus a
historical `python/football/src/football/product/domain.py` checksum mismatch.
Exact original bytes were recovered from Git commit
`13fe3eb7684b6ce09e87592a28be91db657674ca`, SHA-256
`020a24b618d287c878f4eea1447bef3083d500b3afce770221b852e70956e3ad`.
The operating file was not changed. The new inventory points to that verified
retained copy and returns to the original 159-gap digest:
`5043306f0e0c58ce609018f8de300b9d1002615228c82cd3ba987db7dea6b92d`.

The previous investigation searched 41 databases and 100 archives; its detailed
results are externally preserved. Exact inline-byte searches of the two newer
P02 rehearsal databases found no matching missing originals, with no query errors.
Their metadata and idle status were not treated as deletion eligibility.

FULL_RECOVERY is **not achievable with the currently verified bytes and registrations**.
Thirty-one registrations require one- or two-byte originals with digests that
match none of the 256 one-byte or 65,536 two-byte values; that proof was rerun.
They need separately governed registration correction, not fabricated files.
Other missing originals remain unresolved. No historical registration or existing
159-gap manifest was changed. The original gap manifest's SHA-256 remains
`3e00dfee7464d1bad57c68820b169a76302ae7cdde5452da85fb9c72a1413a8c`.

The reconciled inventory is prepared at
`<repo>/.local/storage-protection/2026-11-11/reconciled-recovery-inventory.json`.
The operating `.env`, running services and configured inventory pointer were not
changed by this task. At the inventory observation, the old pointer lacked the
verified historical code locator. Recheck current registrations and adopt the
verified locator plan before the next backup; operations can add dependencies
after the observed inventory. Automatic backup
scheduling remains pending P5. These P0 evidence snapshots are not tagged as full
or recoverable operating backup points and do not reset the Admin backup reminder.

## Durable locations and retrieval

Protected local root: `<repo>/.local/storage-protection/2026-11-11/` (owner-only).
The local copies are supplementary; external verification used the enrolled drive
and existing current-user Keychain configuration. The external filesystem is exFAT;
the Restic v2 repository supplies encryption. Repository ID:
`44aa85e3bbbf737d5852d9b7666ca84d8260b8027e318b32067d278878d4c0b8`. Volume UUID: `988F99A7-D7C1-329C-9AFF-941D5D8B934C`.

| Contents | Snapshot | Snapshot directory |
| --- | --- | --- |
| Audit and v4 backup | `b0cc2b859548374be950d5a2daf4b27b3d2ea72f704664ce139915e6d397c15a` | `<repo>/.local/storage-protection/2026-11-11/payload` |
| Scratch and prior investigation | `0a1122d83cc8a2543f7d74f05c985ef2d889c4c2bce3f55a3d686f32b91538c0` | `<repo>/.local/storage-protection/2026-11-11/supplement` |
| Verification records | `d05c5e8a9d7d4be0261ad8cc6e84333f56e1dce8d51dd7188ccb275cf414d958` | `<repo>/.local/storage-protection/2026-11-11/verification-records` |

`<repo>` in snapshot directories means the exact original absolute directory
`/Users/radar/Desktop/football-simutation`, regardless of the checkout used later.
Follow [recovery credential setup](../recovery.md), authenticate the enrolled
repository and restore the selected `SNAPSHOT:ABSOLUTE_DIRECTORY` to a new empty
durable destination with `restic restore --verify`. Then run
`scripts.recovery_files.verify_files(destination)`, require an empty failure list,
and compare the manifest hash
against the [evidence record](../evidence/storage-protection-2026-11-11.json).
Never restore over operating data or use `latest` without selecting the intended
snapshot scope. Original filenames and provenance remain in `recovery-files.json`.
These steps follow [Restic 0.19.1 repository checking](https://github.com/restic/restic/blob/v0.19.1/doc/045_working_with_repos.rst)
and [restore documentation](https://github.com/restic/restic/blob/v0.19.1/doc/050_restore.rst).

## Capacity and savings

| Measurement | Before P0 | After P0 |
| --- | ---: | ---: |
| This task's retained local protection files, allocated at handoff measurement | 0 | 2,761,007,104 bytes |
| This task's new external packed bytes | 0 | 2,216,585,000 bytes |
| Existing-resource reclamation | 0 | **0 bytes** |

Protection deliberately adds independent copies. Internal restoration admission
required 98,494,765,072 bytes against a measured 201,545,572,352 available bytes;
VM capacity was separately checked during the v4 restore. Temporary restore
storage was released deterministically. New retained protection data needs P1
accounting and P2 registration; it is protected recovery evidence.

The audit's approximately 318 GB (308 GB clone-adjusted), 25.4 GB operating data
and 139.5 GB leftover databases remain dated baseline observations. The whole
environment was not walked again while other tasks were writing. No 31 GB or
215 GB reclamation estimate is reported as actual savings; APFS/Docker/DB totals
are not added together. Per-file allocation does not prove unique physical extents.

## Rollback and failure handling

No operating data or configuration was changed, so no operating rollback is
required. Original sources, earlier snapshots and both protected captures remain
available if any new copy fails. Recover to a new isolated location using the
selected snapshot and original-byte manifests. Reverting these documentation and
status changes does not authorize removing a capture or restoring over live data.

## Verification and handoff

- Focused recovery and encrypted Restic integration tests: **27 passed**.
- Real external checks, full file readbacks and both isolated restore drills: **PASS**
  within their declared scopes. FULL_RECOVERY remains blocked.
- `make format-check lint`: **PASS** (configured formatting, lint, strict types,
  static analysis, migration validation and shell syntax). Shared pinned tools and
  caches were reused; no duplicate dependency environment was installed.
- `make project-status-check`: **PASS** (`ProjectStatusV2 valid`).
- Compact evidence assertions and `git diff --check`: **PASS**.
- Original temporary dump and gap-manifest hashes were rechecked before delivery.
  The two exact disposable restore targets were confirmed absent.
- No production code, SQL schema, frontend or configuration changed. No new test
  resource remains. No cleanup or maintenance execution is authorized by this report.

P1 is next: verify an exact resource-by-resource reclamation manifest and obtain
resource-specific owner approval before deletion. P2–P6 still require implementation
of the registry, admission controls, evidence readers/packing, no-op update guards,
Admin interface, orchestration, budgets, quarantine and final lifecycle tests.
The original prompt's requirements remain part of those phases.

Keep the dedicated task worktree until its PR is merged. Its ignored task records
and original prompt are independently preserved with the verification records;
shared pinned tools are linked rather than copied. Before removing the worktree,
recheck local changes, untracked/ignored unique files and remote commit coverage.
No other worktree or branch is approved for removal.
