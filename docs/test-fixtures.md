# Sprint 1 test fixtures

## Purpose

`data/fixtures/statsbomb/sprint1` contains small synthetic StatsBomb-shaped bundles for deterministic tests. No fixture contains real provider data or requires network access.

Each fixture has a `fixture.json` conforming to `schemas/contracts/sprint1-fixture-v1.schema.json`. The manifest pins source metadata, acquisition time, resource paths, byte sizes, SHA-256 checksums, and expected pipeline results. `tests.support.sprint1_fixtures` rejects missing, undeclared, reordered, unsafe, size-mismatched, or checksum-mismatched resources.

## Cases

- `valid`: clean acquisition, canonical ingestion, event Parquet publication, and passed validation.
- `quality`: preserved provider anomalies producing one quarantine and three warning rules.
- `malformed-events`: malformed JSON preserved by acquisition and rejected atomically before PostgreSQL source registration.

## Coverage

`tests/test_sprint1_fixtures.py` validates fixture contracts and integrity. `tests/integration/test_sprint1_fixtures.py` runs production services end to end against a fresh migrated PostgreSQL database, checks canonical counts and bidirectional dataset lineage, then repeats the pipeline to prove immutable idempotency.

Run all fixture and storage checks with:

```bash
make integration
```

When changing fixture bytes, update the corresponding byte size, SHA-256 checksum, and expected result in the same change. Keep fixtures synthetic and minimal.
