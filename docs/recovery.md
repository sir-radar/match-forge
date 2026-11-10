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
integration test separately replays globals and ownership into a new networkless
PostgreSQL container. Interrupted drills may leave a disposable database/root;
inspect their exact ownership before removing them. A failed/incomplete capture
or corrupt bytes cannot be used as passing recovery evidence.

Thirty-day manual backups are the owner-selected policy. They may leave roughly
a month of changes without an external recovery point; they do not guarantee the
previously desired 24-hour RPO. Measure full operating restore time before adopting
an RTO. The current external drive and missing original-file dependencies must be
verified before claiming complete operating recovery.

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
