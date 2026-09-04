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

Canonical ingestion consumes this boundary only after re-verifying the immutable manifest and every declared resource. See [Canonical ingestion](canonical-ingestion.md). Normalized event publication then consumes the same verified acquisition and registered canonical catalogue. See [Event datasets](event-datasets.md). Published event datasets receive policy-driven [data validation](data-validation.md), and each ingestion publishes immutable [ingestion reports](ingestion-reports.md). 360 normalization remains a later phase.

## Provider capability registry

Each provider declares an immutable `ProviderCapabilityV1` before it is enabled. The declaration
records terms status, supported competition/season scopes, resource-level historical coverage,
update semantics, cursor/webhook support, rate limits, credential references, and adapter version.
The registry stores only non-secret credential references; API keys and tokens never belong in the
capability declaration.

The current StatsBomb Open Data adapter declares the accepted World Cup 2022 and Premier League
2015/16 scopes. Its commit-pinned snapshot contract is enabled for research use without a
credential reference. This registry describes capability, not global source authority; later
reconciliation policy remains responsible for field-level source selection.

Provider roles use the versioned `tier_a` (event intelligence), `tier_b`
(match/statistical enrichment), and `tier_c` (market benchmark) vocabulary. A
provider may declare more than one role; roles describe supplied capability, not
trust priority. StatsBomb Open Data is currently declared as `tier_a` only.

TotalCorner is a gated `tier_b`/`tier_c` candidate under the official JSON REST
API (`/v1/`). It is not enabled until credentials, account timezone/language,
coverage scopes, and licensing/terms approval are recorded. Its aggregate
statistics cannot substitute for Tier A event geometry, and provider-defined
fields such as `dangerous_attacks` retain provider provenance.

Enabled providers also require an immutable `ProviderSyncPolicyV1`. It binds
resource and competition/season scope to configurable discovery cadence,
look-ahead/backfill windows, historical-backfill mode, cursor strategy,
timeouts, bounded retry delays, rate/burst limits, freshness objective, and
adapter version. A webhook can trigger work, but scheduled reconciliation
remains required for recovery; a missing update is never treated as valid data.

Provider-specific `ProviderRuntimePolicyV1` separately governs request timeout,
concurrency, steady/burst limits, quota budgets, retryable status/error classes,
bounded exponential backoff with jitter, circuit-breaker thresholds/cool-down,
probe cadence, and stale-data escalation. Runtime degradation is observable and
must not silently publish missing data or create an unbounded retry storm.

Provider resources declare `ProviderResourceContractV1` with explicit schema,
adapter, parser, and normalizer versions plus required/optional fields and
enumerations. Compatibility inspection accepts additive fields, surfaces
unknown enum values as warnings without relabeling them, and quarantines
missing required fields or unsupported explicit schema versions. Historical
fixtures for each declared contract remain deterministic evidence for adapter
upgrades.

Authenticated providers use `ProviderCredentialRefV1` and `ProviderConfigV1`.
Only non-secret URI references, credential type, rotation metadata, HTTPS base
URL, and policy references are persisted. Tokens never enter source control,
manifests, logs, exceptions, artifacts, or reports. Credential rotation changes
the reference metadata, not provider identity or historical source lineage.

`ProviderSyncWorkerV1` remains Python-owned. Its callback performs one complete
acquisition/validation/publication cycle and advances durable progress only
after that cycle is safe to retry. The worker supports cooperative shutdown
between cycles; restart is therefore at-least-once and relies on durable
cursor/job identity for semantic convergence. Go may expose controls later but
does not own provider normalization or reconciliation.

`AutomaticAcquisitionFlowV1` fixes the steady-state order: discover, checkpoint,
acquire, preserve, validate, normalize, resolve, reconcile, quarantine, publish,
advance the cursor, emit a change set, then trigger downstream eligibility.
Failure stops the flow before later stages; a successful fetch is never treated
as canonical publication.

Durable synchronization state is relational: `provider_sync_runs` records
operational attempts, `provider_resource_cursors` records checkpoints,
`acquisition_jobs` provides at-least-once semantic identity,
`acquired_resources` binds published bytes to source lineage,
`quarantine_records` isolates unsafe units, and `canonical_change_sets` records
trusted downstream changes. Cursor advancement is valid only after the linked
resource contract completes; retries converge on the same resource revision.

`PartialFailureReportV1` isolates each resource outcome as `SUCCEEDED`,
`RETRYABLE`, `QUARANTINED`, or `FAILED`. Aggregate status is `SUCCEEDED`,
`PARTIAL`, or `FAILED`; one bad resource never silently invalidates or marks
unprocessed resources as complete.

Trusted publication emits immutable `CanonicalChangeSetV1` evidence binding sync
runs, source-resource checksums, affected canonical IDs, added/superseding
observations, analytical partitions, football/knowledge-time ranges, and both
resolution and quality policy versions. Downstream eligibility responds to this
change set, never to raw provider notifications.

## Observability

Each provider/resource observation is emitted as an immutable,
machine-readable `ProviderObservabilitySnapshotV1`. It records freshness
timestamps and target, discovery/fetch/unchanged counts, acquired bytes,
validation and resolution outcomes, quarantine and conflict backlog, retries,
rate-limit responses, processing latency, publication/reconciliation failures,
change-set emissions, cursor lag, and circuit state. The snapshot exposes a
deterministic freshness status and alert-condition codes for stale or never
successful resources, open circuits, and present validation, quarantine,
conflict, publication, or reconciliation failures. Spike and drop thresholds
remain versioned operational configuration; consumers compare these snapshots
without changing the recorded evidence.

Phase 2B extends the same snapshot with schema-compatibility failures, quota
exhaustion, resolution-review backlog, dataset-rebuild queue depth, stale
dependency count, and cursor-advance time. These fields make the required
foundation health signals consumable without requiring a dashboard.

`ProviderPlatformAcceptanceReportV1` records the reviewed Phase 1B gate. It
requires explicit evidence references and reports provider schema/runtime
safety, secret-reference boundaries, resolution, quarantine/reprocessing,
cross-source reconciliation, and trusted change-set publication. Overall PASS
requires at least two approved provider namespaces exercised end-to-end;
missing evidence remains `NOT_RUN` and a single exercised provider is `FAIL`.

## StatsBomb Open Data

`StatsBombOpenDataAdapter` implements the provider boundary for competitions, season matches, lineups, and events. It also exposes StatsBomb 360 resources without adding them to the provider-neutral protocol.

Every adapter instance requires a full 40-character lowercase Git commit SHA. Resource URLs use `raw.githubusercontent.com` with that immutable revision; branches and tags are rejected. Requests have a 60-second timeout and a 128 MiB per-resource limit. Provider identifiers must be positive integers.

StatsBomb attribution is retained in every source manifest:

```text
Data provided by StatsBomb
```

## Football-Data.co.uk Phase 1B proof

`FootballDataUkAdapter` is restricted to the approved Phase 1B corpus:
`notes.txt`, Premier League `E0/2526`, and Premier League `E0/1516`. It uses
the `football_data_uk` namespace, direct provider-published CSV resources, no
credentials, and the Tier B match/statistical-enrichment role. Its
`FootballDataUkHistoricalLeagueCsvV1` contract requires result fields,
preserves additive columns, and quarantines missing or duplicate headers.

This adapter does not expose event, lineup, or 360 resources. A URL is only a
locator: later acquisition records immutable raw-byte SHA-256 identities and
the observed MatchForge acquisition time. It must not claim strict historical
provider knowledge time or alter Sprint 2 evidence.

`FootballDataUkSourceResourceV1` is the content-addressed receipt for each
captured resource. It binds the frozen path, HTTP response metadata, byte size,
SHA-256, MatchForge observation time, adapter/parser/normalizer versions, and
the matching MatchForge resource contract. It records no provider-native schema
version and classifies historical knowledge as `retrospective`; the resource
cannot imply when Football-Data.co.uk first knew a historical row.

`FootballDataUkRawStoreV1` writes a receipt-verified payload beneath a path
containing both the source-path digest and raw SHA-256. A later capture at the
same provider path with changed bytes therefore receives a separate immutable
file. A same-byte retry verifies the existing file; a receipt/payload mismatch
fails before any write.

`parse_football_data_uk_csv` validates receipt-matched UTF-8 CSV bytes before
provider normalization. It keeps header order, records a deterministic header
SHA-256, reports per-column non-null/null counts and coverage for that exact
resource checksum, preserves additive columns, and rejects malformed rows.
Missing required fields return schema quarantine evidence rather than a
partially normalized dataset.

`normalize_football_data_uk_record` then produces a provider-normalized
match-level observation only. It validates full-time and half-time score/result
consistency, preserves a timezone-naive provider date/time, and retains all raw
columns. Recognized shots, corners, fouls, cards, booking points, free kicks,
offsides, and woodwork fields remain provider aggregate statistics; this path
does not create events, lineups, or 360 data.

`FootballDataUkAcquirerV1` is the only bounded live-acquisition entry point for
this proof. It requests `notes.txt`, E0/2526, then E0/1516; captures request
start and observed completion time plus HTTP status/content type/ETag/Last-
Modified; creates the content-addressed receipt; and writes the receipt-verified
bytes immutably before returning. It cannot accept paths outside that frozen
three-resource scope.

`FootballDataUkOverlapPrefixSelectionV1` applies the frozen P1 source order:
provider match date, valid local kickoff time when present, then CSV record
index. It selects the shortest prefix covering the R3 team universe, a valid
HC/AC pair when those columns exist, and a record explicitly supplied as trusted
by later canonical-resolution evidence. It neither resolves identities nor
derives trust from names, scores, or provider IDs.

`FootballDataUkTeamCrosswalkV1` maps an exact provider label only after review.
`resolve_football_data_uk_team` creates an append-only `ResolutionDecisionV1`
when that reviewed mapping agrees with one context-qualified canonical candidate.
An unreviewed label is never auto-merged: it remains review-required when
candidates exist and is quarantined when none exist.

`FootballDataUkMatchResolutionContextV1` requires those reviewed canonical
competition, season, and ordered team IDs together with the provider match date.
`resolve_football_data_uk_match` auto-accepts only one date-compatible canonical
candidate, recording an append-only `ResolutionDecisionV1`. No candidate or a
date mismatch is quarantined; multiple candidates require review. Scores and
results are deliberately absent from match identity.

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
