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
