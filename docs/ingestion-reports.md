# Ingestion reports

## Contract

Every successful `football ingest competitions` and `football ingest season <id>` command publishes `IngestionReportV1` in JSON and Markdown. The JSON contract is `schemas/contracts/ingestion-report-v1.schema.json`.

Reports contain:

- provider and commit-pinned source revision;
- every source snapshot role, immutable manifest, resource count, and byte count;
- provider competition and season scope;
- canonical entity counts;
- normalized dataset identity, manifest, files, rows, and bytes when applicable;
- validation run, status, and findings grouped by severity, rule, and action when applicable.

Season ingestion validates the published event dataset before reporting. Competition-only and empty-season reports have null dataset and validation sections.

## Immutable layout

```text
reports/ingestion/
  report=<deterministic-uuid>/
    ingestion-report-v1.json
    ingestion-report-v1.md
```

Report identity uses the operation, ordered source-manifest checksums, provider scope, dataset version, and validation run. `generated_at` uses the latest immutable source acquisition time. Identical ingestion therefore produces identical paths and bytes.

Both formats use exclusive publication. An identical rerun verifies existing bytes without rewriting them. A conflicting file fails closed.
