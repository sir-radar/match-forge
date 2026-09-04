# Data validation

## Boundary

`football.validation.StatsBombDatasetValidator` validates one registered StatsBomb normalized event dataset. It reads immutable Parquet through the schema-bound store, resolves canonical match and lineup state at the dataset source snapshot's acquisition time, applies `schemas/quality/statsbomb-quality-policy-v1.json`, and registers one immutable validation run in PostgreSQL.

Validation does not mutate raw resources, Parquet files, canonical observations, or source processing statuses. `QUARANTINE` is a downstream exclusion classification recorded on a finding; it does not move or overwrite an immutable artifact.

The [`football` CLI](cli.md) validates a season automatically after ingestion and also exposes explicit latest-season validation. Each completed ingestion publishes a machine-readable and human-readable [ingestion report](ingestion-reports.md); season reports include validation status and finding counts by severity, rule, and action.

## Checks

The validator checks:

- duplicate match partitions, event identities, and per-match event indexes;
- incomplete provider-to-canonical player identities and event players absent from lineups;
- invalid event periods, clocks, clock ordering, and second values;
- missing, valid, and out-of-bounds coordinate-state consistency;
- regulation and extra-time goal totals against match scores, excluding period 5 shootouts;
- paired StatsBomb own-goal events, counting the beneficiary-side `Own Goal For` observation once;
- lineup team membership, cross-team players, and non-monotonic provider position stints;
- contradictory player name, nickname, and country facts with exact resource variants;
- unknown provider event types with preserved null canonical mappings;
- malformed embedded provider event JSON;
- registered Parquet schema, physical checksum, logical checksum, row count, and size.

Valid out-of-bounds coordinates and unknown event types remain preserved with warnings. Impossible provider clocks use authoritative `event_index` order and exclude affected temporal features. Non-monotonic StatsBomb position stints remain preserved with warnings because real provider observations contain them. Contradictory player facts retain every source variant, null the disputed canonical consensus field, and produce warnings. Broken identity, score, coordinate, or lineup invariants receive quarantine classifications. Dataset registry integrity failures are fatal.

## Status

Run status is deterministic from finding severity:

```text
FATAL       → failed
QUARANTINE  → quarantined
WARNING     → warnings
INFO/none   → passed
```

## Persistence and idempotency

`validation_runs` binds dataset version, source snapshot, quality-policy version and checksum, validator version, status, and original execution time. `validation_findings` stores deterministic finding identity, severity, action, scope, evidence, optional dataset file, and optional source resource.

Composite foreign keys prevent findings from referencing a file from another dataset or a resource from another source snapshot. Dataset version, manifest checksum, policy checksum, and validator version determine validation-run identity. An identical rerun verifies the existing run and findings without changing timestamps. Advisory locking serializes concurrent registration.

Phase 1B quarantine uses `QuarantineRecordV1` to preserve provider/resource
identity, source checksums, canonical candidates, reason code, evidence,
policy version, attempt history, and review status. Network failure remains a
retryable acquisition-run error, not a data-quarantine reason. Raw evidence is
never deleted or rewritten; reprocessing creates new history.

`PostgresQuarantineRecordStoreV1` registers active records only after matching
their provider and source checksums to an acquired resource and its acquisition
job. Terminal transitions remain reprocessing work; initial records persist as
`open` while retaining their full `QuarantineRecordV1` details.

Eligible changes create append-only `QuarantineReprocessRequestV1` records for
mapping review, schema fixes, provider corrections, or policy versioning. Each
request points to the source quarantine record and trigger evidence; it never
rewrites the prior quarantine attempt or silently reuses a new policy as old
evidence.
