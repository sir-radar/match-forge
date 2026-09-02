# Normalized event datasets

## Boundary

`football.datasets.StatsBombEventDatasetPublisher` consumes a previously acquired `AcquisitionResult`, a PostgreSQL connection, and the same configured data root used by source acquisition. It re-verifies the immutable source manifest and raw bytes before reading canonical state.

Publication requires the exact acquisition-manifest scope and each event resource to have been registered and parsed by `StatsBombCanonicalIngestor`. It never creates or repairs canonical identities implicitly.

## Normalized contract

Each StatsBomb event resource produces one Parquet file using `schemas/arrow/normalized-events-v1.json`, schema version `v1`, and normalizer `statsbomb-normalizer-v1`. Rows are ordered by `event_index`, which remains authoritative when football timestamps repeat.

Cross-provider streams remain separate `ProviderEventStreamV1` values with
their own source order and lineage. `EventStreamReconciliationV1` permits an
authoritative stream; multi-provider fusion fails closed until a separately
versioned alignment contract exists. Aggregate providers cannot manufacture
missing event geometry.

Normalized rows contain:

- canonical and provider event, match, team, and player identifiers;
- provider event type plus nullable known canonical type slug;
- provider timestamp, minute, second, and period;
- original StatsBomb coordinates, bounded normalized coordinates, and location quality;
- the complete provider event as deterministic canonical JSON.

Unknown provider event types keep their provider ID and name with a null canonical mapping. Out-of-bounds coordinates remain unchanged while normalized coordinates stay null. [Data validation](data-validation.md) classifies these preserved states, and [ingestion reports](ingestion-reports.md) summarize the resulting quality evidence.

## Immutable layout

```text
normalized/events/
  schema=v1/
    dataset=<dataset-version-uuid>/
      competition_id=<canonical-uuid>/
        season_id=<canonical-uuid>/
          match_id=<canonical-uuid>/
            events.parquet

manifests/datasets/
  dataset=<dataset-version-uuid>/
    dataset-manifest-v1.json
```

Dataset identity hashes the normalized contract, normalizer, provider revision, exact source scope, canonical partitions, and logical row content. Parquet options are fixed. Clean writes with the same inputs produce the same physical and logical checksums.

## Publication and recovery

Parquet is written beneath a recognizable staging path, read back with the exact Arrow schema, and checked for row count and logical checksum before exclusive hard-link publication. Existing files are never overwritten. An identical rerun verifies existing bytes without changing modification time. A conflicting or malformed artifact fails closed.

After every file and the `DatasetManifestV1` manifest are immutable, one PostgreSQL transaction registers `dataset_versions`, every resource in the exact source-manifest scope as `dataset_inputs`, and `dataset_files`. Advisory locking serializes concurrent registration of the same identity. Database failure can leave valid immutable files but no registry rows; rerunning reconciles that state without rewriting artifacts.

## Deterministic rebuild identity

`DatasetBuildSpecV1` records the immutable source and canonical input
references, dataset contract/version, point-in-time football and knowledge
cutoffs, knowledge mode, feature versions, quality/resolution policies, code
Git SHA, dependency-lock checksum, and canonical JSON configuration. Its
checksum is the build identity. A source correction marks the old derived
state affected or stale; rebuilding with a new specification publishes a new
dataset version and leaves the historical dataset addressable.

`DatasetRebuildRequestV1` is the durable operator/worker hand-off. It binds a
dataset reference to the exact build-spec checksum, records whether the
request came from a source correction, manual replay, or failed publication,
and carries an explicit attempt and status. Retries create a new request
snapshot or advance durable request state; they never overwrite the prior
dataset version.
