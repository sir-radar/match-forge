# Source acquisition

## Boundary

Source acquisition preserves provider bytes before parsing or normalization. The production flow is:

```text
FootballDataProvider
    → pinned provider resource descriptor
    → bounded fetch
    → immutable raw publication
    → SourceManifestV1
```

Canonical ingestion consumes this boundary only after re-verifying the immutable manifest and every declared resource. See [Canonical ingestion](canonical-ingestion.md). Event normalization, Parquet publication, and data-quality reports remain later phases.

## StatsBomb Open Data

`StatsBombOpenDataAdapter` implements the provider boundary for competitions, season matches, lineups, and events. It also exposes StatsBomb 360 resources without adding them to the provider-neutral protocol.

Every adapter instance requires a full 40-character lowercase Git commit SHA. Resource URLs use `raw.githubusercontent.com` with that immutable revision; branches and tags are rejected. Requests have a 60-second timeout and a 128 MiB per-resource limit. Provider identifiers must be positive integers.

StatsBomb attribution is retained in every source manifest:

```text
Data provided by StatsBomb
```

## Immutable layout

The local production store writes beneath a configured data root:

```text
raw/
  provider=statsbomb_open_data/
    snapshot=<git-sha>/
      data/...

manifests/
  provider=statsbomb_open_data/
    snapshot=<git-sha>/
      scope=<resource-set-sha256>/
        source-manifest-v1.json
```

Provider paths must be normalized relative POSIX paths. Absolute paths, parent traversal, backslashes, symlink escapes, and immutable-path conflicts are rejected.

Publication writes a temporary file on the target filesystem, flushes it, and creates the final path with an exclusive hard link. Concurrent writers can never replace an existing final file. Temporary files are removed after success or failure.

## Idempotency and recovery

The manifest scope key is deterministic for provider, source revision, resource paths, and media types. A completed identical rerun verifies the manifest and raw checksums without network access or file modification.

If an interrupted first acquisition preserved some raw files but did not publish a manifest, the retry fetches those resources and byte-compares them before reuse. If a manifest exists but a raw file is missing, the resource may be restored only when fetched bytes match the manifest checksum and size. Existing changed bytes are never overwritten.

Checksum conflicts use the stable `SB_SOURCE_CHECKSUM_MISMATCH` code defined by the StatsBomb quality policy. They are fatal for the acquisition scope.

## Storage evolution

`ImmutableRawStore` currently provides the local filesystem implementation used for development and deterministic tests. A later object-store implementation must preserve the same exclusive publication, checksum, path, manifest, retry, and attribution contracts.
