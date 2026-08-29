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
- lineup team membership, cross-team players, and non-monotonic provider position stints;
- unknown provider event types with preserved null canonical mappings;
- malformed embedded provider event JSON;
- registered Parquet schema, physical checksum, logical checksum, row count, and size.

Valid out-of-bounds coordinates and unknown event types remain preserved with warnings. Impossible provider clocks use authoritative `event_index` order and exclude affected temporal features. Non-monotonic StatsBomb position stints remain preserved with warnings because real provider observations contain them. Broken identity, score, coordinate, or lineup invariants receive quarantine classifications. Dataset registry integrity failures are fatal.

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
