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

Dataset identity hashes the normalized contract, normalizer, provider revision, exact source scope, canonical partitions, and logical row content. An explicit rebuild also hashes the complete `DatasetBuildSpecV1` and the resolved source-resource and canonical-event inputs. Parquet options are fixed. Clean writes with the same inputs produce the same physical and logical checksums.

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

For the StatsBomb normalized-event builder, `source_input_refs` must be the
sorted registered values `source_resource:<uuid>:<sha256>`, one per resource
in the pinned acquisition manifest. `canonical_input_refs` must be the sorted
`canonical_event:<uuid>` values resolved from that source snapshot. The builder
rejects a request when either list does not match the registered inputs, so it
cannot follow a mutable latest-source alias.

For `knowledge_mode = historical`, the builder also rejects a pinned source
whose acquisition time is later than `knowledge_cutoff`. A later correction can
therefore only produce a new dataset under a build specification whose recorded
knowledge cutoff permits that source; it cannot rewrite an earlier historical
view.

New explicit builds store the build-spec SHA-256 in `dataset_versions` and in
the immutable `DatasetManifestV1`. Older dataset rows remain valid with no
build-spec checksum because their original build inputs cannot be reconstructed
without guessing.

`StatsBombEventDatasetPublisher.verify(dataset_id)` reads the manifest and
Parquet files again, compares logical and physical file checksums, confirms the
registered identity, and checks that every source input has a dependency edge.
For a trusted correction, a successful replacement registers `D1 → D2` as a
`DERIVED_FROM` edge before appending `SUPERSEDED` for D1. Failed replacement
attempts leave D1 `REBUILD_REQUIRED`.
