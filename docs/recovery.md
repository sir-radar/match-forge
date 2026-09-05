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

## Immutable byte verification

`football integrity raw <source_resource_id>`, `football integrity dataset <dataset_id>`,
and `football integrity model <model_artifact_id>` inspect only registered files beneath the
configured data root. Each command compares the stored SHA-256 and byte size with the actual file.
Dataset checks also compare its database registration, manifest, Parquet bytes, and logical checksum.
Model checks compare its registration, manifest, every registered file, and the portable model-state
checksum. A missing, unreadable, changed, or contradictory registration fails; the command never
repairs or changes stored data.

## Retained test-only forecast lineage

`artifact_retirement_events` is append-only. It can retain the approved synthetic forecast rows
while excluding only those explicit IDs from the production hard-gate population. It never changes
forecast bytes, artifact links, or dependency edges. Record the approved events with:

```text
football --code-commit-sha <git-sha> retire approved-test-forecast-lineage \
  --evidence-reference <decision-reference>
```

Then run `football integrity hard-gate`. Its output reports production failures separately from
retired test-only physical failures, plus retained artifact-link and lineage counts. No source
kind, timestamp, missing-byte pattern, or other heuristic can exclude a forecast.

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
