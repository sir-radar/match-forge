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
