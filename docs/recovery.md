# Recovery and integrity evidence

`IntegrityVerificationReportV1` is the machine-readable recovery record. It
keeps PostgreSQL backup and isolated restore evidence separate, and requires
both before the report can be `PASS`. It also records raw/object checksum
verification, dataset-manifest verification, model-artifact verification, and
forecast/evaluation registration integrity. Any failed check makes the report
`FAIL`; an unrun check keeps it `NOT_RUN`.

Reports bind a policy version, code Git SHA, and dependency-lock checksum. They
are evidence, not a backup implementation: operators must populate them from
an actual restore and integrity run, and historical artifacts remain immutable.

Recovery across providers follows the standing [research acquisition policy](source-acquisition.md#project-use-policy)
and its source-specific access register. Search retained resources before new
requests. New factual evidence cannot replace a missing checksum-registered
original or backdate a newly recovered observation. Use existing identity,
fixture and file-recovery owners for evidence-complete cases. Before cleanup,
check registrations, dependencies, retention and verified rollback bytes; retain
historical decisions, unresolved evidence and published model/source artifacts.

## Immutable byte verification

`football integrity raw <source_resource_id>`, `football integrity dataset <dataset_id>`,
and `football integrity model <model_artifact_id>` inspect only registered files beneath the
configured data root. Each command compares the stored SHA-256 and byte size with the actual file.
Dataset checks also compare its database registration, manifest, Parquet bytes, and logical checksum.
Model checks compare its registration, manifest, every registered file, and the portable model-state
checksum. A missing, unreadable, changed, or contradictory registration fails; the command never
repairs or changes stored data.

## Retained test-only forecast and evaluation lineage

`artifact_retirement_events` is append-only. It can retain approved synthetic forecast and
evaluation rows while excluding only their explicit IDs from the production hard-gate population.
It never changes forecast or evaluation bytes, artifact links, or dependency edges. Record approved
events with:

```text
football --code-commit-sha <git-sha> retire approved-test-forecast-lineage \
  --evidence-reference <decision-reference>

football --code-commit-sha <git-sha> retire approved-test-evaluation-lineage \
  --evidence-reference <decision-reference>
```

Then run `football integrity hard-gate`. Its output reports production failures separately from
retired forecast and evaluation physical failures, plus retained artifact-link and lineage counts.
No source kind, timestamp, missing-byte pattern, or other heuristic can exclude a forecast or
evaluation.

## Local PostgreSQL restore proof

Run `make postgres-restore-test` to prove local PostgreSQL recovery. It creates
a fresh integration source database, applies all migrations, writes only test
records, creates a PostgreSQL custom-format dump in temporary storage, and
restores that exact dump into a new `football_restore_test_*` database.

The test rejects source and restore databases outside their temporary namespaces
and rejects a restore target equal to its source. It checks the dump is non-empty and readable, then
compares migration state, required relations and constraints, registration
counts, selected IDs and checksums, append-only history, and fixture isolation.
It also proves a corrupt dump fails, a restored-only mutation is detected, and
the source manifest remains unchanged. The temporary dump and restore database
are removed after each run; neither database URLs nor passwords are emitted.

This is local recovery evidence only. It does not replace the separate
raw-file, dataset, model-artifact, or forecast/evaluation integrity checks, and
it is not a production disaster-recovery design.

## Complete snapshot-bound recovery capture

`scripts.capture_architecture_v2_baseline --complete-recovery --output <new-private-directory>
--data-root <operating-data-root>` extends the existing exported repeatable-read
snapshot mechanism. It captures a custom PostgreSQL dump, global roles/tablespaces,
all registered raw/manifests, datasets, models, observations, capabilities,
coverage, forecasts/evaluations, runtime model references and required retained
parity/recovery evidence. Every physical file reference has a relative root,
checksum, size and original modification time. Unknown file-reference columns,
contradictory registrations, absent originals, changed globals and symlinks fail
closed. Inline database records are preserved by the dump rather than exported
into a second registry. Sync diagnostic logs are excluded: run state, work leases,
decisions and summaries are authoritative database records, and the log reader is
not needed to reconstruct football facts or issued forecasts.

The private capture includes `application.tar` from the exact Git commit:
application code, migrations, schemas, locks and example configuration. Local
credentials are not included in that application archive. Retain separate database,
provider and backup credential recovery instructions; configure fresh credentials
after a disaster. Custom runtime artifact roots must be reconciled before capture;
the registry's repository-relative champion path uses the repository root.
Unregistered experimental runs/caches and unrelated `.local` directories are not
part of the selected operating recovery scope. Nothing is deleted.

`recovery.json` starts INCOMPLETE. CAPTURED means snapshot/file capture and
checksums completed, not that an external backup or restore drill passed.
Source files are copied without repair or rewriting. Raw files remain original
bytes; pg_dump is uncompressed so the encrypted destination can deduplicate and
compress its chunks. The exporter stays alive until pg_dump finishes. Global
metadata is checked before and after capture because pg_dumpall does not import
the database snapshot. Administrative role/tablespace changes must not run during
a capture. No GC/cleanup is enabled; a missing file interrupts capture.

For an explicitly requested drill:

```sh
uv run --locked python -m scripts.backup_recovery verify-restore \
  --capture <verified-capture> --destination <new-empty-directory>
```

This always creates a random `football_restore_test_*` database; it accepts no
operating target and removes only its own database afterward. It restores files
into new roots, compares every table's ordered row hashes and historical eligible
history cutoff, checks extensions and re-enumerates file references from the
restored database. It never runs globals against the existing cluster. The
destination must be outside both operating and captured source data roots, with
enough estimated space for the registered files and database. Restored datasets
and models must also pass their existing registered artifact readers. The
integration test separately replays globals and ownership into a new networkless
PostgreSQL container. Interrupted drills may leave a disposable database/root;
inspect their exact ownership before removing them. A failed/incomplete capture
or corrupt bytes cannot be used as passing recovery evidence.
When multiple registrations name one file, every known checksum and byte-size
requirement is retained regardless of registration order; deduplication cannot
discard a stricter requirement.

Thirty-day manual backups are the owner-selected policy. They may leave roughly
a month of changes without an external recovery point; they do not guarantee the
previously desired 24-hour RPO. Measure full operating restore time before adopting
an RTO. The current external drive and missing original-file dependencies must be
verified before claiming complete operating recovery.

## Manual encrypted external backups

Admin → **Backup & Recovery** is server-rendered through the existing private
local Admin boundary. **Back Up Now** performs read-only preflight, then presents
resource estimates and an explicit confirmation. The confirmed request uses a
UUID idempotency key and existing sync-run/shared-work leases, cancellation and
publication checks. Backup work shares the existing bulk exclusion lane; provider
live lanes remain independent. Older sync-list clients do not receive the new
backup enum; backup history has its own read endpoint over the same records.
No second work queue, backup registry or domain scheduler is introduced.

Activation defaults to disabled. Migration `202611100300` is additive and must
be rehearsed in disposable databases; applying it to the operating database
requires separate approval. It does not apply earlier pending migrations itself.
Deploy compatible Go/Python/web readers before separately enabling the action.
Normal ingestion, forecasting and browsing do not depend on the external drive.

Install tested Restic 0.19.1 with `uv run --locked python scripts/install_restic.py`
(also called by bootstrap and CI). Its Homebrew bottles are checksum-pinned for
Apple Silicon and Linux test runners. Restic repository format 2 supplies
encryption, deduplication and compression. See the primary
[repository/key documentation](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html),
[integrity checks](https://restic.readthedocs.io/en/stable/045_working_with_repos.html)
and [restoration](https://restic.readthedocs.io/en/stable/050_restore.html).

### Enroll without changing existing drive files

1. Connect the owner's drive. Use `diskutil info -plist <mount>` to inspect the
   actual external volume UUID, mount point, filesystem, encryption and writable
   state. A display name is insufficient. APFS Encrypted is recommended when
   suitable; do not reformat an existing drive to use this workflow. Restic
   encryption is mandatory even when filesystem encryption is unavailable.
2. Retain a strong recovery password independently of the Mac and drive. For NTC,
   create a generic password in Keychain Access with the current macOS account
   (`$USER`) and service `matchforge-restic-ntc`. The entry is checked without
   displaying its password. Restic retrieves it through `RESTIC_PASSWORD_COMMAND`,
   using `/usr/bin/security find-generic-password -a <current-user> -s
   matchforge-restic-ntc -w`. The command contains no password; the password is not
   placed in arguments, environment values, configuration, Git or logs.
3. Explicitly initialize a new dedicated repository:

   ```sh
   uv run --locked python -m scripts.backup_destination \
     --mount <external-volume-mount> --volume-uuid <verified-volume-uuid> \
     --keychain-service matchforge-restic-ntc --recovery-key-retained
   ```

   Enrollment checks the exact registered-file estimate and available capacity
   before creating the directory. Unresolved originals block enrollment as well
   as backup. Existing `MatchForgeBackup` directories are never reinitialized.
   Record the returned repository ID separately; it is checked after authentication.
4. Set the seven `MATCHFORGE_BACKUP_*` settings in local `.env` from the example,
   preserving all existing values. Use the NTC Keychain service, leaving the
   password-file setting empty. Set
   `RECOVERY_KEY_RETAINED=true` only after retaining the independent password.
   `ENABLED=true` remains a separate operating activation, not an enrollment side
   effect. The password itself is never a configuration value.
5. After activation approval, open Admin, refresh status, run preflight and confirm.
   Missing originals, wrong drive/repository/key, read-only storage, insufficient
   space or unknown dependencies block the backup. Less than the recommended 20%
   free headroom is disclosed as a planning warning, not a passing guarantee.

Repository writes use open directory descriptors and `fchdir` in an exec child,
not a mount-path fallback. Device identity is rechecked. Initialization creates
only the dedicated child directory through the verified volume descriptor. No
format, rename, erase, prune, retention deletion or automatic unlock is performed.
The [Python descriptor APIs](https://docs.python.org/3.13/library/os.html#os.fchdir)
and [subprocess descriptor inheritance](https://docs.python.org/3.13/library/subprocess.html#subprocess.Popen)
support this; substitution tests exercise the actual Restic executable.

One dump worker and two Restic CPUs/readers run at reduced process priority.
Preflight estimates local staging/read-back and external capacity; dump expansion
and growth can exceed estimates, so a write/verification failure remains explicit.
Original Parquet/gzip/source bytes are preserved; no application-level
recompression is performed. Successful completion requires full repository data
checking, a restored byte-for-byte capture and manifest validation. Only then is
the new recovery point tagged `matchforge-verified` and its work result published.
Restic tagging replaces metadata for this new snapshot; previous verified points
remain untouched. A snapshot command's exit status alone is insufficient.

Status includes measured repository-file bytes at verification, newly stored
packed bytes, history, progress, errors and repository-lock/eject state. Backup
age measures time since the database snapshot; the 30-day due date starts at
successful verification. Failed/cancelled jobs never reset it. Reminders and
completion announcements appear in the application; no macOS background
notification agent or automatic backup is enabled. Connecting the drive only
makes the manual action available. Safe-to-eject status is a timed observation;
always use macOS Eject. Interrupted work may leave an unverified snapshot/stale
Restic lock. Inspect the exact run/process before any manual unlock; the workflow
does not silently clear locks or remove partial recovery evidence.

### Restore after losing the original Mac

Keep the independent password, volume/repository IDs, these instructions and tool
versions accessible without the original Keychain. Losing every decryption key
makes encrypted backups unrecoverable. A password-file path or Keychain service
name by itself is not a recovery key.

On the new Mac, install the tested Restic and PostgreSQL tools. Authenticate the
existing repository with the separately retained password; do not initialize it.
List `restic snapshots --tag matchforge-verified --json`, run `check --read-data`,
and select an exact snapshot ID. Read its `paths` entry from snapshot metadata and
restore `<snapshot-id>:<captured-payload-path>` with `--target <new-empty-root>
--verify`. This is a path inside the snapshot; the original working directory is
not needed. Verify `recovery.json`, all listed checksums and the full file set.
Restore `application.tar` into a new application directory using a safe data-only
tar filter, install the locked dependencies, and configure fresh local credentials.
The capture records exact Git/schema/lock identity and non-secret capture-process
settings; it does not claim an unknown running build was identified.

Run the explicit isolated `verify-restore` command above first. For complete
cluster recovery, replay `globals.sql` and the dump only in a newly provisioned
isolated PostgreSQL cluster, preserving owners/ACLs/extensions. Never replay
globals over an operating cluster as a test. Keep provider schedules/workers
disabled until separately approved adoption. The integration test restores using
the archived application from a different directory, rechecks every table and
historical cutoff, and independently tests global-role/ownership replay. A real
operating restore drill and measured RTO remain required before claiming them.

Retain the latest verified point and at least one earlier independently verified
point when capacity permits. Measure actual initial and incremental repository
growth before choosing additional monthly retention. Automatic pruning stays
disabled; capacity pressure never permits dropping required files or deleting the
only complete point. Full database restore drills are explicit operator commands,
not silently launched by reminders or normal backup status requests.

## Provider fixture recovery

The operational scheduler polls yesterday and today in Africa/Lagos time so
matches still awaiting a final status continue receiving provider updates after
midnight. A final status requires provider evidence.

Operational duplicate fixtures are resolved using explicit provider team-ID
crosswalks plus identical canonical competition, season, and kickoff. Conflicting
scores, ambiguous candidates, and historical rows remain outside this display
reconciliation. Source fixtures and mappings are retained; the fixture API shows
the selected representative from active duplicate resolutions. Historical audits
preserve operational resolutions outside their own history scope.
